"""Celery application (MASTER_SPEC §2, §19). Beat carries the scheduled jobs
that have landed so far: Garmin + Technogym syncs every 6 hours (Phases 1/6),
the forecast refresh every 6 hours (Phase 7, §19), the nightly feature engine
at 03:00 user-local (Phase 2), nightly gear accumulation right after it
(Phase 4), the daily AI budget check at 23:45 UTC (Phase 5, §8.6), and the
nightly encrypted database backup at 02:00 UTC (Phase 8, §22.7/§19).

F-02 audit: acks_late + reject_on_worker_lost + visibility_timeout + retry
defaults + soft/hard time limits are now set globally so a worker restart
mid-backfill no longer loses the task and a transient third-party outage
retries with exponential backoff instead of failing the whole batch.
"""

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
        "app.tasks.whoop_sync",
        "app.tasks.strava_sync",
        "app.tasks.oura_sync",
        "app.tasks.weather_tasks",
        "app.tasks.feature_engine",
        "app.tasks.gear_tasks",
        "app.tasks.budget",
        "app.tasks.ai_reports",
        "app.tasks.telegram_voice",
        "app.tasks.backups",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # ---- F-02 audit: task durability --------------------------------------
    # acks_late=True: a task is acked ONLY after it completes successfully.
    # A worker crash mid-backfill redelivers the task to another worker
    # instead of losing it silently.
    task_acks_late=True,
    # reject_on_worker_lost=True: if the worker process dies (OOM, kill),
    # the task is requeued instead of being marked failed.
    task_reject_on_worker_lost=True,
    # visibility_timeout MUST exceed the longest task (the redis broker
    # uses it to redeliver tasks whose ack is overdue). 5h comfortably
    # covers the 4h hard time limit below.
    broker_transport_options={"visibility_timeout": 5 * 3600},
    # Hard ceiling on any single task: 4h wall-clock, 3h soft. Long enough
    # for a multi-year Garmin backfill; short enough that a wedged task
    # cannot pin a worker indefinitely.
    task_time_limit=4 * 3600,
    task_soft_time_limit=3 * 3600,
    # Default retry policy for tasks that don't override: 3 retries with
    # exponential backoff (1 → 2 → 4 minutes) capped at 10 minutes.
    task_default_retry_delay=60,
    task_default_max_retries=3,
    # Prefetch: one task per worker at a time so a long-running backfill
    # doesn't starve short tasks behind it. Critical for an 8 GB single-node
    # box where 2 workers each holding 4 tasks would OOM under load.
    worker_prefetch_multiplier=1,
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
        # Official-API connectors (owner feature batch, 2026-09): Whoop and
        # Strava sync on the same every-6h cadence, staggered at :05/:07 so
        # the unofficial-client Garmin poll (:00) and the feature engine
        # never collide. Official APIs are gentler than the unofficial
        # Garmin client, but pacing is still §19 law.
        "whoop-sync-every-6h": {
            "task": "whoop.sync_all",
            "schedule": crontab(minute=5, hour="*/6"),
        },
        "strava-sync-every-6h": {
            "task": "strava.sync_all",
            "schedule": crontab(minute=7, hour="*/6"),
        },
        # Oura (official API v2, personal apps allowed) rides the same 6h
        # cadence at :09 — after Whoop/Strava, before the weather refresh.
        "oura-sync-every-6h": {
            "task": "oura.sync_all",
            "schedule": crontab(minute=9, hour="*/6"),
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
        # F-08 audit: nightly session purge at 04:00 UTC — bounded by the
        # idx_sessions_expires_at index added in migration 0008.
        "session-purge-nightly": {
            "task": "maintenance.purge_sessions",
            "schedule": crontab(minute=0, hour=4),
        },
        # D-01/D-10 audit: nightly retention + maintenance at 04:30 UTC.
        "retention-nightly": {
            "task": "maintenance.prune_streams",
            "schedule": crontab(minute=30, hour=4),
        },
        "vacuum-weekly": {
            "task": "maintenance.vacuum_analyze",
            "schedule": crontab(minute=0, hour=4, day_of_week=0),
        },
    },
)
