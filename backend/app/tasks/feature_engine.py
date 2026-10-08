"""At 03:00 account-local time, repair the prior four weeks of calculations.

Celery beat dispatches hourly in UTC; accounts in the local 03:00 window
recompute all 28 completed local days, including history before registration.
Missing Garmin sleep/HRV/resting-HR feeds and missing recent strength sets use
the existing durable, account-scoped repair outbox. Completed missing-data
checks are remembered for seven days to bound calls to the unofficial API.
No measurements or minimum baseline support are fabricated. The repair worker
recomputes the range after newly fetched data has been normalised.

Manual features.recompute_range remains the bounded correction path (366 days).
"""

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, or_

from app.features.engine import compute_user_range
from app.core.db import sessionmaker
from app.models.user import User, AuthCredential
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async

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
        users = (await session.scalars(select(User).outerjoin(AuthCredential, AuthCredential.user_id == User.id)
            .where(or_(AuthCredential.user_id.is_(None), AuthCredential.disabled.is_(False))).order_by(User.id))).all()
    for user in users:
        tz = ZoneInfo(user.timezone)
        if not is_nightly_local_time(now, tz):
            continue
        target_day = now.astimezone(tz).date() - timedelta(days=1)
        start = target_day - timedelta(days=27)
        try:
            async with sessionmaker() as session:
                await compute_user_range(session, user, start, target_day)
                from app.models.features import DailyFeature
                if await session.get(DailyFeature, {"user_id": user.id, "date": target_day}):
                    computed[str(user.id)] = str(target_day)
            await queue_history_repair(user, start, target_day)
        except Exception:
            logger.exception("nightly history repair failed for user %s", user.id)
    return computed


async def queue_history_repair(user, start, end):
    """Use the existing durable repair outbox, never a remote call under a lock.

    A partial day is not a completed import: one sleep row cannot mark the HRV
    and daily-stat feeds complete. Existing supported sources remain distinct.
    """
    from app.models.integration import Integration
    from app.models.lab import Observation, LabJob
    from app.services.jobs import request_job
    from app.services.evidence import EvidenceError, scope_lock

    async with sessionmaker() as session:
        integration = await session.scalar(select(Integration).where(
            Integration.user_id == user.id, Integration.provider == "garmin",
            Integration.status == "active", Integration.credentials_encrypted.is_not(None)))
        if integration is None:
            return
        records = (await session.execute(select(Observation.local_date, Observation.metric).where(
            Observation.user_id == user.id, Observation.origin == "garmin", Observation.current.is_(True),
            Observation.availability == "available", Observation.local_date.between(start, end),
            Observation.metric.in_(("resting_hr", "hrv_overnight_rmssd", "sleep_duration"))))).all()
        present = {}
        for day, metric in records:
            present.setdefault(day, set()).add(metric)
        # A completed check may honestly return not-measured. Retry such older
        # days weekly, rather than asking the unofficial API 140 times/night.
        checks = (await session.scalars(select(LabJob).where(
            LabJob.user_id == user.id, LabJob.kind == "repair", LabJob.state == "completed",
            LabJob.updated_at >= datetime.now(UTC) - timedelta(days=7)))).all()
        checked = set()
        for job in checks:
            if job.parameters.get("days") is not None:
                checked.update(job.parameters["days"])
            else:
                first, last = date.fromisoformat(job.parameters["start"]), date.fromisoformat(job.parameters["end"])
                checked.update(str(first + timedelta(days=i)) for i in range((last - first).days + 1))
        days = [str(day) for day in (start + timedelta(days=i) for i in range(28))
                if len(present.get(day, set())) < 3 and str(day) not in checked]
        from app.connectors.garmin.sync import missing_strength_links
        gym_missing = await session.scalar(missing_strength_links(user.id, start, end).limit(1))
        if not days and not gym_missing:
            return
        try:
            await scope_lock(session, user.id, "maintenance_jobs")
            # A user's existing full repair must not be narrowed to the night's
            # missing-feed subset merely because its date range happens to match.
            if await session.scalar(select(LabJob.id).where(LabJob.user_id == user.id, LabJob.state.in_(("queued", "running"))).limit(1)):
                return
            requested = await request_job(session, user, "repair", start, end)
            job = await session.get(LabJob, requested["id"])
            job.parameters = {**job.parameters, "days": days, "repair_strength": True}
            await session.commit()
        except EvidenceError as exc:
            if exc.code != "CONFLICT":
                raise


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
    """Repair the previous four LOCAL weeks for users currently at 03:00."""
    return run_async(_nightly(now_iso))


@celery_app.task(name="features.recompute_range")
def recompute_features(user_id: int, start: str, end: str) -> dict:
    """Owner-facing correction backfill for a closed local-date range (§6.4)."""
    return run_async(_recompute(user_id, start, end))
