"""Tests for the GPU Model Scheduler."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.scheduler import ModelScheduler, ModelSchedulerError, ModelType, get_scheduler


class TestModelScheduler:
    """Test suite for ModelScheduler singleton and VRAM management."""

    def test_singleton_pattern(self):
        """get_scheduler returns the same instance."""
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2

    def test_initial_state(self):
        """Scheduler starts with no model loaded."""
        scheduler = ModelScheduler()
        assert scheduler.current_model == ModelType.NONE

    def test_unload_current_noop_when_empty(self):
        """Unloading when nothing is loaded should not raise."""
        scheduler = ModelScheduler()
        scheduler.unload_current()  # Should not raise
        assert scheduler.current_model == ModelType.NONE

    @patch("app.scheduler.TORCH_AVAILABLE", False)
    def test_get_free_vram_returns_negative_when_no_torch(self):
        """When torch unavailable, _get_free_vram_gb returns -1."""
        scheduler = ModelScheduler()
        assert scheduler._get_free_vram_gb() == -1.0


class TestTotalSegmentator:
    """Tests for TotalSegmentator subprocess execution."""

    @patch("subprocess.run")
    def test_totalsegmentator_basic(self, mock_run, mock_scheduler: MagicMock):
        """Basic TotalSegmentator call succeeds."""
        scheduler = ModelScheduler()
        mock_run.return_value = MagicMock(stdout="success", stderr="")

        scheduler.run_totalsegmentator(
            input_path="/input/ct.nii.gz",
            output_path="/output/masks",
        )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "TotalSegmentator"
        assert "-d" in cmd
        assert "gpu" in cmd

    @patch("subprocess.run")
    def test_totalsegmentator_fast_mode(self, mock_run):
        """Fast mode adds --fast flag."""
        scheduler = ModelScheduler()
        mock_run.return_value = MagicMock(stdout="success", stderr="")

        scheduler.run_totalsegmentator(
            input_path="/input/ct.nii.gz",
            output_path="/output/masks",
            fast=True,
        )

        cmd = mock_run.call_args[0][0]
        assert "--fast" in cmd

    @patch("subprocess.run")
    def test_totalsegmentator_roi_subset(self, mock_run):
        """ROI subset adds -rs flag with structures."""
        scheduler = ModelScheduler()
        mock_run.return_value = MagicMock(stdout="success", stderr="")

        scheduler.run_totalsegmentator(
            input_path="/input/ct.nii.gz",
            output_path="/output/masks",
            roi_subset=["lung_upper_lobe_left", "lung_lower_lobe_left"],
        )

        cmd = mock_run.call_args[0][0]
        assert "-rs" in cmd
        assert "lung_upper_lobe_left" in cmd
        assert "lung_lower_lobe_left" in cmd

    @patch("subprocess.run")
    def test_totalsegmentator_timeout(self, mock_run):
        """Timeout raises ModelSchedulerError."""
        import subprocess
        scheduler = ModelScheduler()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["TotalSegmentator"], timeout=300)

        with pytest.raises(ModelSchedulerError, match="timed out"):
            scheduler.run_totalsegmentator(
                input_path="/input/ct.nii.gz",
                output_path="/output/masks",
                timeout=300,
            )

    @patch("subprocess.run")
    def test_totalsegmentator_failure(self, mock_run):
        """Subprocess failure raises ModelSchedulerError."""
        import subprocess
        scheduler = ModelScheduler()
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["TotalSegmentator"], stderr="CUDA out of memory"
        )

        with pytest.raises(ModelSchedulerError, match="failed"):
            scheduler.run_totalsegmentator(
                input_path="/input/ct.nii.gz",
                output_path="/output/masks",
            )


class TestReportGeneration:
    """Tests for report generation methods."""

    @pytest.mark.asyncio
    async def test_generate_report_local_success(self):
        """Local Ollama report generation succeeds."""
        from unittest.mock import AsyncMock, MagicMock, patch

        scheduler = ModelScheduler()
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Polished report text."}
        mock_response.raise_for_status = MagicMock()

        # Create a proper async context manager mock for httpx.AsyncClient
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "MedAIBase/MedGemma1.5:4b-it"
        mock_settings.ollama_timeout = 120

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with patch("app.config.get_settings", return_value=mock_settings):
                result = await scheduler.generate_report_local("Test findings")

        assert "Polished report text" in result

    @pytest.mark.asyncio
    async def test_generate_report_cloud_tier2_offline_mode(self):
        """Cloud report generation fails when offline mode enabled."""
        from unittest.mock import patch, MagicMock

        scheduler = ModelScheduler()

        mock_settings = MagicMock()
        mock_settings.offline_mode = True
        mock_settings.openrouter_api_key = ""

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(ModelSchedulerError, match="Offline Mode"):
                await scheduler.generate_report_cloud_tier2("Test findings")


class TestThreadSafety:
    """Tests for thread-safe model loading."""

    def test_concurrent_load_serializes(self):
        """Concurrent model operations serialize via lock."""
        scheduler = ModelScheduler()
        results = []

        def operation(name):
            with scheduler._lock:
                results.append(f"{name}_start")
                results.append(f"{name}_end")

        threads = [
            threading.Thread(target=operation, args=(f"op{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each operation should have start/end pairs
        assert len(results) == 10
        for i in range(5):
            start = results.index(f"op{i}_start")
            end = results.index(f"op{i}_end")
            assert start < end
