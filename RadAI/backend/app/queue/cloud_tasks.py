"""RadAI — Celery tasks for cloud GPU job processing.

These tasks run in the Celery worker and handle the full cloud pipeline:
anonymization → upload → cloud inference → download → results storage.
"""
from __future__ import annotations

import asyncio
import datetime
from uuid import UUID

import structlog

from app.queue.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, name="radai.tasks.cloud_segmentation", max_retries=2)
def cloud_segmentation_task(
    self,
    job_id: str,
    study_id: str,
    job_type: str = "totalsegmentator_full",
    params: dict | None = None,
) -> dict:
    """Run cloud segmentation pipeline as a Celery task.

    This allows the cloud pipeline to be queued and retried independently
    of the FastAPI process.
    """
    from app.cloud.pipeline import run_cloud_segmentation

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            run_cloud_segmentation(
                job_id=UUID(job_id),
                study_id=UUID(study_id),
                job_type=job_type,
                params=params,
            )
        )
        return {
            "status": "completed",
            "job_type": job_type,
            "completed_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    except Exception as exc:
        logger.error(
            "Cloud segmentation task failed",
            job_id=job_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=120)
