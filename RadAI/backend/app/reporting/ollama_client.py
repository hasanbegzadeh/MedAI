"""RadAI — Ollama API client with retry and streaming support.

Wraps the Ollama HTTP API for local model inference.
Supports: MedGemma 1.5 4B (report polish), text cleanup of voice transcriptions.

NOTE: Voice-to-text (ASR) runs via faster-whisper locally, NOT through Ollama.
Ollama only accepts text prompts — MedASR/Whisper audio input is handled separately.
"""
from __future__ import annotations

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = structlog.get_logger(__name__)

# ─── Prompt templates ─────────────────────────────────────────────────────────
REPORT_POLISH_SYSTEM = (
    "You are a radiology report assistant. "
    "Your ONLY task is to rewrite the provided structured findings in professional "
    "radiology prose. You MUST preserve every measurement, number, and anatomical "
    "detail exactly as stated. NEVER add findings, diagnoses, or recommendations "
    "that are not explicitly present in the input."
)

VOICE_TRANSCRIPTION_SYSTEM = (
    "You are a medical transcription assistant. Convert the following speech transcription "
    "into clean, properly punctuated medical text. Correct obvious speech-to-text errors "
    "using standard radiology terminology."
)


class OllamaError(Exception):
    """Raised on Ollama API failures."""


class OllamaClient:
    """Async HTTP client for the local Ollama API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def _base_url(self) -> str:
        return self._settings.ollama_url

    @property
    def _model(self) -> str:
        return self._settings.ollama_model

    # ─── Generate ────────────────────────────────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Call /api/generate and return full response text.

        Args:
            prompt: User message.
            system: Optional system prompt.
            model: Override default Ollama model.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Max tokens in response.

        Returns:
            Generated text string.

        Raises:
            OllamaError: On HTTP error or malformed response.
        """
        payload = {
            "model": model or self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        logger.debug("Ollama generate", model=payload["model"], prompt_len=len(prompt))

        async with httpx.AsyncClient(timeout=self._settings.ollama_timeout) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["response"]
            except httpx.HTTPStatusError as exc:
                raise OllamaError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
            except httpx.RequestError as exc:
                raise OllamaError(f"Ollama connection failed: {exc}") from exc
            except KeyError as exc:
                raise OllamaError(f"Unexpected Ollama response shape: {exc}") from exc

    async def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
    ):
        """Stream /api/generate token-by-token (async generator).

        Yields:
            str: Each token chunk as it is generated.
        """
        payload = {
            "model": model or self._model,
            "prompt": prompt,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self._base_url}/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json as _json
                    data = _json.loads(line)
                    if token := data.get("response"):
                        yield token
                    if data.get("done"):
                        break

    # ─── Domain methods ───────────────────────────────────────────────────────
    async def polish_report(self, findings_text: str) -> str:
        """Polish a structured radiology report using MedGemma 1.5 4B."""
        return await self.generate(
            prompt=findings_text,
            system=REPORT_POLISH_SYSTEM,
            temperature=0.2,
        )

    async def transcribe_medical_speech(self, raw_transcription: str) -> str:
        """Clean up a voice-to-text transcription for medical terminology."""
        return await self.generate(
            prompt=raw_transcription,
            system=VOICE_TRANSCRIPTION_SYSTEM,
            temperature=0.1,
        )

    async def list_models(self) -> list[str]:
        """Return list of available local Ollama model names."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
            except Exception as exc:
                raise OllamaError(f"Cannot reach Ollama at {self._base_url}: {exc}") from exc

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable and the configured model is available."""
        try:
            models = await self.list_models()
            available = self._model in models
            if not available:
                logger.warning("Configured model not in Ollama", model=self._model, available=models)
            return available
        except OllamaError:
            return False
