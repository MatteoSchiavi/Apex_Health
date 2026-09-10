"""Celery application (MASTER_SPEC §2, §19). Beat carries the first scheduled
job: Garmin sync every 6 hours (§19, §23 Phase 1)."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "hcc",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.health_tasks", "app.tasks.garmin_sync"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # §19: Garmin sync every 6 hours — not real-time, an unofficial client
    # polled continuously raises ban risk.
    beat_schedule={
        "garmin-sync-every-6h": {
            "task": "garmin.sync_all",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
