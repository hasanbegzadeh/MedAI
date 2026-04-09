"""RadAI — Studies API router."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db.models import Study, User
from app.db.session import get_db

router = APIRouter()


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
