"""RadAI — Thread-safe GPU Model Scheduler.

Ensures only ONE model occupies GPU VRAM at a time on 8 GB cards.
All public methods acquire a lock before touching the GPU.
"""
from __future__ import annotations

import asyncio
import gc
import logging
import subprocess
import threading
import time
from enum import Enum
from typing import Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

logger = structlog.get_logger(__name__)

_OPENROUTER_RATE_LOCK = asyncio.Lock()
_OPENROUTER_LAST_REQUEST_AT: float | None = None
_OPENROUTER_MIN_INTERVAL_SECONDS = 2.5


def _is_retryable_openrouter_error(exception: BaseException) -> bool:
    if isinstance(exception, httpx.RequestError):
        return True
    if isinstance(exception, httpx.HTTPStatusError) and exception.response is not None:
        return exception.response.status_code in {429, 500, 502, 503, 504}
    return False


async def _ensure_openrouter_rate_limit() -> None:
    global _OPENROUTER_LAST_REQUEST_AT
    async with _OPENROUTER_RATE_LOCK:
        now = time.monotonic()
        if _OPENROUTER_LAST_REQUEST_AT is not None:
            elapsed = now - _OPENROUTER_LAST_REQUEST_AT
            if elapsed < _OPENROUTER_MIN_INTERVAL_SECONDS:
                await asyncio.sleep(_OPENROUTER_MIN_INTERVAL_SECONDS - elapsed)
        _OPENROUTER_LAST_REQUEST_AT = time.monotonic()


# Try importing torch; graceful degradation when running without GPU
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not installed — GPU scheduling disabled")


class ModelType(str, Enum):
    TOTALSEGMENTATOR = "totalsegmentator"
    NNINTERACTIVE = "nninteractive"
    LITEMEDSAM = "litemedsam"
    NONE = "none"


class ModelSchedulerError(Exception):
    """Raised when model loading or inference fails."""


