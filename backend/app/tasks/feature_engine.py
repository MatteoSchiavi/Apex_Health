"""Nightly feature-engine task (§19: 1x/day, 03:00 user-local — prior local
day per §17) and the manual correction path (§6.4).

Celery beat runs one process in UTC; "03:00 user-local" is honored by
dispatching hourly and computing only for users whose local wall clock
currently reads hour 3. Each user therefore triggers exactly once per local
day; a DST fall-back that shows 03:00 twice is harmless because the
computation is an idempotent upsert (§17).

`features.recompute_range` is the §6.4 correction path: after fixing a
feature_weights row (or correcting source data), re-run a closed local-date
range — upserts by (user_id, date) make it a safe backfill, and dates whose
data disappeared get their stale rows deleted.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.features.engine import compute_user_day, compute_user_range
from app.core.db import sessionmaker
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.feature_engine")

NIGHTLY_LOCAL_HOUR = 3


def is_nightly_local_time(now: datetime, tz: ZoneInfo) -> bool:
    """True when `now` falls in the 03:00-03:59 local window for `tz` (§19)."""
    return now.astimezone(tz).hour == NIGHTLY_LOCAL_HOUR


async def _nightly(now_iso: str | None) -> dict:
    now = (
        datetime.fromisoformat(now_iso)
        if now_iso is not None
        else datetime.now(UTC)
    )
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    computed: dict[str, str] = {}
    async with sessionmaker() as session:
        users = (await session.scalars(select(User).order_by(User.id))).all()
        for user in users:
            tz = ZoneInfo(user.timezone)
            if not is_nightly_local_time(now, tz):
                continue
            target_day = now.astimezone(tz).date() - timedelta(days=1)
            try:
                result = await compute_user_day(session, user, target_day)
                # Report only days that actually produced a row — a user with
                # no data for the target day has nothing to report.
                if result is not None:
                    computed[str(user.id)] = str(target_day)
            except Exception:
                # §21: one user's failure must not starve the others; the
                # next night's run (or a recompute_range) heals it.
                logger.exception(
                    "nightly features failed for user %s day %s",
                    user.id,
                    target_day,
                )
    return computed


async def _recompute(user_id: int, start_iso: str, end_iso: str) -> dict:
    start = date_from_iso(start_iso)
    end = date_from_iso(end_iso)
    async with sessionmaker() as session:
        user = await session.get(User, user_id)
        if user is None:
            return {"user_id": user_id, "error": "user not found"}
        return await compute_user_range(session, user, start, end)


def date_from_iso(value: str) -> date:
    return date.fromisoformat(value)


@celery_app.task(name="features.nightly")
def nightly_features(now_iso: str | None = None) -> dict:
    """Compute the prior LOCAL day for every user currently at 03:00."""
    return asyncio.run(_nightly(now_iso))


@celery_app.task(name="features.recompute_range")
def recompute_features(user_id: int, start: str, end: str) -> dict:
    """Owner-facing correction backfill for a closed local-date range (§6.4)."""
    return asyncio.run(_recompute(user_id, start, end))
