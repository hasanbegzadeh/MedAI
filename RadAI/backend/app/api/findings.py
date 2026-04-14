"""RadAI — Findings API router.

CRUD endpoints for managing AI-detected findings. Radiologists can
accept, reject, or modify findings before report generation.
"""

# NOTE: do NOT add `from __future__ import annotations` here. See app/api/ai.py
# for the full explanation — slowapi's @limiter.limit decorator requires
# non-stringified annotations for FastAPI schema resolution.

import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.rate_limiter import limiter
from app.db.models import Finding, Study, User
from app.db.session import get_db

router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────────────────────

class FindingOut(BaseModel):
    id: UUID
    study_id: UUID
    ai_job_id: UUID | None
    finding_type: str
    location: str | None
    laterality: str | None
    measurements: dict | None
    characteristics: list[str] | None
    confidence: float | None
    lung_rads_category: str | None
    status: str
    radiologist_notes: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime.datetime | None
    created_at: datetime.datetime | None

    model_config = {"from_attributes": True}


class PaginatedFindings(BaseModel):
    items: list[FindingOut]
    total: int


class UpdateFindingRequest(BaseModel):
    status: str | None = None  # "accepted", "rejected", "modified"
    radiologist_notes: str | None = None
    measurements: dict | None = None
    characteristics: list[str] | None = None
    lung_rads_category: str | None = None


class CreateFindingRequest(BaseModel):
    finding_type: str
    location: str | None = None
    laterality: str | None = None
    measurements: dict | None = None
    characteristics: list[str] | None = None
    confidence: float | None = None
    lung_rads_category: str | None = None
    radiologist_notes: str | None = None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/studies/{study_id}",
    response_model=PaginatedFindings,
    summary="List all findings for a study",
)
async def list_findings(
    study_id: UUID,
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedFindings:
    query = select(Finding).where(Finding.study_id == study_id)
    count_query = select(func.count()).where(Finding.study_id == study_id)

    if status_filter:
        query = query.where(Finding.status == status_filter)
        count_query = count_query.where(Finding.status == status_filter)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    result = await db.execute(query.order_by(Finding.created_at))
    findings = list(result.scalars().all())

    return PaginatedFindings(
        items=[FindingOut.model_validate(f) for f in findings],
        total=total,
    )


@router.get(
    "/{finding_id}",
    response_model=FindingOut,
    summary="Get a single finding by ID",
)
async def get_finding(
    finding_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Finding:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.put(
    "/{finding_id}",
    response_model=FindingOut,
    summary="Update a finding (accept/reject/modify)",
)
@limiter.limit("30/minute")
async def update_finding(
    finding_id: UUID,
    request: Request,
    body: UpdateFindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Finding:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if body.status is not None:
        valid_statuses = {"pending", "accepted", "rejected", "modified"}
        if body.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
            )
        finding.status = body.status
        finding.reviewed_by = current_user.id
        finding.reviewed_at = datetime.datetime.now(datetime.UTC)

    if body.radiologist_notes is not None:
        finding.radiologist_notes = body.radiologist_notes

    if body.measurements is not None:
        finding.measurements = body.measurements

    if body.characteristics is not None:
        finding.characteristics = body.characteristics

    if body.lung_rads_category is not None:
        finding.lung_rads_category = body.lung_rads_category

    await db.commit()
    await db.refresh(finding)
    return finding


@router.post(
    "/studies/{study_id}",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a finding to a study",
)
@limiter.limit("10/minute")
async def create_finding(
    study_id: UUID,
    request: Request,
    body: CreateFindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Finding:
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    finding = Finding(
        study_id=study_id,
        finding_type=body.finding_type,
        location=body.location,
        laterality=body.laterality,
        measurements=body.measurements,
        characteristics=body.characteristics,
        confidence=body.confidence,
        lung_rads_category=body.lung_rads_category,
        radiologist_notes=body.radiologist_notes,
        status="accepted",  # Manual findings are auto-accepted
        reviewed_by=current_user.id,
        reviewed_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(finding)
    await db.commit()
    await db.refresh(finding)
    return finding


@router.post(
    "/studies/{study_id}/batch-review",
    response_model=list[FindingOut],
    summary="Accept or reject multiple findings at once",
)
@limiter.limit("10/minute")
async def batch_review(
    study_id: UUID,
    request: Request,
    action: str,  # "accept_all" or "reject_all"
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Finding]:
    if action not in ("accept_all", "reject_all"):
        raise HTTPException(status_code=400, detail="action must be 'accept_all' or 'reject_all'")

    new_status = "accepted" if action == "accept_all" else "rejected"

    result = await db.execute(
        select(Finding)
        .where(Finding.study_id == study_id)
        .where(Finding.status == "pending")
    )
    findings = list(result.scalars().all())

    now = datetime.datetime.now(datetime.UTC)
    for f in findings:
        f.status = new_status
        f.reviewed_by = current_user.id
        f.reviewed_at = now

    await db.commit()
    for f in findings:
        await db.refresh(f)

    return findings
