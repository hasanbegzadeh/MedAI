"""RadAI — Cloud GPU client for RunPod/Vast.ai integration.

Handles communication with remote GPU servers for heavy AI workloads
that exceed local VRAM capacity (e.g., full-resolution TotalSegmentator,
MedSAM2).

Usage::

    client = CloudGPUClient()
    result = await client.run_totalsegmentator(
        nifti_file="/path/ct.nii.gz",
        full_res=True,
    )
"""

from __future__ import annotations

import io
import json
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


class CloudGPUError(Exception):
    """Raised when cloud GPU job fails."""


class CloudProvider(str, Enum):
    """Supported cloud GPU providers."""
    RUNPOD = "runpod"
    VASTAI = "vastai"


class CloudGPUClient:
    """Client for cloud GPU inference services (RunPod, Vast.ai, etc.).

    Supports two deployment patterns:
    1. RunPod Serverless — HTTP endpoint with JSON payload
    2. Vast.ai REST API — submit job to available GPU instances

    The cloud server runs a TotalSegmentator instance that accepts
    NIfTI files and returns segmentation masks as ZIP archives.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.cloud_gpu_url.rstrip("/")
        self._api_key = settings.cloud_gpu_api_key

    def _is_configured(self) -> bool:
        """Return True if cloud GPU is properly configured."""
        return bool(self._base_url and self._api_key)

    async def run_totalsegmentator(
        self,
        nifti_path: str,
        full_res: bool = True,
        roi_subset: list[str] | None = None,
        timeout: int = 600,
        progress_callback: Any = None,
    ) -> dict:
        """Run TotalSegmentator on cloud GPU.

        Uploads NIfTI file, triggers inference, downloads results.

        Args:
            nifti_path: Path to input NIfTI file.
            full_res: Use full resolution (12+ GB VRAM, cloud-only).
            roi_subset: Optional list of structures to segment.
            timeout: Maximum wait time in seconds.
            progress_callback: Optional async callback(pct: int).

        Returns:
            Dict with output_path and job metadata.

        Raises:
            CloudGPUError: On upload, inference, or download failure.
        """
        if not self._is_configured():
            raise CloudGPUError(
                "Cloud GPU not configured. Set CLOUD_GPU_URL and CLOUD_GPU_API_KEY."
            )

        if progress_callback:
            await progress_callback(10)

        # Step 1: Upload NIfTI file
        logger.info("Uploading NIfTI to cloud GPU", path=nifti_path)
        nifti_data = Path(nifti_path).read_bytes()

        async with httpx.AsyncClient(timeout=timeout) as client:
            upload_resp = await client.post(
                f"{self._base_url}/upload",
                files={"file": ("ct.nii.gz", io.BytesIO(nifti_data), "application/gzip")},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )

            if upload_resp.status_code != 200:
                raise CloudGPUError(f"Upload failed: {upload_resp.status_code} {upload_resp.text}")

            upload_result = upload_resp.json()
            file_id = upload_result["file_id"]

        if progress_callback:
            result = progress_callback(30)
            if hasattr(result, "__await__"):
                await result

        # Step 2: Trigger inference
        logger.info("Starting cloud TotalSegmentator inference", file_id=file_id)
        payload: dict[str, Any] = {
            "file_id": file_id,
            "model": "totalsegmentator",
            "full_res": full_res,
        }
        if roi_subset:
            payload["roi_subset"] = roi_subset

        async with httpx.AsyncClient(timeout=timeout) as client:
            infer_resp = await client.post(
                f"{self._base_url}/infer",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )

            if infer_resp.status_code != 202:
                raise CloudGPUError(
                    f"Inference start failed: {infer_resp.status_code} {infer_resp.text}"
                )

            job_id = infer_resp.json()["job_id"]

        if progress_callback:
            result = progress_callback(40)
            if hasattr(result, "__await__"):
                await result

        # Step 3: Poll for completion
        result = await self._poll_job(job_id, timeout=timeout, progress_callback=progress_callback)

        if progress_callback:
            result = progress_callback(100)
            if hasattr(result, "__await__"):
                await result

        logger.info("Cloud TotalSegmentator complete", job_id=job_id)
        return result

    async def _poll_job(
        self,
        job_id: str,
        timeout: int = 600,
        progress_callback: Any = None,
    ) -> dict:
        """Poll cloud GPU job until completion.

        Args:
            job_id: Cloud job identifier.
            timeout: Max wait time in seconds.
            progress_callback: Optional async callback(pct: int).

        Returns:
            Job result dict.

        Raises:
            CloudGPUError: On job failure or timeout.
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()
        poll_interval = 5  # seconds

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise CloudGPUError(f"Cloud GPU job timed out after {timeout}s")

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self._base_url}/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )

                if resp.status_code != 200:
                    raise CloudGPUError(f"Status check failed: {resp.status_code}")

                job_status = resp.json()

            status = job_status.get("status", "unknown")

            if status == "completed":
                # Download results
                return await self._download_results(job_id)
            elif status == "failed":
                raise CloudGPUError(
                    f"Cloud GPU job failed: {job_status.get('error', 'Unknown error')}"
                )
            elif status in ("running", "queued"):
                pct = job_status.get("progress", 50)
                if progress_callback:
                    await progress_callback(40 + int(pct * 0.5))
                await asyncio.sleep(poll_interval)
            else:
                raise CloudGPUError(f"Unknown job status: {status}")

    async def _download_results(self, job_id: str) -> dict:
        """Download segmentation results from cloud GPU.

        Args:
            job_id: Completed job ID.

        Returns:
            Dict with local path to downloaded results.

        Raises:
            CloudGPUError: On download failure.
        """
        import tempfile
        import zipfile

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(
                f"{self._base_url}/jobs/{job_id}/download",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )

            if resp.status_code != 200:
                raise CloudGPUError(f"Download failed: {resp.status_code}")

            # Save to temp directory
            tmpdir = tempfile.mkdtemp(prefix="radai-cloud-")
            zip_path = Path(tmpdir) / "results.zip"
            zip_path.write_bytes(resp.content)

            # Extract
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)

        logger.info("Cloud results downloaded", path=tmpdir)
        return {"output_path": tmpdir, "job_id": job_id}

    async def test_connection(self) -> dict:
        """Test connectivity to cloud GPU server.

        Returns:
            Dict with status and server info.

        Raises:
            CloudGPUError: On connection failure.
        """
        if not self._is_configured():
            raise CloudGPUError("Cloud GPU not configured")

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base_url}/health",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )

            if resp.status_code != 200:
                raise CloudGPUError(f"Health check failed: {resp.status_code}")

            return resp.json()


# ─── Singleton ────────────────────────────────────────────────────────────────
_client: CloudGPUClient | None = None


def get_cloud_gpu_client() -> CloudGPUClient:
    """Return the process-wide CloudGPUClient singleton."""
    global _client
    if _client is None:
        _client = CloudGPUClient()
    return _client
