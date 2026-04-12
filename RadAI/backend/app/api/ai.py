"""RadAI — AI inference API router."""

# NOTE: do NOT add `from __future__ import annotations` here. The slowapi
# `@limiter.limit` decorator wraps the endpoint and replaces its __globals__
# with slowapi's own module globals. Combined with PEP 563 stringified
# annotations, FastAPI/pydantic cannot then resolve `UUID` (or any other
# module-level import) when building the request model, and blows up at
# import time with `NameError: name 'UUID' is not defined`.

import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.rate_limiter import limiter
from app.db.models import AIJob, Study, User
from app.db.session import get_db
from app.ai.totalsegmentator import run_totalsegmentator_job
from app.ai.nninteractive import run_nninteractive_job
from app.ai.nodule_detection import run_nodule_detection_job
from app.config import get_settings

settings = get_settings()

router = APIRouter()


async def run_nodule_detection_from_study(job_id: UUID, study_id: UUID):
    """Run TotalSegmentator with lung ROI, then detect nodules.

    This is a composite job: first segment lungs, then find nodules
    within the lung masks.
    """
    import datetime
    import shutil
    from pathlib import Path

    import httpx
    import numpy as np
    import structlog
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import AIJob, Study
    from app.db.session import AsyncSessionLocal
    from app.scheduler import get_scheduler, ModelSchedulerError
    from app.websocket import manager
    from app.dicom.converter import dicom_series_to_nifti
    from app.ai.nodule_detection import detect_nodules
    from app.config import get_settings

    logger = structlog.get_logger(__name__)
    settings = get_settings()
    scheduler = get_scheduler()
    study_id_str = str(study_id)

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.progress_pct = pct
                await db.commit()
        await manager.send_progress(study_id_str, job_type="nodule_detection", pct=pct)

    try:
        temp_base = Path("/tmp/radai-processing")
        temp_base.mkdir(parents=True, exist_ok=True)

        dicom_dir = temp_base / f"{study_id}_nodule_dicom"
        dicom_dir.mkdir(parents=True, exist_ok=True)
        ct_nifti = temp_base / f"{study_id}_ct.nii.gz"
        lung_mask_dir = temp_base / f"{study_id}_lung_mask"

        # Get study orthanc_id
        async with AsyncSessionLocal() as db:
            study = await db.get(Study, study_id)
            orthanc_id = study.orthanc_id if study else None

        if not orthanc_id:
            raise ModelSchedulerError("Study not found or Orthanc ID missing")

        # 1. Download DICOM from Orthanc
        await progress(5)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{orthanc_id}",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])
            if not series_ids:
                raise ModelSchedulerError("No series found in Orthanc study")

            series_id = series_ids[0]
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            for inst in resp.json():
                inst_id = inst["ID"]
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst_id}/file",
                    auth=(settings.orthanc_user, settings.orthanc_password),
                )
                with open(dicom_dir / f"{inst_id}.dcm", "wb") as f:
                    f.write(inst_resp.content)

        # 2. DICOM → NIfTI
        await progress(15)
        dicom_series_to_nifti(dicom_dir, ct_nifti)

        # 3. Run TotalSegmentator with lung ROI only
        await progress(25)
        scheduler.run_totalsegmentator(
            input_path=str(ct_nifti),
            output_path=str(lung_mask_dir),
            roi_subset=["lung_upper_lobe_left", "lung_lower_lobe_left",
                        "lung_upper_lobe_right", "lung_middle_lobe_right",
                        "lung_lower_lobe_right"],
            fast=True,
            timeout=600,
            progress_callback=lambda pct: progress(25 + int(pct * 0.5)),
        )

        # 4. Load CT and lung masks, run nodule detection
        await progress(80)
        import SimpleITK as sitk

        ct_image = sitk.ReadImage(str(ct_nifti))
        ct_volume = sitk.GetArrayFromImage(ct_image)

        # Build combined lung mask from TotalSegmentator output files
        spacing = ct_image.GetSpacing()
        spacing_mm = (spacing[2], spacing[1], spacing[0])

        # Find all mask files and combine into lung mask
        mask_files = list(lung_mask_dir.glob("*.nii.gz"))
        if not mask_files:
            raise ModelSchedulerError("No lung masks found after TotalSegmentator")

        # Start with zeros
        lung_mask = np.zeros(ct_volume.shape, dtype=np.int32)
        label = 1
        for mf in mask_files:
            mask_img = sitk.ReadImage(str(mf))
            mask_arr = sitk.GetArrayFromImage(mask_img)
            lung_mask[mask_arr > 0] = label
            label += 1

        from app.ai.nodule_detection import detect_nodules
        candidates = detect_nodules(ct_volume, lung_mask, spacing_mm)

        # Store results
        results = {
            "total_candidates": len(candidates),
            "candidates": [
                {
                    "nodule_id": c.nodule_id,
                    "location": c.location,
                    "laterality": c.laterality,
                    "lobe": c.lobe,
                    "diameter_mm": c.diameter_mm,
                    "volume_mm3": c.volume_mm3,
                    "mean_hu": c.mean_hu,
                    "confidence": c.confidence,
                }
                for c in candidates
            ],
        }

        # Update job
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "completed"
                job.progress_pct = 100
                job.result_json = results
                job.completed_at = datetime.datetime.now(datetime.UTC)
                await db.commit()

        await manager.send_complete(
            study_id_str,
            job_type="nodule_detection",
            result_summary=f"Found {len(candidates)} nodule candidate(s)",
        )

    except Exception as exc:
        logger.error("Nodule detection job failed", study_id=study_id, error=str(exc))
        async with AsyncSessionLocal() as db:
            job = await db.get(AIJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                await db.commit()
        await manager.send_error(
            study_id_str, job_type="nodule_detection", error=str(exc)
        )
    finally:
        shutil.rmtree(dicom_dir, ignore_errors=True)
        shutil.rmtree(lung_mask_dir, ignore_errors=True)
        ct_nifti.unlink(missing_ok=True)


class AIJobOut(BaseModel):
    id: UUID
    study_id: UUID
    job_type: str
    status: str
    tier: int
    model_name: str | None
    progress_pct: int

    model_config = {"from_attributes": True}


class RunAIRequest(BaseModel):
    job_type: Literal[
        "totalsegmentator", "nninteractive", "nodule_detection", "report_polish", "medsam2"
    ]
    tier: int = 1
    roi_subset: list[str] | None = None
    fast: bool = True
    clicks: list[dict] | None = None  # Added for interactive segmentation
# Background logic moved to app.ai.* modules


@router.post(
    "/studies/{study_id}/run",
    response_model=AIJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger AI analysis on a study",
)
@limiter.limit("5/minute")
async def run_ai(
    study_id: UUID,
    # NOTE: slowapi's @limiter.limit looks up a parameter literally named
    # `request` and asserts it is a starlette Request. Do NOT name the body
    # model `request` — keep that name reserved for the Request injection.
    request: Request,
    body: RunAIRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AIJob:
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    job = AIJob(
        study_id=study_id,
        job_type=body.job_type,
        tier=body.tier,
        model_name="TotalSegmentator"
        if body.job_type == "totalsegmentator"
        else body.job_type,
        status="queued",
    )
    db.add(job)
    study.ai_status = "queued"
    await db.commit()
    await db.refresh(job)

    if body.job_type == "totalsegmentator":
        background_tasks.add_task(
            run_totalsegmentator_job, job.id, study_id, body.roi_subset, body.fast
        )
    elif body.job_type == "nninteractive":
        background_tasks.add_task(run_nninteractive_job, job.id, study_id, body.clicks)
    elif body.job_type == "nodule_detection":
        background_tasks.add_task(
            run_nodule_detection_from_study, job.id, study_id
        )

    return job


@router.get(
    "/jobs/{job_id}",
    response_model=AIJobOut,
    summary="Get status of an AI job",
)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AIJob:
    job = await db.get(AIJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
