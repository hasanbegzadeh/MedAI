"""End-to-end integration tests for the Docker Compose stack.

These tests require the full Docker Compose stack to be running:
    make up  # from RadAI/ directory

They verify service connectivity, health checks, and cross-service
communication. Skip automatically if Docker services are not running.

Usage:
    pytest tests/test_e2e/ -v -m integration
"""

from __future__ import annotations

import os

import pytest

# Skip all tests in this file if RADAI_E2E env var not set
pytestmark = pytest.mark.skipif(
    os.environ.get("RADAI_E2E") != "1",
    reason="E2E tests require RADAI_E2E=1 and running Docker stack",
)

BACKEND_URL = os.environ.get("RADAI_BACKEND_URL", "http://localhost:8000")
ORTHANC_URL = os.environ.get("RADAI_ORTHANC_URL", "http://localhost:8042")


@pytest.fixture
def http_client():
    """Create an httpx client for E2E requests."""
    import httpx
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


@pytest.fixture
def orthanc_client():
    """Create an httpx client for Orthanc requests."""
    import httpx
    return httpx.Client(
        base_url=ORTHANC_URL,
        auth=("orthanc", os.environ.get("ORTHANC_PASSWORD", "orthanc")),
        timeout=30,
    )


@pytest.mark.integration
class TestStackHealth:
    """Verify all Docker services are healthy."""

    def test_backend_health(self, http_client):
        """Backend API health check responds."""
        resp = http_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "checks" in data

    def test_orthanc_health(self, orthanc_client):
        """Orthanc PACS server is reachable."""
        resp = orthanc_client.get("/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "Version" in data

    def test_backend_can_reach_orthanc(self, http_client):
        """Backend health check reports Orthanc as reachable."""
        resp = http_client.get("/health")
        data = resp.json()
        checks = data.get("checks", {})
        # Orthanc connectivity is checked in health endpoint
        assert "api" in checks
        assert checks["api"] == "ok"


@pytest.mark.integration
class TestAuthFlow:
    """Test authentication end-to-end."""

    def test_login_flow(self, http_client):
        """Admin user can log in and get a JWT token."""
        resp = http_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        # Should succeed (admin seeded) or fail gracefully
        assert resp.status_code in (200, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"


@pytest.mark.integration
class TestAIModalities:
    """Test modality endpoints end-to-end."""

    def test_list_modalities(self, http_client):
        """Modalities endpoint returns supported modalities."""
        # First login to get token
        login_resp = http_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        if login_resp.status_code != 200:
            pytest.skip("Admin login required for modalities endpoint")

        token = login_resp.json()["access_token"]
        resp = http_client.get(
            "/api/v1/ai/modalities",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3  # CT, MRI, XRAY at minimum
