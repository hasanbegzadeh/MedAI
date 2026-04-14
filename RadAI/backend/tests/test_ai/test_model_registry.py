"""Tests for Model Versioning & Performance Registry (Plan 4.2)."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_registry import (
    DEFAULT_MODELS,
    MODEL_STATUS_ACTIVE,
    MODEL_STATUS_DEPRECATED,
    MODEL_STATUS_TESTING,
    ModelRegistryService,
)
from app.db.models import AIJob, Finding, ModelVersion, Study


# ─── Service Unit Tests ──────────────────────────────────────────────────────


class TestModelRegistryService:

    @pytest.mark.asyncio
    async def test_register_version(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version(
            model_name="TestModel",
            version="1.0.0",
            hash="abc123",
            config_json={"vram_gb": 2.0},
            status=MODEL_STATUS_ACTIVE,
        )
        assert mv.model_name == "TestModel"
        assert mv.version == "1.0.0"
        assert mv.hash == "abc123"
        assert mv.status == MODEL_STATUS_ACTIVE
        assert mv.deployed_at is not None

    @pytest.mark.asyncio
    async def test_register_testing_version_no_deployed_at(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version(
            model_name="TestModel",
            version="2.0.0",
            status=MODEL_STATUS_TESTING,
        )
        assert mv.deployed_at is None

    @pytest.mark.asyncio
    async def test_get_active_version(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)
        await svc.register_version("ModelA", "2.0.0", status=MODEL_STATUS_TESTING)
        await svc.register_version("ModelB", "1.0.0", status=MODEL_STATUS_ACTIVE)

        active = await svc.get_active_version("ModelA")
        assert active is not None
        assert active.version == "1.0.0"
        assert active.model_name == "ModelA"

    @pytest.mark.asyncio
    async def test_get_active_version_none(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        active = await svc.get_active_version("NonExistent")
        assert active is None

    @pytest.mark.asyncio
    async def test_list_versions(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)
        await svc.register_version("ModelA", "2.0.0", status=MODEL_STATUS_TESTING)
        await svc.register_version("ModelB", "1.0.0", status=MODEL_STATUS_ACTIVE)

        # List all
        versions, total = await svc.list_versions()
        assert total == 3

        # Filter by name
        versions, total = await svc.list_versions(model_name="ModelA")
        assert total == 2

        # Filter by status
        versions, total = await svc.list_versions(status=MODEL_STATUS_ACTIVE)
        assert total == 2

    @pytest.mark.asyncio
    async def test_update_status(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_TESTING)
        assert mv.deployed_at is None

        updated = await svc.update_status(mv.id, MODEL_STATUS_ACTIVE)
        assert updated.status == MODEL_STATUS_ACTIVE
        assert updated.deployed_at is not None

    @pytest.mark.asyncio
    async def test_update_status_nonexistent(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        result = await svc.update_status(uuid4(), MODEL_STATUS_DEPRECATED)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_metric(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)

        metric = await svc.record_metric(mv.id, "accuracy", 0.95)
        assert metric.metric_name == "accuracy"
        assert metric.metric_value == 0.95
        assert metric.study_id is None

    @pytest.mark.asyncio
    async def test_compute_performance_no_findings(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)

        perf = await svc.compute_performance(mv.id)
        assert perf["total_reviewed"] == 0
        assert perf["acceptance_rate"] is None

    @pytest.mark.asyncio
    async def test_compute_performance_with_findings(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)

        # Create a study and job linked to this model version
        study = Study(
            orthanc_id="test-perf-study",
            study_instance_uid=f"1.2.3.{uuid4()}",
            modality="CT",
            body_part="CHEST",
        )
        db_session.add(study)
        await db_session.flush()

        job = AIJob(
            study_id=study.id,
            job_type="totalsegmentator",
            model_version_id=mv.id,
            model_name="TotalSegmentator",
            status="completed",
        )
        db_session.add(job)
        await db_session.flush()

        # Create findings with various review statuses
        for status_val in ["accepted", "accepted", "accepted", "rejected", "modified"]:
            finding = Finding(
                study_id=study.id,
                ai_job_id=job.id,
                finding_type="nodule",
                location="Right upper lobe",
                status=status_val,
                confidence=0.85,
            )
            db_session.add(finding)
        await db_session.flush()

        perf = await svc.compute_performance(mv.id)
        assert perf["total_reviewed"] == 5
        assert perf["accepted"] == 3
        assert perf["rejected"] == 1
        assert perf["modified"] == 1
        assert perf["acceptance_rate"] == 0.6
        assert perf["rejection_rate"] == 0.2

    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("ModelA", "1.0.0", status=MODEL_STATUS_ACTIVE)

        await svc.record_metric(mv.id, "accuracy", 0.90)
        await svc.record_metric(mv.id, "accuracy", 0.95)
        await svc.record_metric(mv.id, "accuracy", 0.92)
        await svc.record_metric(mv.id, "latency_ms", 150.0)

        summary = await svc.get_metrics_summary(mv.id)
        assert len(summary) == 2

        accuracy = next(s for s in summary if s["metric_name"] == "accuracy")
        assert accuracy["count"] == 3
        assert 0.90 <= accuracy["avg_value"] <= 0.95

    @pytest.mark.asyncio
    async def test_resolve_version_for_job(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        mv = await svc.register_version("TotalSegmentator", "2.13.0", status=MODEL_STATUS_ACTIVE)

        resolved = await svc.resolve_version_for_job("totalsegmentator")
        assert resolved is not None
        assert resolved.id == mv.id

    @pytest.mark.asyncio
    async def test_resolve_version_for_unknown_job(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        resolved = await svc.resolve_version_for_job("unknown_job_type")
        assert resolved is None

    @pytest.mark.asyncio
    async def test_seed_defaults(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        created = await svc.seed_defaults()
        assert created == len(DEFAULT_MODELS)

        # Idempotent — second call creates nothing
        created_again = await svc.seed_defaults()
        assert created_again == 0

    @pytest.mark.asyncio
    async def test_seed_defaults_all_active(self, db_session: AsyncSession):
        svc = ModelRegistryService(db_session)
        await svc.seed_defaults()

        versions, total = await svc.list_versions(status=MODEL_STATUS_ACTIVE)
        assert total == len(DEFAULT_MODELS)


# ─── API Integration Tests ───────────────────────────────────────────────────


class TestModelRegistryAPI:

    @pytest.mark.asyncio
    async def test_list_models_unauthenticated(self, async_client):
        resp = await async_client.get("/api/v1/ai/models")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_models_empty(self, async_client, auth_headers):
        resp = await async_client.get("/api/v1/ai/models", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert "items" in data
