"""Device priority law — the merge engine behind main + secondary devices.

Owner rule (2026-09): a user designates ONE connected integration as the
MAIN device. Resolution:

1. **Vitals / sleep / daily metrics** — the main device wins wherever it has
   data. A secondary device fills a day/field ONLY when the main device has
   nothing for it (no value at all, not merely a different value).
2. **Activities** — when the main device recorded NO activity overlapping a
   timeframe and a secondary DID, the secondary's activity stands for that
   window (e.g. Whoop logged the gym session the watch stayed home for).
   When both recorded the same effort, the main device's row wins and the
   secondary's is kept only as a source link (dedupe, never duplicate).

Laws honoured:
- Canonical columns only ever carry Garmin-canonical units (annotation law).
  Whoop/Oura/COROS-specific quantities stay in `source_metrics` JSONB.
- Rows are never forked: resolution happens at INGEST time (connectors call
  `should_write_vitals` / `resolve_activity_winner`) and every decision is
  re-derivable, so changing the main device + a range recompute rebuilds
  the same view. No merged-copy tables.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import Integration
from app.models.user import User
from app.models.wellness import DailyBiometric

logger = logging.getLogger("app.services.device_merge")

# Overlap window for "same physical effort" de-duplication: two activities
# from different providers count as the SAME session when their start times
# sit within this tolerance and durations are within 20% of each other.
SAME_EFFORT_START_TOLERANCE = timedelta(minutes=10)
SAME_EFFORT_DURATION_REL = 0.20

# Providers ordered by fallback priority when the user has not picked a main
# device (first-connected-wins legacy rule uses this ordering as tiebreak).
FALLBACK_PRIORITY = ("garmin", "whoop", "oura", "coros", "strava")


@dataclass(frozen=True)
class MergeDecision:
    write: bool
    reason: str
    winner_source: str | None = None
    winner_activity_id: int | None = None


async def _integrations(session: AsyncSession, user_id: int) -> dict[str, Integration]:
    rows = (
        await session.scalars(
            select(Integration).where(
                Integration.user_id == user_id, Integration.status == "active"
            )
        )
    ).all()
    return {i.provider: i for i in rows}


async def main_provider(session: AsyncSession, user: User) -> str | None:
    """The user's declared main device, or the fallback pick (garmin first,
    else the highest-priority active integration)."""
    if user.main_integration_id is not None:
        integration = await session.get(Integration, user.main_integration_id)
        if integration is not None and integration.user_id == user.id:
            return integration.provider
    integrations = await _integrations(session, user.id)
    for provider in FALLBACK_PRIORITY:
        if provider in integrations:
            return provider
    return next(iter(integrations), None)


async def should_write_vitals(
    session: AsyncSession,
    user: User,
    table: str,
    day,
    incoming_provider: str,
    has_value: bool,
) -> MergeDecision:
    """Ingest gate for daily-grain wellness rows (daily_biometrics today).

    `has_value=False` (an empty payload) NEVER overwrites anything regardless
    of priority — a gap in the main device is not permission to backfill it
    with a conflicting metric; only a genuine reading from a secondary fills
    a genuinely missing day/field.
    """
    if not has_value:
        return MergeDecision(False, "empty payload never overwrites")

    main = await main_provider(session, user)
    if main is None or incoming_provider == main:
        return MergeDecision(True, "main device (or no main declared yet)", incoming_provider)

    # Secondary provider: write only fields/day the main device left empty.
    if table == "daily_biometrics":
        row = (
            await session.scalars(
                select(DailyBiometric).where(
                    DailyBiometric.user_id == user.id, DailyBiometric.date == day
                )
            )
        ).first()
        if row is None:
            return MergeDecision(True, "secondary fills missing day", incoming_provider)
        return MergeDecision(
            False,
            f"main device ({main}) already holds data for {day}",
            main,
        )

    # Unknown table → conservative default: main wins.
    return MergeDecision(False, f"unmerged table {table}: main ({main}) wins", main)


async def resolve_activity_winner(
    session: AsyncSession,
    user: User,
    start_time: datetime,
    duration_s: int,
    incoming_provider: str,
) -> MergeDecision:
    """Decide whether an incoming activity row should be written, merged as a
    source link onto an existing row, or skipped.

    - Same-effort collision with the MAIN device → main wins; caller should
      attach the incoming row as an ActivitySourceLink on the winner (dedupe).
    - Same-effort collision with a SECONDARY → incoming (main) replaces the
      secondary's canonical columns; the secondary keeps its source link.
    - No collision → write (secondary activity ALSO writes: it covers a
      window the main device missed — the gym-session rule).
    """
    window_start = start_time - SAME_EFFORT_START_TOLERANCE
    window_end = start_time + SAME_EFFORT_START_TOLERANCE + timedelta(seconds=duration_s)
    candidates = (
        await session.scalars(
            select(Activity).where(
                and_(
                    Activity.user_id == user.id,
                    Activity.start_time >= window_start - timedelta(hours=1),
                    Activity.start_time <= window_end,
                )
            )
        )
    ).all()

    def _same_effort(a: Activity) -> bool:
        delta = abs((a.start_time - start_time).total_seconds())
        if delta > SAME_EFFORT_START_TOLERANCE.total_seconds():
            return False
        d0, d1 = a.duration_s, duration_s
        if d0 <= 0 or d1 <= 0:
            return True
        return abs(d0 - d1) / max(d0, d1) <= SAME_EFFORT_DURATION_REL

    main = await main_provider(session, user)
    for a in candidates:
        if not _same_effort(a):
            continue
        existing = (
            await session.scalars(
                select(ActivitySourceLink.source)
                .where(ActivitySourceLink.activity_id == a.id)
                .order_by(ActivitySourceLink.id)
            )
        ).all()
        existing_source = existing[0] if existing else "unknown"
        if existing_source == main or main is None:
            # Incoming is secondary or same-provider refresh: dedupe onto main.
            if incoming_provider == main:
                return MergeDecision(True, "main device re-ingest (upsert)", main, None)
            return MergeDecision(
                False,
                f"main device ({main}) already recorded this effort",
                main,
                a.id,
            )
        # Existing row belongs to a secondary; incoming is main → take over.
        if incoming_provider == main:
            return MergeDecision(True, "main overrides secondary's window", main, a.id)
    return MergeDecision(True, "no collision", incoming_provider, None)


def field_merge(
    main_value,
    secondary_value,
) -> tuple[object, str]:
    """Column-level fill rule used by backfills/recomputes: main value when
    present, else the secondary's. Returns (value, source)."""
    if main_value is not None:
        return main_value, "main"
    if secondary_value is not None:
        return secondary_value, "secondary"
    return None, "none"


def utc_now() -> datetime:
    return datetime.now(UTC)
