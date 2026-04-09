"""RadAI — Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ─── Application ─────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    offline_mode: bool = False

    # ─── Security ────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_expiry_hours: int = 24
    jwt_refresh_expiry_days: int = 7

    # ─── Database ────────────────────────────────────────────────────────────
    database_url: str
    postgres_db: str = "radai"
    postgres_user: str = "radai"
    postgres_password: str

    # ─── Redis ───────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # ─── Orthanc ─────────────────────────────────────────────────────────────
    orthanc_url: AnyHttpUrl = "http://localhost:8042"  # type: ignore[assignment]
    orthanc_user: str = "orthanc"
    orthanc_password: str

    # ─── Ollama (Local LLM) ──────────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "MedAIBase/MedGemma1.5:4b-it"
    ollama_timeout: int = 120

    # ─── Cloud APIs (Tier 2) ─────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-31b-it"
    hf_token: str = ""
    hf_medgemma_model: str = "google/medgemma-1.5-4b-it"

    # ─── Voice Dictation (faster-whisper) ────────────────────────────────────
    # MedASR can't run via Ollama (needs audio input, not text API).
    # faster-whisper is the local ASR solution (~3 GB VRAM for large-v3).
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"

    # ─── Cloud GPU (Tier 3) ──────────────────────────────────────────────────
    cloud_gpu_url: str = ""
    cloud_gpu_api_key: str = ""

    # ─── Storage ─────────────────────────────────────────────────────────────
    temp_processing_dir: str = "/tmp/radai-processing"
    reports_dir: str = "./reports"
    models_dir: str = "./models"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str | None) -> str:
        if v:
            return v
        raise ValueError("DATABASE_URL must be set")

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings (loaded once at startup)."""
    return Settings()  # type: ignore[call-arg]
