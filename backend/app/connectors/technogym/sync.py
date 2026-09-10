"""Technogym sync orchestration (§11a, §6.3 backfill, §19 cadence, §21).

Two-stage flow per §3: FETCH stores every payload in raw_ingest
(processed=false), then NORMALIZE consumes unprocessed raw rows with per-row
savepoints — a malformed payload stays unprocessed and replayable instead of
wedging the sync or losing history.

Modes (§6.3, same contract as the Garmin connector):
- backfill   (integrations.last_synced_at IS NULL): walk every page of the
  workout history — the product's value is long-term trend analysis, so the
  full available history is pulled, not a recent window.
- incremental (last_synced_at set): newest-first pages, stopping at the
  boundary; overlap is absorbed by idempotent upserts.

Every remote call is paced (§19 note: same ban-risk reasoning as Garmin).
Machine-record detail (get_workout_detail) is fetched for newly seen workouts
and stored raw — normalized columns come from the workout row; the detail
rows keep the richer machine data (resistance/incline curves) queryable via
raw_ingest, exactly what §12's "richer source per field" reads.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.technogym import fetch
from app.connectors.technogym.normalize import (
    NormalizationError,
    NormalizerStats,
    normalize_raw_row,
)
from app.models.activity import ActivitySourceLink, Discipline
from app.models.integration import Integration, RawIngest
from app.models.user import User

logger = logging.getLogger("connectors.technogym.sync")

SOURCE = fetch.SOURCE


class SyncError(Exception):
    pass


@dataclass
class SyncReport:
    user_id: int
    mode: str  # "backfill" | "incremental"
    workout_pages: int = 0
    workouts_seen: int = 0
    new_workouts: int = 0
    details_fetched: int = 0
    raw_rows_stored: int = 0
    raw_rows_unprocessed: int = 0
    stats: NormalizerStats | None = None
    notes: list[str] = field(default_factory=list)


async def _pace(delay_s: float) -> None:
    if delay_s > 0:
        await asyncio.sleep(delay_s)


def _start_of(workout: dict[str, Any]) -> datetime | None:
    """Best-effort parse of a workout's startDate for the incremental
    boundary — parse problems are the normalizer's to report."""
    value = workout.get("startDate")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


# ------------------------------------------------------------------ fetch


async def fetch_workouts(
    session: AsyncSession,
    user_id: int,
    client: Any,
    *,
    since: datetime | None,
    page_size: int,
    delay_s: float,
    report: SyncReport,
) -> list[str]:
    """Store workout payloads as raw rows. Returns ids of NEWLY seen workouts
    (no source link yet) — machine detail is only fetched for those.

    Backfill (since=None) walks every page (§6.3). Incremental walks
    newest-first pages and stops once a page's oldest item is at or before
    `since` — upserts make the boundary overlap harmless."""
    new_ids: list[str] = []
    start = 0
    while True:
        page = await client.get_workouts(start, page_size)
        if not page:
            break
        report.workout_pages += 1
        oldest_start: datetime | None = None
        for workout in page:
            report.workouts_seen += 1
            await fetch.store_raw(session, user_id, fetch.PAYLOAD_WORKOUT, workout)
            report.raw_rows_stored += 1

            external_id = str(workout.get("id"))
            link = await session.scalar(
                select(ActivitySourceLink).where(
                    ActivitySourceLink.source == SOURCE,
                    ActivitySourceLink.external_id == external_id,
                )
            )
            if link is None:
                new_ids.append(external_id)

            parsed = _start_of(workout)
            if parsed is not None and (oldest_start is None or parsed < oldest_start):
                oldest_start = parsed

        if len(page) < page_size:
            break  # short page -> history exhausted
        if since is not None and oldest_start is not None and oldest_start <= since:
            break  # boundary reached; overlap is absorbed by idempotent upserts
        start += len(page)
        await _pace(delay_s)
    report.new_workouts = len(new_ids)
    return new_ids


