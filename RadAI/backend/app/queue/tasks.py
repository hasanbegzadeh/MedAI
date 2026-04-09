"""RadAI — Celery async task definitions."""

from __future__ import annotations

import datetime
from uuid import UUID

import structlog

from app.queue.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, name="radai.tasks.run_totalsegmentator", max_retries=3)
def run_totalsegmentator_task(
    self,
    job_id: UUID,
    input_path: str,
    output_path: str,
    roi_subset: list[str] | None = None,
    fast: bool = True,
    timeout: int = 300,
) -> dict:
    """Run TotalSegmentator as a Celery task."""
    from app.scheduler import get_scheduler, ModelSchedulerError

    scheduler = get_scheduler()
    try:
        scheduler.run_totalsegmentator(
            input_path=input_path,
            output_path=output_path,
            roi_subset=roi_subset,
            fast=fast,
            timeout=timeout,
        )
        return {
            "status": "completed",
            "output_path": output_path,
            "completed_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    except ModelSchedulerError as exc:
        logger.error("TotalSegmentator task failed", job_id=str(job_id), error=str(exc))
        raise self.retry(exc=exc, countdown=60)
