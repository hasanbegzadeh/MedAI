"""RadAI — Studies API router."""

# NOTE: do NOT add `from __future__ import annotations` here. See app/api/ai.py
# for the full explanation — slowapi's @limiter.limit decorator swaps out the
# wrapped function's __globals__, so PEP 563 stringified annotations cannot
# resolve module-level names like `UUID` at FastAPI schema-build time. Even
# though this router currently has no @limiter.limit endpoints, the ban holds
# to prevent future additions from silently breaking the app.

from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.db.models import Study, User
from app.db.session import get_db

router = APIRouter()
logger = structlog.get_logger(__name__)
settings = get_settings()


class StudyOut(BaseModel):
    id: UUID
    orthanc_id: str
    study_instance_uid: str
    modality: str
    body_part: str | None
    study_description: str | None
    ai_status: str

    model_config = {"from_attributes": True}


class PaginatedStudies(BaseModel):
    items: list[StudyOut]
    total: int
    limit: int
    offset: int


@router.get(
    "/",
    response_model=PaginatedStudies,
    summary="List all studies with pagination",
)
async def list_studies(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    modality: str | None = None,
    ai_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedStudies:
    query = select(Study)
    count_query = select(func.count()).select_from(Study)

    if modality:
        query = query.where(Study.modality == modality.upper())
        count_query = count_query.where(Study.modality == modality.upper())
    if ai_status:
        query = query.where(Study.ai_status == ai_status)
        count_query = count_query.where(Study.ai_status == ai_status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    studies = list(result.scalars().all())

    return PaginatedStudies(
        items=[StudyOut.model_validate(s) for s in studies],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{study_id}", response_model=StudyOut, summary="Get a single study")
async def get_study(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StudyOut:
    obj = await db.get(Study, study_id)
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study not found"
        )
    return StudyOut.model_validate(obj)


class SyncResult(BaseModel):
    synced: int
    created: int
    updated: int
    orthanc_studies_total: int


@router.post(
    "/sync-from-orthanc",
    response_model=SyncResult,
    summary="Pull the current study list from Orthanc and upsert into the DB",
)
async def sync_from_orthanc(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SyncResult:
    """Idempotent one-shot sync: fetch every study from Orthanc and upsert.

    This is a Phase 1 bootstrap endpoint. In production, studies should be
    ingested reactively via an Orthanc webhook or periodic poll — but for
    development and E2E testing we want a blunt "refresh everything" button
    that the OHIF extension and smoke tests can call.
    """
    auth = (settings.orthanc_user, settings.orthanc_password)
    created = 0
    updated = 0

    async with httpx.AsyncClient(timeout=30, auth=auth) as client:
        resp = await client.get(f"{settings.orthanc_url}/studies")
        resp.raise_for_status()
        study_ids: list[str] = resp.json()

        for orthanc_id in study_ids:
            detail = await client.get(f"{settings.orthanc_url}/studies/{orthanc_id}")
            detail.raise_for_status()
            info = detail.json()

            main_tags = info.get("MainDicomTags", {}) or {}
            patient_tags = info.get("PatientMainDicomTags", {}) or {}
            study_uid = main_tags.get("StudyInstanceUID") or ""
            if not study_uid:
                logger.warning(
                    "Skipping Orthanc study without StudyInstanceUID",
                    orthanc_id=orthanc_id,
                )
                continue

            # Count series and instances by pulling the child lists
            num_series = len(info.get("Series", []) or [])
            num_instances = 0
            for series_id in info.get("Series", []) or []:
                series_detail = await client.get(
                    f"{settings.orthanc_url}/series/{series_id}"
                )
                if series_detail.status_code == 200:
                    num_instances += len(
                        series_detail.json().get("Instances", []) or []
                    )

            # Modality: Orthanc stores this at the series level, so sniff
            # the first series. Fall back to "OT" (Other) when unknown.
            modality = "OT"
            first_series_list = info.get("Series", []) or []
            if first_series_list:
                series_detail = await client.get(
                    f"{settings.orthanc_url}/series/{first_series_list[0]}"
                )
                if series_detail.status_code == 200:
                    modality = (
                        series_detail.json()
                        .get("MainDicomTags", {})
                        .get("Modality", "OT")
                    )

            existing = await db.execute(
                select(Study).where(Study.orthanc_id == orthanc_id)
            )
            obj = existing.scalar_one_or_none()
            if obj is None:
                obj = Study(
                    orthanc_id=orthanc_id,
                    study_instance_uid=study_uid,
                    accession_number=main_tags.get("AccessionNumber"),
                    modality=modality,
                    body_part=main_tags.get("BodyPartExamined"),
                    study_description=main_tags.get("StudyDescription"),
                    num_series=num_series,
                    num_instances=num_instances,
                )
                db.add(obj)
                created += 1
            else:
                obj.modality = modality
                obj.body_part = main_tags.get("BodyPartExamined") or obj.body_part
                obj.study_description = (
                    main_tags.get("StudyDescription") or obj.study_description
                )
                obj.num_series = num_series
                obj.num_instances = num_instances
                updated += 1

    await db.commit()
    return SyncResult(
        synced=created + updated,
        created=created,
        updated=updated,
        orthanc_studies_total=len(study_ids),
    )
