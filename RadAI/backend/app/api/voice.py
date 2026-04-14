"""RadAI — Voice transcription API router.

Uses the model scheduler for VRAM-safe Whisper loading, ensuring
no other GPU model is loaded while transcribing.
"""

# NOTE: do NOT add `from __future__ import annotations` here. See app/api/ai.py
# for the full explanation — slowapi's @limiter.limit decorator requires
# non-stringified annotations for FastAPI schema resolution.

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from app.auth import get_current_user
from app.db.models import User
from app.rate_limiter import limiter
from app.scheduler import get_scheduler, ModelSchedulerError
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

class TranscriptionOut(BaseModel):
    text: str
    language: str = "en"

@router.post(
    "/transcribe",
    response_model=TranscriptionOut,
    summary="Transcribe medical audio to text",
)
@limiter.limit("5/minute")
async def transcribe(
    request: Request,  # required by slowapi @limiter.limit to read client IP
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> TranscriptionOut:
    """
    Accepts an audio file (WAV, MP3, WebM, etc.) and returns the transcribed
    medical text. Uses faster-whisper via the model scheduler to ensure
    VRAM is freed from other models before loading Whisper.
    """
    try:
        audio_bytes = await file.read()
        scheduler = get_scheduler()
        text = await scheduler.transcribe_audio(audio_bytes)
        return TranscriptionOut(text=text)
    except ModelSchedulerError as exc:
        logger.error(f"Transcription failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )
    except Exception as exc:
        logger.error(f"Unexpected transcription error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during transcription."
        )
