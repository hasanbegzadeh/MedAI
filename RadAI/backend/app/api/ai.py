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
from app.ai.modality_registry import get_modality_registry, ModalityError
from app.config import get_settings

settings = get_settings()

router = APIRouter()


async def run_nodule_detection_from_study(job_id: UUID, study_id: UUID):
    """Run TotalSegmentator with lung ROI, then detect nodules (Refactored)."""
    from pathlib import Path
    import SimpleITK as sitk
    import structlog
    from app.db.models import Study
    from app.db.session import AsyncSessionLocal
    from app.scheduler import get_scheduler
    from app.websocket import manager
    from app.services.pacs_service import PACSService
    from app.services.findings_service import FindingsService
    from app.services.ai_pipeline import AIPipeline
    from app.services.subagent_orchestrator import SubagentStateLogger
    
    logger = structlog.get_logger(__name__)
    settings = get_settings()
    scheduler = get_scheduler()
    study_id_str = str(study_id)
    
    # Initialize subagent logger
    log_dir = Path(settings.temp_processing_dir) / "agent_logs"
    agent_log = SubagentStateLogger(log_dir, str(job_id))

    async def progress(pct: int):
        async with AsyncSessionLocal() as db:
            fs = FindingsService(db)
            await fs.update_job_status(job_id, status=None, progress_pct=pct)
        await manager.send_progress(study_id_str, job_type="nodule_detection", pct=pct)

    try:
        async with AsyncSessionLocal() as db:
            pacs = PACSService(settings)
            findings_svc = FindingsService(db)
            pipeline = AIPipeline(study_id, job_id, settings, pacs, findings_svc, progress)
            
            await pipeline.initialize()
            
            # Step 1: Fetch
            agent_log.log_step_start("fetch_data")
            study = await db.get(Study, study_id)
            if not study or not study.orthanc_id:
                raise ValueError("Study or Orthanc ID missing")
            await pipeline.fetch_data(study.orthanc_id)
            agent_log.log_step_complete("fetch_data", "DICOM series downloaded from Orthanc")
            
            # Step 2: Conversion
            agent_log.log_step_start("conversion")
            await progress(15)
            await pipeline.convert_to_nifti()
            agent_log.log_step_complete("conversion", "DICOM series converted to NIfTI volume")
            
            # Step 3: Segmentation
            agent_log.log_step_start("segmentation")
            await progress(25)
            scheduler.run_totalsegmentator(
                input_path=str(pipeline.nifti_path),
                output_path=str(pipeline.output_dir),
                roi_subset=[
                    "lung_upper_lobe_left", "lung_lower_lobe_left",
                    "lung_upper_lobe_right", "lung_middle_lobe_right",
                    "lung_lower_lobe_right"
                ],
                fast=True,
                progress_callback=lambda pct: progress(25 + int(pct * 0.5)),
            )
            agent_log.log_step_complete("segmentation", "TotalSegmentator lung lobe extraction complete")
            
            # Step 4: Detection
            agent_log.log_step_start("detection")
            await progress(80)
            candidates = await pipeline.detect_nodules_in_volume(pipeline.output_dir)
            agent_log.log_step_complete("detection", f"Detected {len(candidates)} nodule candidates")
            
            # Step 5: Persistence
            agent_log.log_step_start("persistence")
            await pipeline.persist_results(candidates)
            await manager.send_complete(
                study_id_str,
                job_type="nodule_detection",
                result_summary=f"Found {len(candidates)} nodule candidate(s)",
            )
            agent_log.log_step_complete("persistence", "Findings saved to database")
            agent_log.finalize()

    except Exception as exc:
        logger.error("Nodule detection pipeline failed", study_id=study_id, error=str(exc))
        agent_log.log_error("pipeline", str(exc))
        async with AsyncSessionLocal() as db:
            fs = FindingsService(db)
            await fs.update_job_status(job_id, status="failed", error_message=str(exc))
        await manager.send_error(study_id_str, job_type="nodule_detection", error=str(exc))
    finally:
        await pipeline.cleanup()


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

    # Resolve active model version for this job type
    from app.ai.model_registry import ModelRegistryService
    registry_svc = ModelRegistryService(db)
    active_version = await registry_svc.resolve_version_for_job(body.job_type)

    job = AIJob(
        study_id=study_id,
        job_type=body.job_type,
        tier=body.tier,
        model_name="TotalSegmentator"
        if body.job_type == "totalsegmentator"
        else body.job_type,
        model_version_id=active_version.id if active_version else None,
        status="queued",
    )
    db.add(job)
    study.ai_status = "queued"
    await db.commit()
    await db.refresh(job)

    if body.job_type == "totalsegmentator":
        if body.tier == 3:
            # Cloud GPU (Tier 3) — full-resolution TotalSegmentator
            from app.ai.totalsegmentator import run_totalsegmentator_cloud_job
            background_tasks.add_task(
                run_totalsegmentator_cloud_job, job.id, study_id, body.roi_subset
            )
        else:
            # Local GPU (Tier 1) — fast mode
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


# ─── Multi-Modality Endpoints ─────────────────────────────────────────────────

class ModalityOut(BaseModel):
    code: str
    name: str
    body_parts: list[str]
    available_models: int
    report_templates: int


class ModalityModelOut(BaseModel):
    name: str
    description: str
    vram_gb: float
    tier: int
    status: str


@router.get(
    "/modalities",
    response_model=list[ModalityOut],
    summary="List supported imaging modalities",
)
async def list_modalities(
    _: User = Depends(get_current_user),
) -> list[ModalityOut]:
    """Return all supported imaging modalities and their capabilities."""
    registry = get_modality_registry()
    result = []

    for code in registry.get_supported_modalities():
        modality = registry.get_modality(code)
        models = registry.get_available_models(code)
        templates = registry.get_report_templates(code)

        result.append(
            ModalityOut(
                code=code,
                name=modality.name,
                body_parts=modality.body_parts,
                available_models=len(models),
                report_templates=len(templates),
            )
        )

    return result


@router.get(
    "/modalities/{dicom_code}/models",
    response_model=list[ModalityModelOut],
    summary="List available AI models for a modality",
)
async def get_modality_models(
    dicom_code: str,
    _: User = Depends(get_current_user),
) -> list[ModalityModelOut]:
    """Return available AI models for the specified modality."""
    registry = get_modality_registry()
    try:
        models = registry.get_available_models(dicom_code)
        return [ModalityModelOut(**m) for m in models]
    except ModalityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/studies/{study_id}/recommend-ai",
    summary="Recommend AI analyses for a study based on modality and body part",
)
async def recommend_ai_for_study(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Suggest appropriate AI models based on the study's modality and body part."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    registry = get_modality_registry()

    try:
        modality = registry.get_modality(study.modality)
        recommended_template = registry.recommend_template(
            study.modality, study.body_part
        )
        available_models = registry.get_available_models(study.modality)

        return {
            "study_id": str(study_id),
            "modality": modality.name,
            "body_part": study.body_part,
            "recommended_template": recommended_template,
            "available_models": available_models,
            "processing_requirements": modality.processing_requirements,
        }
    except ModalityError:
        return {
            "study_id": str(study_id),
            "modality": study.modality,
            "message": f"Modality '{study.modality}' not yet supported for AI analysis",
            "available_models": [],
        }
