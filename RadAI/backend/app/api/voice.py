"""RadAI — Voice transcription API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from app.auth import get_current_user
from app.db.models import User
from app.rate_limiter import limiter
from app.reporting.voice_transcription import transcribe_audio, TranscriptionError
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
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> TranscriptionOut:
    """
    Accepts an audio file (WAV, MP3, etc.) and returns the transcribed medical text.
    """
    try:
        # Read file content
        audio_bytes = await file.read()
        
        # Perform transcription
        text = await transcribe_audio(audio_bytes)
        
        return TranscriptionOut(text=text)
    except TranscriptionError as exc:
        logger.error(f"Transcription API failed: {exc}")
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
