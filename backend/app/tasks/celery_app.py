"""Celery application (MASTER_SPEC §2, §19). Celery beat joins in a later phase
with the first scheduled job (§23 phase order)."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "hcc",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.health_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