class ModelScheduler:
    """Ensures only one model occupies GPU at a time.

    Usage::

        scheduler = ModelScheduler()
        scheduler.run_totalsegmentator(input_path, output_path)
        session = scheduler.load_nninteractive()
        # ... use session ...
        scheduler.unload_current()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_model: ModelType = ModelType.NONE
        self._model_instance: Optional[object] = None

    @property
    def current_model(self) -> ModelType:
        return self._current_model

    def _get_free_vram_gb(self) -> float:
        """Return free VRAM in GB, or -1 if torch unavailable."""
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return -1.0
        return torch.cuda.mem_get_info()[0] / 1e9

    def unload_current(self) -> None:
        """Free GPU VRAM by deleting the currently loaded model."""
        if self._model_instance is not None:
            logger.info("Unloading model", model=self._current_model)
            del self._model_instance
            self._model_instance = None
        self._current_model = ModelType.NONE
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        free_gb = self._get_free_vram_gb()
        if free_gb >= 0:
            logger.info("GPU VRAM freed", free_gb=f"{free_gb:.1f}")

    def run_totalsegmentator(
        self,
        input_path: str,
        output_path: str,
        roi_subset: Optional[list[str]] = None,
        fast: bool = True,
        body_seg: bool = True,
        timeout: int = 300,
        progress_callback=None,
    ) -> None:
        """Run TotalSegmentator as a subprocess, unloading any current model first.

        Args:
            input_path: Path to input NIfTI file.
            output_path: Directory for segmentation masks.
            roi_subset: List of specific structures to segment (saves VRAM).
            fast: Use --fast flag (~2-3 GB VRAM vs ~12+ GB full-res).
            body_seg: Use --body_seg to crop to body region (saves VRAM).
            timeout: Subprocess timeout in seconds.
            progress_callback: Optional callable(pct: int) for WebSocket updates.

        Raises:
            ModelSchedulerError: On subprocess failure or timeout.

        VRAM Budget (RTX 5060, 8 GB GDDR7):
            --fast:                 ~2-3 GB ✓
            --fast --body_seg:      ~2 GB ✓
            --roi_subset (5 org):   ~3-5 GB ✓
            Full resolution:        ~12+ GB ✗ (cloud-only, Tier 3)
        """
        with self._lock:
            self.unload_current()
            # TotalSegmentator >=2.0 removed `--gpu`. It accepts
            # `-d {gpu|cpu|mps|gpu:X}` — *not* `cuda`. `--body_seg` was also
            # renamed to `-bs`, and `--roi_subset` to `-rs`.
            cmd = [
                "TotalSegmentator",
                "-i", input_path,
                "-o", output_path,
                "-d", "gpu",
            ]
            if fast:
                cmd.append("--fast")
            if body_seg:
                cmd.append("-bs")
            if roi_subset:
                cmd.extend(["-rs"] + roi_subset)

            logger.info("Running TotalSegmentator", cmd=" ".join(cmd))
            if progress_callback:
                progress_callback(10)
            try:
                result = subprocess.run(
                    cmd, check=True, capture_output=True, text=True, timeout=timeout
                )
                logger.info("TotalSegmentator completed", stdout=result.stdout[-500:])
                if progress_callback:
                    progress_callback(100)
            except subprocess.TimeoutExpired as exc:
                raise ModelSchedulerError(
                    f"TotalSegmentator timed out after {timeout}s"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise ModelSchedulerError(
                    f"TotalSegmentator failed (exit {exc.returncode}): {exc.stderr[-500:]}"
                ) from exc
            # TotalSegmentator subprocess auto-frees GPU after exit

    def load_nninteractive(self) -> object:
        """Load nnInteractive inference session (6–8 GB VRAM).

        Returns:
            nnInteractiveInferenceSession instance.

        Raises:
            ModelSchedulerError: If nnInteractive cannot be loaded.
        """
        with self._lock:
            if self._current_model == ModelType.NNINTERACTIVE:
                logger.debug("nnInteractive already loaded")
                return self._model_instance  # type: ignore[return-value]

            self.unload_current()
            try:
                import torch as _torch
                from nnInteractive.inference import nnInteractiveInferenceSession

                logger.info("Loading nnInteractive")
                session = nnInteractiveInferenceSession(
                    device=_torch.device("cuda:0"),
                    use_torch_compile=False,
                    do_autozoom=True,
                )
                self._model_instance = session
                self._current_model = ModelType.NNINTERACTIVE
                logger.info("nnInteractive loaded", free_vram=f"{self._get_free_vram_gb():.1f} GB")
                return session
            except ImportError as exc:
                raise ModelSchedulerError(
                    "nnInteractive is not installed. Run: pip install nnInteractive"
                ) from exc
            except RuntimeError as exc:
                raise ModelSchedulerError(f"Failed to load nnInteractive: {exc}") from exc

    def load_litemedsam(self) -> object:
        """Load LiteMedSAM inference session (~2-3 GB VRAM).

        Returns:
            LiteMedSAM model instance.

        Raises:
            ModelSchedulerError: If LiteMedSAM cannot be loaded.
        """
        with self._lock:
            if self._current_model == ModelType.LITEMEDSAM:
                logger.debug("LiteMedSAM already loaded")
                return self._model_instance  # type: ignore[return-value]

            self.unload_current()
            try:
                from app.ai.litemedsam_infer import LiteMedSAMInference
                from app.config import get_settings

                settings = get_settings()
                checkpoint_path = Path(settings.models_dir) / "lite_medsam.pth"

                if not checkpoint_path.exists():
                    raise ModelSchedulerError(
                        f"LiteMedSAM checkpoint not found at {checkpoint_path}. "
                        "Download from: https://drive.google.com/file/d/18Zed-TUTsmr2zc5CHUWd5Tu13nb6vq6z/view?usp=sharing"
                    )

                logger.info("Loading LiteMedSAM", checkpoint=str(checkpoint_path))
                session = LiteMedSAMInference(
                    checkpoint_path=str(checkpoint_path),
                    device="cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu",
                )
                self._model_instance = session
                self._current_model = ModelType.LITEMEDSAM
                logger.info("LiteMedSAM loaded", free_vram=f"{self._get_free_vram_gb():.1f} GB")
                return session
            except (ImportError, FileNotFoundError) as exc:
                raise ModelSchedulerError(
                    f"Failed to load LiteMedSAM: {exc}"
                ) from exc
            except RuntimeError as exc:
                raise ModelSchedulerError(f"Failed to load LiteMedSAM: {exc}") from exc

    async def generate_report_local(
        self, findings_text: str, model: Optional[str] = None
    ) -> str:
        """Generate radiology report prose via local Ollama (MedGemma 1.5 4B Q4).

        Async to avoid blocking FastAPI worker threads during the 30-120s
        Ollama inference. Does NOT require GPU unload — Ollama manages its
        own VRAM independently.

        Args:
            findings_text: Structured findings as plain text.
            model: Ollama model name override.

        Returns:
            Polished report string.

        Raises:
            ModelSchedulerError: On Ollama API error.
        """
        import httpx
        from app.config import get_settings

        settings = get_settings()
        model_name = model or settings.ollama_model

        prompt = (
            "You are a radiology assistant. Rewrite the following structured findings "
            "into professional radiology report prose. "
            "PRESERVE ALL measurements, values, and anatomical details EXACTLY. "
            "DO NOT invent, add, or omit any findings.\n\n"
            f"Structured Findings:\n{findings_text}"
        )

        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={"model": model_name, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                return resp.json()["response"]
        except httpx.HTTPError as exc:
            raise ModelSchedulerError(f"Ollama request failed: {exc}") from exc

    @retry(
        retry=retry_if_exception(_is_retryable_openrouter_error),
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(multiplier=1, max=20),
        reraise=True,
    )
    async def generate_report_cloud_tier2(
        self, findings_text: str
    ) -> str:
        """Generate report via Gemma 4 31B through OpenRouter (Tier 2 cloud).

        Uses the fast, high-quality Gemma 4 31B model for complex cases.
        ONLY structured text is sent — no DICOM pixel data.

        Includes retry logic (3 attempts with exponential backoff) as a
        circuit breaker for cloud API failures.

        Args:
            findings_text: Structured findings as plain text.

        Returns:
            Polished report string.
        """
        import httpx
        from app.config import get_settings

        settings = get_settings()
        if settings.offline_mode:
            raise ModelSchedulerError(
                "Offline Mode is enabled. Cannot use Tier 2 cloud reports."
            )
        if not settings.openrouter_api_key:
            raise ModelSchedulerError(
                "OPENROUTER_API_KEY not configured. Cannot use Tier 2 cloud reports."
            )

        prompt = (
            "You are a board-certified radiologist assistant. "
            "Rewrite these structured findings into a professional radiology report. "
            "Preserve every measurement and finding exactly. "
            "Use standard radiology terminology. "
            "Do not add any findings not present in the structured data.\n\n"
            f"Findings:\n{findings_text}"
        )

        await _ensure_openrouter_rate_limit()
        async with httpx.AsyncClient(
            timeout=60,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        ) as client:
            try:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.openrouter_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2048,
                        "temperature": 0.3,
                    },
                )
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        await asyncio.sleep(int(retry_after))
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPError as exc:
                raise ModelSchedulerError(f"OpenRouter request failed: {exc}") from exc


# ─── Singleton ────────────────────────────────────────────────────────────────
_scheduler: Optional[ModelScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> ModelScheduler:
    """Return the process-wide ModelScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = ModelScheduler()
    return _scheduler