async def fetch_details(
    session: AsyncSession,
    user_id: int,
    client: Any,
    workout_ids: list[str],
    delay_s: float,
    report: SyncReport,
) -> None:
    """Store per-workout machine detail as raw rows (context carried in
    payload_type, raw bytes untouched). A detail failure never fails the
    sync — the workout row already normalized the session."""
    for external_id in workout_ids:
        try:
            detail = await client.get_workout_detail(external_id)
        except Exception as exc:
            logger.warning(
                "technogym detail fetch failed for workout %s: %s", external_id, exc
            )
            await _pace(delay_s)
            continue
        if not detail:
            await _pace(delay_s)
            continue
        await fetch.store_raw(
            session, user_id, f"{fetch.PAYLOAD_WORKOUT_DETAIL}:{external_id}", detail
        )
        report.raw_rows_stored += 1
        report.details_fetched += 1
        await _pace(delay_s)


# --------------------------------------------------------------- normalize


async def normalize_pending(
    session: AsyncSession,
    user_id: int,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    report: SyncReport,
) -> None:
    """Consume unprocessed raw rows for this user+source with per-row
    savepoints: a malformed payload rolls back alone, stays processed=false,
    and the pass continues (§3: parser breaks, history doesn't)."""
    rows = (
        (
            await session.scalars(
                select(RawIngest)
                .where(
                    RawIngest.user_id == user_id,
                    RawIngest.source == SOURCE,
                    RawIngest.processed.is_(False),
                )
                .order_by(RawIngest.id)
            )
        )
        .all()
    )

    totals = NormalizerStats()
    for row in rows:
        try:
            async with session.begin_nested():
                stats = await normalize_raw_row(session, row, tz, discipline_index)
                totals.activities_upserted += stats.activities_upserted
                totals.discipline_fallbacks.extend(stats.discipline_fallbacks)
        except NormalizationError as exc:
            logger.warning(
                "technogym normalizer: raw row %s (%s) stays unprocessed: %s",
                row.id,
                row.payload_type,
                exc,
            )
            report.raw_rows_unprocessed += 1
            totals.unprocessed.append(row.id)
    report.stats = totals
    if totals.discipline_fallbacks:
        report.notes.append(
            "discipline fallback used for: " + ", ".join(sorted(totals.discipline_fallbacks))
        )


# ------------------------------------------------------------------ driver


async def sync_user_technogym(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    *,
    page_size: int,
    page_delay_s: float,
    now: datetime | None = None,
) -> SyncReport:
    """One full sync pass for one user. Caller owns commit and escalation
    bookkeeping (§21 lives in run_user_sync_with_escalation)."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(user.timezone)
    backfill = integration.last_synced_at is None
    report = SyncReport(user_id=user.id, mode="backfill" if backfill else "incremental")

    rows = await session.execute(select(Discipline.name, Discipline.id))
    discipline_index = dict(rows.all())

    since = None if backfill else integration.last_synced_at
    new_ids = await fetch_workouts(
        session,
        user.id,
        client,
        since=since,
        page_size=page_size,
        delay_s=page_delay_s,
        report=report,
    )
    await fetch_details(session, user.id, client, new_ids, page_delay_s, report)
    await normalize_pending(session, user.id, tz, discipline_index, report)

    integration.last_synced_at = now
    return report


async def run_user_sync_with_escalation(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    *,
    page_size: int,
    page_delay_s: float,
    now: datetime | None = None,
) -> SyncReport | None:
    """§21: a failing sync increments consecutive_failures; every third
    consecutive failure fires a sync_failure alert. Success resets the
    counter. Raises nothing — returns the report, or None on failure."""
    from app.connectors.escalation import run_sync_with_escalation

    return await run_sync_with_escalation(
        session,
        user,
        integration,
        sync_user_technogym,
        client,
        source_label="Technogym",
        page_size=page_size,
        page_delay_s=page_delay_s,
        now=now,
    )
