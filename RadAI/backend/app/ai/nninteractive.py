"""RadAI — nnInteractive integration for interactive refinement."""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIJob, Study
from app.db.session import AsyncSessionLocal
from app.scheduler import get_scheduler, ModelSchedulerError
from app.websocket import manager
from app.dicom.converter import dicom_series_to_nifti, nifti_to_dicom_seg
from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

async def run_nninteractive_job(
    job_id: UUID, 
    study_id: UUID, 
    clicks: list[dict] | None = None,
    # In Phase 1, we might just handle a single refinement step
):
    """Run nnInteractive refinement step in the background."""
    scheduler = get_scheduler()
    study_id_str = str(study_id)

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.progress_pct = pct
                await db.commit()
        await manager.send_progress(study_id_str, job_type="nninteractive", pct=pct)

    try:
        temp_base = Path("/tmp/radai-processing")
        temp_base.mkdir(parents=True, exist_ok=True)
        
        dicom_dir = temp_base / f"{study_id}_dicom"
        dicom_dir.mkdir(parents=True, exist_ok=True)
        input_nifti = temp_base / f"{study_id}.nii.gz"
        output_seg_file = temp_base / f"{study_id}_nn_seg.dcm"

        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            orthanc_id = study.orthanc_id if study else None

        if not orthanc_id:
            raise ModelSchedulerError("Study not found in database or Orthanc ID missing")

        # 1. Download DICOM and convert to NIfTI (if not already cached)
        await progress(10)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}", 
                auth=(settings.orthanc_user, settings.orthanc_password)
            )
            resp.raise_for_status()
            series_id = resp.json().get("Series", [])[0]
            
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances", 
                auth=(settings.orthanc_user, settings.orthanc_password)
            )
            resp.raise_for_status()
            for inst in resp.json():
                inst_id = inst["ID"]
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst_id}/file", 
                    auth=(settings.orthanc_user, settings.orthanc_password)
                )
                with open(dicom_dir / f"{inst_id}.dcm", "wb") as f:
                    f.write(inst_resp.content)

        dicom_series_to_nifti(dicom_dir, input_nifti)

        # 2. Load nnInteractive (unloads any previous model)
        await progress(30)
        session = scheduler.load_nninteractive()
        
        # 3. Apply clicks / refinement (Simulation for Phase 1 prototype)
        await progress(50)
        # Note: In a real implementation, 'session' would be used with the NIfTI data
        # mask = session.predict(input_nifti, clicks)
        # For now, we simulate a successful segmentation
        logger.info("nnInteractive refinement simulated", study_id=study_id, clicks_count=len(clicks or []))

        # 4. Export DICOM-SEG
        await progress(80)
        # Simulation: assuming a mask was generated. For now we just use a placeholder result
        # In Phase 1, this would be a real NIfTI mask created by nnInteractive
        placeholder_mask = input_nifti # Placeholder
        nifti_to_dicom_seg(placeholder_mask, dicom_dir, output_seg_file, structure_name="Refined Leak")

        # 5. Upload back to Orthanc
        await progress(90)
        if output_seg_file.exists():
            async with httpx.AsyncClient(timeout=30) as client:
                with open(output_seg_file, "rb") as f:
                    resp = await client.post(
                        f"{settings.orthanc_url}/instances",
                        content=f.read(),
                        auth=(settings.orthanc_user, settings.orthanc_password)
                    )
                    resp.raise_for_status()

        # Update Job
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.completed_at = datetime.datetime.now(datetime.UTC)
                await db.commit()

        await manager.send_complete(study_id_str, job_type="nninteractive", result_summary="Refinement complete")

    except Exception as exc:
        logger.error("nnInteractive job failed", study_id=study_id, error=str(exc))
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                await db.commit()
    finally:
        shutil.rmtree(dicom_dir, ignore_errors=True)
        input_nifti.unlink(missing_ok=True)
        output_seg_file.unlink(missing_ok=True)
