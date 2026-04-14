"""RadAI — Model Registry API router."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.ai.model_registry import ModelRegistryService

router = APIRouter()


# ─── Response / Request Models ───────────────────────────────────────────────

class ModelVersionOut(BaseModel):
    id: UUID
    model_name: str
    version: str
    hash: str | None
    config_json: dict | None
    status: str
    deployed_at: str | None
    created_at: str | None

    model_config = {"from_attributes": True}


class ModelVersionCreate(BaseModel):
    model_name: str
    version: str
    hash: str | None = None
    config_json: dict | None = None
    status: str = "testing"


class ModelVersionStatusUpdate(BaseModel):
    status: Literal["active", "deprecated", "testing", "retired"]


class PaginatedModelVersions(BaseModel):
    items: list[ModelVersionOut]
    total: int
    limit: int
    offset: int


class MetricsSummaryOut(BaseModel):
    metric_name: str
    avg_value: float
    min_value: float
    max_value: float
    count: int


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _serialize_version(mv) -> dict:
    return {
        "id": mv.id,
        "model_name": mv.model_name,
        "version": mv.version,
        "hash": mv.hash,
        "config_json": mv.config_json,
        "status": mv.status,
        "deployed_at": mv.deployed_at.isoformat() if mv.deployed_at else None,
        "created_at": mv.created_at.isoformat() if mv.created_at else None,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get(
    "/models",
    response_model=PaginatedModelVersions,
    summary="List all model versions",
)
async def list_model_versions(
    model_name: str | None = None,
    model_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    svc = ModelRegistryService(db)
    versions, total = await svc.list_versions(
        model_name=model_name, status=model_status, limit=limit, offset=offset
    )
    return {
        "items": [_serialize_version(v) for v in versions],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/models/{version_id}",
    response_model=ModelVersionOut,
    summary="Get a single model version",
)
async def get_model_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    svc = ModelRegistryService(db)
    mv = await svc.get_version(version_id)
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found")
    return _serialize_version(mv)


@router.get(
    "/models/{version_id}/metrics",
    summary="Get performance metrics for a model version",
)
async def get_model_metrics(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    svc = ModelRegistryService(db)
    mv = await svc.get_version(version_id)
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found")

    performance = await svc.compute_performance(version_id)
    recorded_metrics = await svc.get_metrics_summary(version_id)

    return {
        "model_version": _serialize_version(mv),
        "performance": performance,
        "recorded_metrics": recorded_metrics,
    }


@router.post(
    "/models",
    response_model=ModelVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new model version (admin only)",
)
async def create_model_version(
    body: ModelVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if hasattr(user, "role") and user.role not in ("admin", "radiologist"):
        raise HTTPException(status_code=403, detail="Only admins or radiologists can register model versions")

    svc = ModelRegistryService(db)
    mv = await svc.register_version(
        model_name=body.model_name,
        version=body.version,
        hash=body.hash,
        config_json=body.config_json,
        status=body.status,
    )
    await db.commit()
    return _serialize_version(mv)


@router.put(
    "/models/{version_id}/status",
    response_model=ModelVersionOut,
    summary="Update model version status (admin only)",
)
async def update_model_version_status(
    version_id: UUID,
    body: ModelVersionStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if hasattr(user, "role") and user.role not in ("admin", "radiologist"):
        raise HTTPException(status_code=403, detail="Only admins or radiologists can update model status")

    svc = ModelRegistryService(db)
    mv = await svc.update_status(version_id, body.status)
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found")
    await db.commit()
    return _serialize_version(mv)


@router.post(
    "/models/seed",
    summary="Seed default model versions (idempotent)",
)
async def seed_model_versions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if hasattr(user, "role") and user.role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admins can seed model versions")

    svc = ModelRegistryService(db)
    created = await svc.seed_defaults()
    await db.commit()
    return {"created": created, "message": f"Seeded {created} model versions" if created else "Registry already populated"}
