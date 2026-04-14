"""RadAI — Model Versioning & Performance Registry.

FDA PCCP-ready model tracking: every AI inference is linked to an exact
model version, and acceptance/rejection rates are computed as approximate
performance metrics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIJob, Finding, ModelMetric, ModelVersion


MODEL_STATUS_ACTIVE = "active"
MODEL_STATUS_DEPRECATED = "deprecated"
MODEL_STATUS_TESTING = "testing"
MODEL_STATUS_RETIRED = "retired"

# Default model definitions used to seed the registry on first run.
DEFAULT_MODELS: list[dict] = [
    {
        "model_name": "TotalSegmentator",
        "version": "2.13.0",
        "config_json": {
            "vram_gb": 2.0,
            "mode": "fast+body_seg",
            "classes": 117,
            "framework": "nnUNet",
        },
    },
    {
        "model_name": "nnInteractive",
        "version": "0.1.0",
        "config_json": {
            "vram_gb": 6.0,
            "prompt_types": ["click", "scribble", "bbox"],
            "framework": "nnUNet",
        },
    },
    {
        "model_name": "LiteMedSAM",
        "version": "1.0.0",
        "config_json": {
            "vram_gb": 2.5,
            "framework": "SAM",
        },
    },
    {
        "model_name": "NoduleDetection",
        "version": "1.0.0",
        "config_json": {
            "vram_gb": 0,
            "framework": "scipy+MONAI",
            "hu_range": [-700, 300],
            "size_range_mm": [2, 30],
        },
    },
    {
        "model_name": "MedGemma",
        "version": "1.5-4b-it-Q4",
        "config_json": {
            "vram_gb": 3.0,
            "framework": "Ollama",
            "task": "report_polish",
        },
    },
    {
        "model_name": "faster-whisper",
        "version": "large-v3",
        "config_json": {
            "vram_gb": 3.0,
            "framework": "CTranslate2",
            "task": "voice_transcription",
        },
    },
]

# Map job_type strings to model_name for automatic version lookup.
JOB_TYPE_TO_MODEL: dict[str, str] = {
    "totalsegmentator": "TotalSegmentator",
    "nninteractive": "nnInteractive",
    "litemedsam": "LiteMedSAM",
    "nodule_detection": "NoduleDetection",
    "report_polish": "MedGemma",
    "medsam2": "MedSAM2",
}


class ModelRegistryService:
    """Manages model versions and computes performance metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_version(
        self,
        model_name: str,
        version: str,
        hash: str | None = None,
        config_json: dict | None = None,
        status: str = MODEL_STATUS_TESTING,
    ) -> ModelVersion:
        mv = ModelVersion(
            model_name=model_name,
            version=version,
            hash=hash,
            config_json=config_json or {},
            status=status,
            deployed_at=datetime.now(timezone.utc) if status == MODEL_STATUS_ACTIVE else None,
        )
        self.db.add(mv)
        await self.db.flush()
        return mv

    async def get_active_version(self, model_name: str) -> ModelVersion | None:
        stmt = select(ModelVersion).where(
            ModelVersion.model_name == model_name,
            ModelVersion.status == MODEL_STATUS_ACTIVE,
        ).order_by(ModelVersion.deployed_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_version(self, version_id: uuid.UUID) -> ModelVersion | None:
        return await self.db.get(ModelVersion, version_id)

    async def list_versions(
        self,
        model_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ModelVersion], int]:
        stmt = select(ModelVersion)
        count_stmt = select(func.count(ModelVersion.id))

        if model_name:
            stmt = stmt.where(ModelVersion.model_name == model_name)
            count_stmt = count_stmt.where(ModelVersion.model_name == model_name)
        if status:
            stmt = stmt.where(ModelVersion.status == status)
            count_stmt = count_stmt.where(ModelVersion.status == status)

        stmt = stmt.order_by(ModelVersion.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        total_result = await self.db.execute(count_stmt)

        return list(result.scalars().all()), total_result.scalar_one()

    async def update_status(self, version_id: uuid.UUID, new_status: str) -> ModelVersion | None:
        mv = await self.db.get(ModelVersion, version_id)
        if not mv:
            return None
        mv.status = new_status
        if new_status == MODEL_STATUS_ACTIVE:
            mv.deployed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return mv

    async def record_metric(
        self,
        model_version_id: uuid.UUID,
        metric_name: str,
        metric_value: float,
        study_id: uuid.UUID | None = None,
    ) -> ModelMetric:
        metric = ModelMetric(
            model_version_id=model_version_id,
            metric_name=metric_name,
            metric_value=metric_value,
            study_id=study_id,
        )
        self.db.add(metric)
        await self.db.flush()
        return metric

    async def compute_performance(self, model_version_id: uuid.UUID) -> dict:
        """Compute acceptance/rejection metrics for a model version.

        These are approximations based on radiologist review decisions,
        NOT ground-truth validated metrics.
        """
        # Get all findings produced by jobs using this model version
        stmt = (
            select(Finding.status)
            .join(AIJob, Finding.ai_job_id == AIJob.id)
            .where(AIJob.model_version_id == model_version_id)
            .where(Finding.status.in_(["accepted", "rejected", "modified"]))
        )
        result = await self.db.execute(stmt)
        statuses = [r[0] for r in result.all()]

        total_reviewed = len(statuses)
        if total_reviewed == 0:
            return {
                "model_version_id": str(model_version_id),
                "total_reviewed": 0,
                "accepted": 0,
                "rejected": 0,
                "modified": 0,
                "acceptance_rate": None,
                "rejection_rate": None,
                "note": "No reviewed findings yet for this model version.",
            }

        accepted = statuses.count("accepted")
        rejected = statuses.count("rejected")
        modified = statuses.count("modified")

        return {
            "model_version_id": str(model_version_id),
            "total_reviewed": total_reviewed,
            "accepted": accepted,
            "rejected": rejected,
            "modified": modified,
            "acceptance_rate": round(accepted / total_reviewed, 4),
            "rejection_rate": round(rejected / total_reviewed, 4),
            "modification_rate": round(modified / total_reviewed, 4),
            "note": "Metrics are approximate — based on radiologist review decisions, not ground-truth labels.",
        }

    async def get_metrics_summary(self, model_version_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(
                ModelMetric.metric_name,
                func.avg(ModelMetric.metric_value).label("avg_value"),
                func.min(ModelMetric.metric_value).label("min_value"),
                func.max(ModelMetric.metric_value).label("max_value"),
                func.count(ModelMetric.id).label("count"),
            )
            .where(ModelMetric.model_version_id == model_version_id)
            .group_by(ModelMetric.metric_name)
        )
        result = await self.db.execute(stmt)
        return [
            {
                "metric_name": row.metric_name,
                "avg_value": round(float(row.avg_value), 4),
                "min_value": round(float(row.min_value), 4),
                "max_value": round(float(row.max_value), 4),
                "count": row.count,
            }
            for row in result.all()
        ]

    async def resolve_version_for_job(self, job_type: str) -> ModelVersion | None:
        """Look up the active model version for a given job_type."""
        model_name = JOB_TYPE_TO_MODEL.get(job_type)
        if not model_name:
            return None
        return await self.get_active_version(model_name)

    async def seed_defaults(self) -> int:
        """Seed default model versions if registry is empty. Returns count created."""
        count_result = await self.db.execute(select(func.count(ModelVersion.id)))
        if count_result.scalar_one() > 0:
            return 0

        created = 0
        for model_def in DEFAULT_MODELS:
            await self.register_version(
                model_name=model_def["model_name"],
                version=model_def["version"],
                config_json=model_def.get("config_json"),
                status=MODEL_STATUS_ACTIVE,
            )
            created += 1
        await self.db.flush()
        return created
