"""Tests for the Cloud GPU client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cloud.gpu_client import (
    CloudGPUClient,
    CloudGPUError,
    CloudProvider,
    get_cloud_gpu_client,
)


class TestCloudGPUClient:
    """Tests for cloud GPU client operations."""

    def test_provider_enum(self):
        """CloudProvider has expected values."""
        assert CloudProvider.RUNPOD.value == "runpod"
        assert CloudProvider.VASTAI.value == "vastai"

    def test_not_configured_raises(self):
        """Client raises when not configured."""
        mock_settings = MagicMock()
        mock_settings.cloud_gpu_url = ""
        mock_settings.cloud_gpu_api_key = ""

        with patch("app.cloud.gpu_client.get_settings", return_value=mock_settings):
            client = CloudGPUClient()
            assert not client._is_configured()

    def test_configured_when_url_and_key_set(self):
        """Client reports configured when both URL and key are set."""
        mock_settings = MagicMock()
        mock_settings.cloud_gpu_url = "https://gpu.example.com"
        mock_settings.cloud_gpu_api_key = "test-key"

        with patch("app.cloud.gpu_client.get_settings", return_value=mock_settings):
            client = CloudGPUClient()
            assert client._is_configured()

    @pytest.mark.asyncio
    async def test_run_totalsegmentator_unconfigured_raises(self):
        """Running inference on unconfigured client raises CloudGPUError."""
        mock_settings = MagicMock()
        mock_settings.cloud_gpu_url = ""
        mock_settings.cloud_gpu_api_key = ""

        with patch("app.cloud.gpu_client.get_settings", return_value=mock_settings):
            client = CloudGPUClient()
            with pytest.raises(CloudGPUError, match="not configured"):
                await client.run_totalsegmentator("/fake/path.nii.gz")

    @pytest.mark.asyncio
    async def test_test_connection_unconfigured_raises(self):
        """Health check on unconfigured client raises CloudGPUError."""
        mock_settings = MagicMock()
        mock_settings.cloud_gpu_url = ""
        mock_settings.cloud_gpu_api_key = ""

        with patch("app.cloud.gpu_client.get_settings", return_value=mock_settings):
            client = CloudGPUClient()
            with pytest.raises(CloudGPUError, match="not configured"):
                await client.test_connection()

    def test_singleton_pattern(self):
        """get_cloud_gpu_client returns same instance."""
        # Reset singleton for test
        import app.cloud.gpu_client as mod
        mod._client = None

        mock_settings = MagicMock()
        mock_settings.cloud_gpu_url = ""
        mock_settings.cloud_gpu_api_key = ""

        with patch("app.cloud.gpu_client.get_settings", return_value=mock_settings):
            c1 = get_cloud_gpu_client()
            c2 = get_cloud_gpu_client()
            assert c1 is c2

        # Clean up
        mod._client = None
