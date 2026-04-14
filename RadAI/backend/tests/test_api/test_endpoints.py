"""Tests for the API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, app):
        """Health endpoint returns basic status."""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    def test_login_rejects_missing_credentials(self, app):
        """Login rejects empty payload."""
        client = TestClient(app)

        response = client.post("/api/v1/auth/login", json={})

        # Should return 422 (validation error) for missing fields
        assert response.status_code == 422

    def test_login_rejects_invalid_credentials(self, app):
        """Login with invalid credentials does not return 200."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "wrong"},
        )

        # Without a real DB, returns 401 (auth failure) or 500 (DB error)
        # Must NOT return 200 (would mean auth is bypassed)
        assert response.status_code != 200


class TestFindingsEndpoints:
    """Tests for findings CRUD endpoints."""

    def test_list_findings_requires_auth(self, app):
        """Findings endpoint rejects unauthenticated requests."""
        client = TestClient(app)
        study_id = str(uuid4())

        response = client.get(f"/api/v1/findings/studies/{study_id}")

        # HTTPBearer returns 401 when no token provided (newer FastAPI) or 403
        assert response.status_code in (401, 403)


class TestReportsEndpoints:
    """Tests for report generation endpoints."""

    def test_generate_report_requires_auth(self, app):
        """Report generation rejects unauthenticated requests."""
        client = TestClient(app)
        study_id = str(uuid4())

        response = client.post(
            f"/api/v1/reports/studies/{study_id}/generate",
            json={"template": "lung_rads", "use_ai_polish": False},
        )

        assert response.status_code in (401, 403)

    def test_export_pdf_requires_auth(self, app):
        """PDF export rejects unauthenticated requests."""
        client = TestClient(app)
        report_id = str(uuid4())

        response = client.post(
            f"/api/v1/reports/reports/{report_id}/export-pdf",
            json={"report_id": report_id},
        )

        assert response.status_code in (401, 403)


class TestVoiceEndpoint:
    """Tests for voice transcription endpoint."""

    def test_transcribe_requires_auth(self, app):
        """Transcription rejects unauthenticated requests."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/voice/transcribe",
            files={"file": ("test.wav", b"fake-audio-data", "audio/wav")},
        )

        assert response.status_code in (401, 403)


class TestAIJobsEndpoint:
    """Tests for AI job submission endpoints."""

    def test_run_ai_requires_auth(self, app):
        """AI job submission rejects unauthenticated requests."""
        client = TestClient(app)
        study_id = str(uuid4())

        response = client.post(
            f"/api/v1/ai/studies/{study_id}/run",
            json={"job_type": "totalsegmentator", "tier": 1},
        )

        assert response.status_code in (401, 403)
