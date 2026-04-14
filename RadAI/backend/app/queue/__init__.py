"""RadAI — Celery async task queue."""

from app.queue.celery_app import celery_app
from app.queue import tasks  # noqa: F401 — ensures tasks are registered

__all__ = ["celery_app"]
