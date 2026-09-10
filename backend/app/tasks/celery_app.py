"""Celery application (MASTER_SPEC §2, §19). Beat carries the scheduled jobs
that have landed so far: Garmin sync every 6 hours (Phase 1) and the nightly
feature engine at 03:00 user-local (Phase 2)."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "hcc",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.health_tasks",
        "app.tasks.garmin_sync",
        "app.tasks.feature_engine",
        "app.tasks.telegram_voice",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # §19: Garmin sync every 6 hours — not real-time, an unofficial client
    # polled continuously raises ban risk.
    #
    # §19: nightly feature engine at 03:00 USER-LOCAL. Beat ticks hourly and
    # the task computes only for users whose local wall clock reads hour 3,
    # so every timezone is served from this single UTC schedule; DST
    # fall-back double-runs are harmless (the engine upserts idempotently).
    beat_schedule={
        "garmin-sync-every-6h": {
            "task": "garmin.sync_all",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "feature-engine-hourly-dispatch": {
            "task": "features.nightly",
            "schedule": crontab(minute=0),
        },
    },
)
