"""Scheduled AI report tasks (MASTER_SPEC §19).

Hourly-dispatch pattern (same as the feature engine / gear accumulation):
beat ticks on the hour/half-hour in UTC, each task computes only for users
whose LOCAL wall clock matches the §19 cadence —

- daily summary: :45 inside the 03:00-03:59 local window, summarizing the
  freshly computed prior local day (templated, no LLM — see reports/daily.py)
- weekly AI report: Monday 06:00 local, last Mon..Sun (§19, powerful tier)
- monthly AI report: 1st of month 06:00 local, previous calendar month

A DST fall-back double-run is harmless: every row upserts idempotently per
(user, report_type, period_start) (§17).
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import sessionmaker
from app.models.user import User
from app.reports.daily import upsert_daily_report
from app.reports.periodic import upsert_periodic_report
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.reports")

DAILY_LOCAL_HOUR = 3
REPORT_LOCAL_HOUR = 6


def is_report_local_time(now: datetime, tz: ZoneInfo, weekday: int | None, day: int | None) -> bool:
    local = now.astimezone(tz)
    if local.hour != REPORT_LOCAL_HOUR:
        return False
    if weekday is not None and local.weekday() != weekday:
        return False
    if day is not None and local.day != day:
        return False
    return True


async def _users_at(session, now: datetime, *, hour: int, weekday: int | None = None, day_of_month: int | None = None) -> list[tuple[User, datetime]]:
    """Users whose local wall clock currently matches the dispatch window,
    with their local `now` for downstream day math."""
    matches: list[tuple[User, datetime]] = []
    users = (await session.scalars(select(User).order_by(User.id))).all()
    for user in users:
        tz = ZoneInfo(user.timezone)
        local_now = now.astimezone(tz)
        if local_now.hour != hour:
            continue
        if weekday is not None and local_now.weekday() != weekday:
            continue
        if day_of_month is not None and local_now.day != day_of_month:
            continue
        matches.append((user, local_now))
    return matches


async def _dispatch_daily(now_iso: str | None = None) -> dict:
    now = _now_of(now_iso)
    results: dict[str, str] = {}
    async with sessionmaker() as session:
        targets = await _users_at(session, now, hour=DAILY_LOCAL_HOUR)
    for user, local_now in targets:
        target_day = local_now.date() - timedelta(days=1)  # the just-computed local day
        try:
            row = await upsert_daily_report(sessionmaker, user, target_day)
            results[str(user.id)] = f"daily:{row.period_start.isoformat() if row else 'skipped'}"
        except ValueError:
            results[str(user.id)] = "no-data"
        except Exception:
            # §21: one user's failure must not starve the others.
            logger.exception("daily summary failed for user %s", user.id)
            results[str(user.id)] = "failed"
    return results


def _period_for(report_type: str, local_now: datetime) -> tuple[date, date]:
    """§19 periods, user-local: weekly = Mon..Sun ending yesterday; monthly =
    the previous calendar month."""
    today = local_now.date()
    if report_type == "weekly":
        # today is Monday → period is the 7 days ending yesterday (Sunday)
        end = today - timedelta(days=1)
        start = end - timedelta(days=6)
        return start, end
    # monthly: previous calendar month
    first_of_this_month = today.replace(day=1)
    end = first_of_this_month - timedelta(days=1)
    start = end.replace(day=1)
    return start, end


async def _dispatch_periodic(report_type: str, now_iso: str | None = None) -> dict:
    now = _now_of(now_iso)
    settings = get_settings()
    if not settings.glm_api_key:
        logger.warning("%s report skipped: GLM_API_KEY not configured", report_type)
        return {"status": "no-llm-key"}

    from app.core.llm import build_llm_client

    llm = build_llm_client()

    if report_type == "weekly":
        weekday, day_of_month = 0, None  # Monday
    else:
        weekday, day_of_month = None, 1  # 1st of month

    async with sessionmaker() as session:
        targets = await _users_at(session, now, hour=REPORT_LOCAL_HOUR, weekday=weekday, day_of_month=day_of_month)

    results: dict[str, str] = {}
    from app.connectors.telegram.alerts import notify_user

    telegram = None
    if settings.telegram_bot_token:
        from app.connectors.telegram.client import LiveTelegramClient

        telegram = LiveTelegramClient(settings.telegram_bot_token)

    embeddings_client = None
    if settings.openai_api_key:
        from app.core.embeddings import build_embedding_client

        embeddings_client = build_embedding_client()

    for user, local_now in targets:
        start, end = _period_for(report_type, local_now)
        try:
            row = await upsert_periodic_report(
                sessionmaker, llm, user, report_type, start, end, embeddings_client=embeddings_client
            )
            if row is None:
                results[str(user.id)] = "no-data"
                continue
            results[str(user.id)] = f"{report_type}:{row.period_start.isoformat()}"
            if telegram is not None:
                header = f"📊 Your {report_type} report ({start.isoformat()} — {end.isoformat()}):\n\n"
                await notify_user(sessionmaker, telegram, user.id, header + row.content_md)
        except Exception:
            logger.exception("%s report failed for user %s", report_type, user.id)
            results[str(user.id)] = "failed"
    return results


def _now_of(now_iso: str | None) -> datetime:
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    return now.replace(tzinfo=UTC) if now.tzinfo is None else now


@celery_app.task(name="reports.daily_summary")
def daily_summaries(now_iso: str | None = None) -> dict:
    return asyncio.run(_dispatch_daily(now_iso))


@celery_app.task(name="reports.weekly")
def weekly_reports(now_iso: str | None = None) -> dict:
    return asyncio.run(_dispatch_periodic("weekly", now_iso))


@celery_app.task(name="reports.monthly")
def monthly_reports(now_iso: str | None = None) -> dict:
    return asyncio.run(_dispatch_periodic("monthly", now_iso))
