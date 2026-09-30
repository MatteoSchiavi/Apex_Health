"""Rankings & challenges: live metric computation over canonical tables.

At friends-scale, computing leaderboards on the fly is cheap and always
consistent with freshly synced data (no materialization step to drift).
All metric semantics are documented inline; ordering: lowest for times
(5k), highest for everything else.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.challenge import Challenge, ChallengeMember
from app.models.user import User
from app.models.wellness import DailyBiometric, SleepSession

METRICS = {
    "activities_count",
    "steps",
    "distance_m",
    "intensity_minutes",
    "sleep_score_avg",
    "training_load_sum",
    "5k_time_s",
}

# intensity minutes proxy: minutes of tracked activity at/above a moderate
# aerobic HR (the canonical schema has no Garmin "intensity minutes" column;
# this is the documented, device-agnostic approximation).
MODERATE_HR = 100

# 5k record window: runs between 4.8 and 5.2 km count as 5k attempts.
_FIVE_K_LOW_M, _FIVE_K_HIGH_M = 4800, 5200


def period_window(
    challenge: Challenge, now: datetime, tz_offset_days: int = 0
) -> tuple[datetime | None, datetime | None]:
    """(start, end) bounds for the challenge period (UTC, inclusive start)."""
    if challenge.period == "all_time":
        return None, None
    if challenge.period == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, None
    if challenge.period == "monthly":
        start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return start, None
    return challenge.starts_at, challenge.ends_at


async def _member_ids(session: AsyncSession, challenge_id: int) -> list[int]:
    rows = await session.scalars(
        select(ChallengeMember.user_id).where(
            ChallengeMember.challenge_id == challenge_id
        )
    )
    return list(rows.all())


async def compute_metric(
    session: AsyncSession,
    user_id: int,
    metric: str,
    *,
    start: datetime | None,
    end: datetime | None,
) -> float | None:
    """One user's metric value over the window; None = no data (ranked last
    rather than zero, so someone with no Whoop/Garmin sync isn't 'worst')."""
    if metric == "activities_count":
        q = select(func.count(Activity.id)).where(Activity.user_id == user_id)
        if start:
            q = q.where(Activity.start_time >= start)
        if end:
            q = q.where(Activity.start_time < end)
        value = await session.scalar(q)
        return float(value or 0)

    if metric == "distance_m":
        q = select(func.coalesce(func.sum(Activity.distance_m), 0.0)).where(
            Activity.user_id == user_id
        )
        if start:
            q = q.where(Activity.start_time >= start)
        if end:
            q = q.where(Activity.start_time < end)
        value = await session.scalar(q)
        return float(value or 0)

    if metric == "training_load_sum":
        q = select(func.coalesce(func.sum(Activity.training_load), 0.0)).where(
            Activity.user_id == user_id
        )
        if start:
            q = q.where(Activity.start_time >= start)
        if end:
            q = q.where(Activity.start_time < end)
        value = await session.scalar(q)
        return float(value or 0)

    if metric == "intensity_minutes":
        q = select(
            func.coalesce(func.sum(Activity.duration_s), 0)
        ).where(
            Activity.user_id == user_id,
            Activity.avg_hr.is_not(None),
            Activity.avg_hr >= MODERATE_HR,
        )
        if start:
            q = q.where(Activity.start_time >= start)
        if end:
            q = q.where(Activity.start_time < end)
        total_s = await session.scalar(q)
        return float(total_s or 0) / 60.0

    if metric == "steps":
        q = select(func.coalesce(func.sum(DailyBiometric.steps), 0)).where(
            DailyBiometric.user_id == user_id
        )
        if start:
            q = q.where(DailyBiometric.date >= start.date() if isinstance(start, datetime) else start)
        if end:
            q = q.where(DailyBiometric.date < end.date() if isinstance(end, datetime) else end)
        value = await session.scalar(q)
        return float(value or 0)

    if metric == "sleep_score_avg":
        q = select(func.avg(SleepSession.sleep_score)).where(
            SleepSession.user_id == user_id,
            SleepSession.sleep_score.is_not(None),
        )
        if start:
            q = q.where(SleepSession.local_date >= start.date())
        if end:
            q = q.where(SleepSession.local_date < end.date())
        value = await session.scalar(q)
        return float(value) if value is not None else None

    if metric == "5k_time_s":
        q = (
            select(Activity.duration_s)
            .where(
                Activity.user_id == user_id,
                Activity.distance_m.is_not(None),
                Activity.distance_m >= _FIVE_K_LOW_M,
                Activity.distance_m <= _FIVE_K_HIGH_M,
                Activity.duration_s.is_not(None),
            )
            .order_by(Activity.duration_s.asc())
            .limit(1)
        )
        if start:
            q = q.where(Activity.start_time >= start)  # type: ignore[call-arg]
        best = await session.scalar(q)
        return float(best) if best else None

    return None


_SORT_ASC = {"5k_time_s"}


async def leaderboard(
    session: AsyncSession, challenge: Challenge, now: datetime
) -> dict:
    start, end = period_window(challenge, now)
    member_ids = await _member_ids(session, challenge.id)
    entries: list[dict] = []
    for user_id in member_ids:
        user = await session.get(User, user_id)
        value = await compute_metric(
            session, user_id, challenge.metric, start=start, end=end
        )
        entries.append(
            {
                "user_id": user_id,
                "display_name": user.name if user else f"user {user_id}",
                "value": value,
            }
        )
    entries.sort(
        key=lambda e: (
            e["value"] is None,  # users without data rank last
            e["value"] if e["value"] is not None else 0,
        ),
        reverse=challenge.metric not in _SORT_ASC,
    )
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank if entry["value"] is not None else None
    return {
        "challenge_id": challenge.id,
        "name": challenge.name,
        "metric": challenge.metric,
        "period": challenge.period,
        "entries": entries,
    }


async def global_records(
    session: AsyncSession, metric: str, *, limit: int = 10
) -> list[dict]:
    """All-time leaderboard across ALL accounts (the 'who holds the record'
    surface — independent of any challenge)."""
    rows = await session.scalars(select(User.id).order_by(User.id))
    entries = []
    for user_id in rows.all():
        user = await session.get(User, user_id)
        v = await compute_metric(session, user_id, metric, start=None, end=None)
        if v is not None:
            entries.append(
                {
                    "user_id": user_id,
                    "display_name": user.name if user else f"user {user_id}",
                    "value": v,
                }
            )
    entries.sort(
        key=lambda e: e["value"], reverse=metric not in _SORT_ASC
    )
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return entries[:limit]
