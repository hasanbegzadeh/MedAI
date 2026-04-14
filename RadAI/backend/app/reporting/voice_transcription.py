"""RadAI — Voice transcription service using faster-whisper.

Handles medical speech-to-text for report dictation.

Architecture:
  Browser microphone → WebSocket audio stream → faster-whisper (local GPU/CPU)
  → raw transcription → OllamaClient.transcribe_medical_speech() → cleaned text

This replaces the incorrect MedASR-via-Ollama approach. MedASR requires audio
input (not text), so Ollama's text-only /api/generate endpoint cannot serve it.
faster-whisper is a battle-tested, Python-native Whisper implementation.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Lazy import — faster-whisper may not be installed in CI/testing
_whisper_model = None
_whisper_lock = None


class TranscriptionError(Exception):
    """Raised on transcription failures."""


def _get_whisper_model():
    """Lazy-load the Whisper model to avoid startup VRAM allocation.

    Uses 'large-v3' model (~3 GB VRAM) for medical-grade accuracy.
    Falls back to 'medium' (~1.5 GB) if VRAM is tight.
    """
    global _whisper_model, _whisper_lock
    import threading

    if _whisper_lock is None:
        _whisper_lock = threading.Lock()

    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                try:
                    from faster_whisper import WhisperModel

                    # Try large-v3 first (best accuracy for medical terms)
                    try:
                        _whisper_model = WhisperModel(
                            "large-v3",
                            device="cuda",
                            compute_type="float16",
                        )
                        logger.info("Loaded faster-whisper large-v3 (CUDA)")
                    except Exception:
                        # Fallback to medium if large doesn't fit in VRAM
                        _whisper_model = WhisperModel(
                            "medium",
                            device="cuda",
                            compute_type="float16",
                        )
                        logger.info("Loaded faster-whisper medium (CUDA, fallback)")
                except Exception:
                    from faster_whisper import WhisperModel

                    _whisper_model = WhisperModel(
                        "medium",
                        device="cpu",
                        compute_type="int8",
                    )
                    logger.warning("Loaded faster-whisper medium (CPU, slow)")

    return _whisper_model


async def transcribe_audio(
    audio_data: bytes,
    language: str = "en",
    initial_prompt: Optional[str] = None,
) -> str:
    """Transcribe audio bytes to text using faster-whisper.

    Args:
        audio_data: Raw audio bytes (WAV, MP3, FLAC, etc.)
        language: ISO 639-1 language code.
        initial_prompt: Optional medical context to guide transcription.
            Example: "Radiology report dictation for CT chest with contrast."

    Returns:
        Transcribed text string.

    Raises:
        TranscriptionError: On audio processing failure.
    """
    if initial_prompt is None:
        initial_prompt = (
            "Radiology report dictation. Medical terminology including: "
            "nodule, spiculated, ground-glass opacity, consolidation, "
            "pleural effusion, cardiomegaly, lymphadenopathy."
        )

    try:
        import asyncio

        model = _get_whisper_model()

        # Write audio to temp file (faster-whisper needs file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            tmp_path = f.name

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: model.transcribe(
                tmp_path,
                language=language,
                initial_prompt=initial_prompt,
                vad_filter=True,
                word_timestamps=False,
            ),
        )

        # Collect all segment texts
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        result = " ".join(text_parts)
        logger.info(
            "Transcription complete",
            chars=len(result),
            language=info.language,
            duration=f"{info.duration:.1f}s",
        )
        return result

    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc
    except Exception as exc:
        raise TranscriptionError(f"Transcription failed: {exc}") from exc


def unload_whisper_model() -> None:
    """Unload the Whisper model to free VRAM for other models."""
    global _whisper_model
    if _whisper_model is not None:
        del _whisper_model
        _whisper_model = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        import gc
        gc.collect()
        logger.info("Whisper model unloaded")
