"""Celery application (MASTER_SPEC §2, §19). Beat carries the scheduled jobs
that have landed so far: Garmin + Technogym syncs every 6 hours (Phases 1/6),
the forecast refresh every 6 hours (Phase 7, §19), the nightly feature engine
at 03:00 user-local (Phase 2), nightly gear accumulation right after it
(Phase 4), the daily AI budget check at 23:45 UTC (Phase 5, §8.6), and the
nightly encrypted database backup at 02:00 UTC (Phase 8, §22.7/§19)."""

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
        "app.tasks.technogym_sync",
        "app.tasks.weather_tasks",
        "app.tasks.feature_engine",
        "app.tasks.gear_tasks",
        "app.tasks.budget",
        "app.tasks.ai_reports",
        "app.tasks.telegram_voice",
        "app.tasks.backups",
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
        # §19: Technogym sync every 6 hours — same unofficial-client pacing
        # reasoning as Garmin. Staggered at :10 to spread engine load; still
        # every-6h per §19 (documented judgment call).
        "technogym-sync-every-6h": {
            "task": "technogym.sync_all",
            "schedule": crontab(minute=10, hour="*/6"),
        },
        # §19: forecast refresh every 6 hours, upserts forecast_cache (§6.4).
        # Staggered at :20, after both connector syncs — so activities they
        # ingested are enriched in the same tick (§14).
        "weather-refresh-every-6h": {
            "task": "weather.refresh_all",
            "schedule": crontab(minute=20, hour="*/6"),
        },
        # §14 nudge: hourly dispatch, the task gates on LOCAL hour 07:00 (the
        # feature engine's pattern) and de-dupes per user per day in Redis.
        "weather-nudge-hourly-dispatch": {
            "task": "weather.readiness_nudge",
            "schedule": crontab(minute=25),
        },
        "feature-engine-hourly-dispatch": {
            "task": "features.nightly",
            "schedule": crontab(minute=0),
        },
        # §19: gear accumulation "right after feature engine" — the :15 tick
        # is still inside every user's 03:00-03:59 local window, so it runs
        # after that day's feature pass, wherever the user lives.
        "gear-accumulation-hourly-dispatch": {
            "task": "gear.accumulate_all",
            "schedule": crontab(minute=15),
        },
        # §19: daily budget check, 1×/day at 23:45 UTC — near the close of
        # the UTC accounting day the token_usage sums use (§8.6).
        "daily-budget-check": {
            "task": "budget.daily_check",
            "schedule": crontab(minute=45, hour=23),
        },
        # §19 Phase 5 reports: hourly dispatch, tasks select users by LOCAL
        # wall clock — daily summary at :45 inside the 03:00-03:59 window
        # (after feature engine + gear), weekly Monday 06:00, monthly 1st
        # 06:00. Weekly/monthly ride the powerful tier (§9.2).
        "daily-summary-hourly-dispatch": {
            "task": "reports.daily_summary",
            "schedule": crontab(minute=45),
        },
        "weekly-report-hourly-dispatch": {
            "task": "reports.weekly",
            "schedule": crontab(minute=0),
        },
        "monthly-report-hourly-dispatch": {
            "task": "reports.monthly",
            "schedule": crontab(minute=0),
        },
        # §19/§22.7: nightly encrypted pg_dump at 02:00 UTC. Database-wide
        # job — no per-user local-time semantics, so a plain UTC crontab.
        "nightly-backup": {
            "task": "backups.nightly",
            "schedule": crontab(minute=0, hour=2),
        },
    },
)
