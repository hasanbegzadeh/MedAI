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
from app.config import get_settings

settings = get_settings()

router = APIRouter()


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
    request: RunAIRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AIJob:
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    job = AIJob(
        study_id=study_id,
        job_type=request.job_type,
        tier=request.tier,
        model_name="TotalSegmentator"
        if request.job_type == "totalsegmentator"
        else request.job_type,
        status="queued",
    )
    db.add(job)
    study.ai_status = "queued"
    await db.commit()
    await db.refresh(job)

    if request.job_type == "totalsegmentator":
        background_tasks.add_task(run_totalsegmentator_job, job.id, study_id, request.roi_subset, request.fast)
    elif request.job_type == "nninteractive":
        background_tasks.add_task(run_nninteractive_job, job.id, study_id, request.clicks)

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
