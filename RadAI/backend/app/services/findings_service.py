"""RadAI — Findings persistence service."""

import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AIJob, Finding


class FindingsService:
    """Service for persisting AI findings and updating job status."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
        progress_pct: int | None = None,
        result_json: dict | None = None,
        error_message: str | None = None,
    ):
        """Update the status and progress of an AI job."""
        job = await self.db.get(AIJob, job_id)
        if job:
            if status:
                job.status = status
            if progress_pct is not None:
                job.progress_pct = progress_pct
            if result_json:
                job.result_json = result_json
            if error_message:
                job.error_message = error_message

            if status == "completed":
                job.completed_at = datetime.datetime.now(datetime.UTC)
            
            await self.db.commit()

    async def persist_nodule_findings(
        self, study_id: UUID, job_id: UUID, candidates: list
    ):
        """Convert nodule candidates into permanent Finding records."""
        for c in candidates:
            finding = Finding(
                study_id=study_id,
                ai_job_id=job_id,
                finding_type="nodule",
                location=c.location,
                laterality=c.laterality,
                measurements={
                    "longest_diameter_mm": c.diameter_mm,
                    "volume_mm3": c.volume_mm3,
                    "mean_hu": c.mean_hu,
                },
                characteristics=[c.lobe] if c.lobe else [],
                confidence=c.confidence,
                status="pending",
            )
            self.db.add(finding)
        
        await self.db.commit()
