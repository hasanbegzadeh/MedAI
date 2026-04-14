"""RadAI — Cloud Processing Pipeline.

End-to-end pipeline for cloud GPU processing:
  1. Download DICOM from Orthanc
  2. Anonymize all PHI tags
  3. Convert to NIfTI
  4. Upload anonymized NIfTI to cloud GPU
  5. Run model (TotalSegmentator full, etc.)
  6. Download results
  7. Map back to original study UIDs
  8. Store DICOM-SEG + findings in Orthanc/DB

This pipeline NEVER sends identifiable patient data to the cloud.
"""
from __future__ import annotations

import datetime
import shutil
import uuid
from pathlib import Path
from uuid import UUID

import httpx
import structlog

from app.cloud.gpu_client import CloudGPUClient, CloudGPUError
from app.config import get_settings
from app.db.models import AIJob, Finding, Study
from app.db.session import AsyncSessionLocal
from app.dicom.anonymizer import DICOMAnonymizer
from app.dicom.converter import dicom_series_to_nifti
from app.websocket import manager

logger = structlog.get_logger(__name__)


class CloudPipelineError(Exception):
    """Raised on cloud pipeline failures."""


async def run_cloud_segmentation(
    job_id: UUID,
    study_id: UUID,
    job_type: str = "totalsegmentator_full",
    params: dict | None = None,
) -> None:
    """Full cloud segmentation pipeline for a study.

    Called as a BackgroundTask from the AI router.
    """
    settings = get_settings()
    study_id_str = str(study_id)

    if not settings.cloud_gpu_url or not settings.cloud_gpu_api_key:
        await _fail_job(job_id, "Cloud GPU not configured (CLOUD_GPU_URL / CLOUD_GPU_API_KEY)")
        return

    temp_base = Path(settings.temp_processing_dir) / f"cloud_{study_id}"
    dicom_dir = temp_base / "dicom_original"
    anon_dir = temp_base / "dicom_anonymized"
    nifti_path = temp_base / "anonymized.nii.gz"
    result_dir = temp_base / "results"

    try:
        # ─── 1. Get study from DB ──────────────────────────────────
        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            if not study:
                raise CloudPipelineError("Study not found")
            orthanc_id = study.orthanc_id

        await _progress(job_id, study_id_str, 5, "Downloading from Orthanc")

        # ─── 2. Download DICOM from Orthanc ────────────────────────
        dicom_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])

            if not series_ids:
                raise CloudPipelineError("No series in study")

            # Download first CT series
            series_id = series_ids[0]
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()

            for inst in resp.json():
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst['ID']}/file",
                    auth=(settings.orthanc_user, settings.orthanc_password),
                )
                with open(dicom_dir / f"{inst['ID']}.dcm", "wb") as f:
                    f.write(inst_resp.content)

        await _progress(job_id, study_id_str, 15, "Anonymizing DICOM")

        # ─── 3. Anonymize ──────────────────────────────────────────
        anonymizer = DICOMAnonymizer()
        anonymizer.anonymize_directory(dicom_dir, anon_dir)
        logger.info("DICOM anonymized for cloud upload")

        await _progress(job_id, study_id_str, 25, "Converting to NIfTI")

        # ─── 4. Convert to NIfTI ──────────────────────────────────
        dicom_series_to_nifti(anon_dir, nifti_path)

        await _progress(job_id, study_id_str, 30, "Uploading to cloud GPU")

        # ─── 5. Submit to cloud GPU ───────────────────────────────
        cloud_client = CloudGPUClient()

        result_dir.mkdir(parents=True, exist_ok=True)
        result = await cloud_client.run_totalsegmentator(
            nifti_path=str(nifti_path),
            full_res=True,
            roi_subset=params.get("roi_subset") if params else None,
            timeout=600,
            progress_callback=lambda pct: _progress(
                job_id, study_id_str, 30 + int(pct * 0.55), "Cloud inference"
            ),
        )

        await _progress(job_id, study_id_str, 85, "Processing results")

        # ─── 6. Store results ─────────────────────────────────────
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.completed_at = datetime.datetime.now(datetime.UTC)
                job.result_json = {
                    "cloud_provider": "runpod",
                    "job_type": job_type,
                    "findings": result.get("findings", []),
                    "segments_count": result.get("segments_count", 0),
                }

                # Persist findings if returned by cloud
                for f_data in result.get("findings", []):
                    finding = Finding(
                        study_id=study_id,
                        ai_job_id=job_id,
                        finding_type=f_data.get("type", "unknown"),
                        location=f_data.get("location"),
                        laterality=f_data.get("laterality"),
                        measurements=f_data.get("measurements"),
                        characteristics=f_data.get("characteristics", []),
                        confidence=f_data.get("confidence"),
                        status="pending",
                    )
                    db.add(finding)

                await db.commit()

        await manager.send_complete(
            study_id_str,
            job_type=job_type,
            result_summary=f"Cloud {job_type} completed",
        )

    except (CloudGPUError, CloudPipelineError) as exc:
        logger.error("Cloud pipeline failed", error=str(exc), study_id=study_id_str)
        await _fail_job(job_id, str(exc))
        await manager.send_error(study_id_str, job_type=job_type, error=str(exc))

    except Exception as exc:
        logger.error("Unexpected cloud pipeline error", error=str(exc), study_id=study_id_str)
        await _fail_job(job_id, f"Unexpected error: {exc}")
        await manager.send_error(study_id_str, job_type=job_type, error=str(exc))

    finally:
        shutil.rmtree(temp_base, ignore_errors=True)


async def _progress(job_id: UUID, study_id_str: str, pct: int, message: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(AIJob, job_id)
        if job:
            job.progress_pct = pct
            await db.commit()
    await manager.send_progress(study_id_str, job_type="cloud", pct=pct)
    logger.info("Cloud pipeline progress", pct=pct, message=message)


async def _fail_job(job_id: UUID, error: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(AIJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = error
            await db.commit()
