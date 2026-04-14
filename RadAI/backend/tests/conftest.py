"""Pytest configuration and shared fixtures for RadAI backend tests."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test environment variables BEFORE importing app modules
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-chars-long!!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["ORTHANC_PASSWORD"] = "test"
os.environ["ORTHANC_URL"] = "http://localhost:8042"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "DEBUG"

# Clear any cached settings so they pick up test env vars
from app.config import get_settings
get_settings.cache_clear()

from app.db.models import Base, Finding, ModelVersion, ModelMetric, Report, Study, User
from app.auth import create_access_token


# ─── Database fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine using SQLite for unit tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# ─── App fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings():
    """Return mock settings for testing."""
    class TestSettings:
        environment = "testing"
        log_level = "DEBUG"
        jwt_secret = "test-secret-key-at-least-32-chars-long!!"
        jwt_algorithm = "HS256"
        jwt_access_expiry_hours = 24
        jwt_refresh_expiry_days = 7
        database_url = "sqlite+aiosqlite:///:memory:"
        postgres_db = "test_radai"
        postgres_user = "test"
        postgres_password = "test"
        redis_url = "redis://localhost:6379/0"
        celery_broker_url = "redis://localhost:6379/0"
        celery_result_backend = "redis://localhost:6379/0"
        orthanc_url = "http://localhost:8042"
        orthanc_user = "orthanc"
        orthanc_password = "test"
        ollama_url = "http://localhost:11434"
        ollama_model = "MedAIBase/MedGemma1.5:4b-it"
        ollama_timeout = 120
        openrouter_api_key = ""
        openrouter_model = "google/gemma-4-31b-it"
        hf_token = ""
        hf_medgemma_model = "google/medgemma-1.5-4b-it"
        whisper_model = "large-v3"
        whisper_device = "cuda"
        whisper_compute_type = "float16"
        cloud_gpu_url = ""
        cloud_gpu_api_key = ""
        temp_processing_dir = "/tmp/radai-processing"
        reports_dir = "./reports"
        models_dir = "./models"
        backend_host = "0.0.0.0"
        backend_port = 8000
        offline_mode = False

    return TestSettings()


@pytest.fixture
def app(mock_settings):
    """Create a FastAPI test application with mocked dependencies."""
    with patch("app.config.get_settings", return_value=mock_settings):
        from app.main import app as fastapi_app
        yield fastapi_app


@pytest_asyncio.fixture
async def async_client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ─── Auth fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def test_user():
    """Create a test user dict."""
    return {
        "id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "role": "radiologist",
        "is_active": True,
    }


@pytest.fixture
def auth_token(test_user):
    """Create a valid JWT token for testing."""
    return create_access_token(
        user_id=test_user["id"],
        username=test_user["username"],
        role=test_user["role"],
    )


@pytest.fixture
def auth_headers(auth_token):
    """Create auth headers for test requests."""
    return {"Authorization": f"Bearer {auth_token}"}


# ─── Mock data factories ─────────────────────────────────────────────────────

@pytest.fixture
def study_factory():
    """Factory for creating test Study objects."""
    def _create_study(orthanc_id: str = "test-study-123", **kwargs) -> Study:
        return Study(
            orthanc_id=orthanc_id,
            study_instance_uid=f"1.2.3.4.5.{uuid4()}",
            modality="CT",
            body_part="CHEST",
            study_description="CT Chest Test",
            **kwargs,
        )
    return _create_study


@pytest.fixture
def finding_factory():
    """Factory for creating test Finding objects."""
    def _create_finding(
        study_id=None,
        finding_type: str = "nodule",
        location: str = "Right upper lobe",
        confidence: float = 0.85,
        **kwargs
    ) -> Finding:
        return Finding(
            study_id=study_id or uuid4(),
            finding_type=finding_type,
            location=location,
            laterality="right",
            measurements={"longest_diameter_mm": 8.5, "volume_mm3": 250.0},
            characteristics=["solid"],
            confidence=confidence,
            status="pending",
            **kwargs,
        )
    return _create_finding


@pytest.fixture
def report_factory():
    """Factory for creating test Report objects."""
    def _create_report(
        study_id=None,
        content_text: str = "Test report content",
        ai_polished: bool = False,
        **kwargs
    ) -> Report:
        return Report(
            study_id=study_id or uuid4(),
            report_type="draft",
            template_name="lung_rads",
            content_text=content_text,
            ai_polished=ai_polished,
            **kwargs,
        )
    return _create_report


# ─── Scheduler mocks ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_scheduler():
    """Create a mock ModelScheduler for testing."""
    scheduler = MagicMock()
    scheduler.current_model = "none"
    scheduler.run_totalsegmentator = MagicMock()
    scheduler.load_nninteractive = MagicMock()
    scheduler.load_litemedsam = MagicMock()
    scheduler.load_whisper = MagicMock()
    scheduler.transcribe_audio = AsyncMock(return_value="Transcribed medical text")
    scheduler.generate_report_local = AsyncMock(
        return_value="Polished radiology report prose."
    )
    scheduler.generate_report_cloud_tier2 = AsyncMock(
        return_value="Cloud-polished radiology report."
    )
    scheduler.unload_current = MagicMock()
    return scheduler
