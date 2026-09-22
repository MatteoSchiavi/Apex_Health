"""Garmin sync orchestration (§6.3 backfill, §19 cadence, §21 escalation).

Two-stage flow per §3: FETCH stores every payload in raw_ingest (processed=
false), then NORMALIZE consumes unprocessed raw rows into typed tables with
per-row savepoints — a malformed payload stays unprocessed and replayable
instead of wedging the sync or losing history.

Modes (§6.3):
- backfill  (integrations.last_synced_at IS NULL): full paginated activity
  history; wellness walked backwards day by day until a sustained empty gap
  (the source's real history depth), not an arbitrary recent window.
- incremental (last_synced_at set): activity pages newest-first, stopping at
  the boundary; wellness from the last synced local day (minus one, so
  overnight sessions that completed after the last run are re-fetched) to
  today.

Every remote call is paced (§19 note: an unofficial client polled
continuously raises ban risk; pagination respects rate limits).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin import fetch
from app.connectors.garmin.normalize import (
    NormalizationError,
    NormalizerStats,
    normalize_raw_row,
    _parse_gmt_datetime,
)
from app.models.activity import ActivitySourceLink, Discipline
from app.models.integration import Integration, RawIngest
from app.models.user import User
from app.models.wellness import SleepSession

logger = logging.getLogger("connectors.garmin.sync")

SOURCE = fetch.SOURCE


class SyncError(Exception):
    pass


@dataclass
class SyncReport:
    user_id: int
    mode: str  # "backfill" | "incremental"
    activity_pages: int = 0
    activities_seen: int = 0
    new_activities: int = 0
    streams_fetched: int = 0
    wellness_days: int = 0
    raw_rows_stored: int = 0
    raw_rows_unprocessed: int = 0
    stats: NormalizerStats | None = None
    notes: list[str] = field(default_factory=list)


async def _pace(delay_s: float) -> None:
    if delay_s > 0:
        await asyncio.sleep(delay_s)


def _payload_date_label(day: date) -> str:
    return day.isoformat()


# ------------------------------------------------------------------ fetch


async def fetch_activities(
    session: AsyncSession,
    user_id: int,
    client: Any,
    *,
    since: datetime | None,
    page_size: int,
    delay_s: float,
    report: SyncReport,
    tz: ZoneInfo | None = None,
    discipline_index: dict[str, int] | None = None,
    checkpoint: bool = False,
) -> list[int]:
    """Store activity summaries as raw rows. Returns ids of NEWLY seen
    activities (no source link yet) — streams are only fetched for those.

    Backfill (since=None) walks every page (§6.3). Incremental walks
    newest-first pages and stops once a page's oldest item is at or before
    `since` — upserts make the boundary overlap harmless.

    checkpoint=True (live backfills): after every page, normalize what is
    pending and COMMIT — a killed multi-hour walk then resumes without
    duplicating work, because already-normalized activities carry source
    links and are skipped on the re-walk.
    """
    new_ids: list[int] = []
    start = 0
    while True:
        page = await client.get_activities(start, page_size)
        if not page:
            break
        report.activity_pages += 1
        oldest_start: datetime | None = None
        for summary in page:
            report.activities_seen += 1
            external_id = str(summary.get("activityId"))
            link = await session.scalar(
                select(ActivitySourceLink).where(
                    ActivitySourceLink.source == SOURCE,
                    ActivitySourceLink.external_id == external_id,
                )
            )
            if link is not None:
                if checkpoint:
                    # Checkpoint resume: this activity is already normalized —
                    # re-storing its raw row would only duplicate work.
                    try:
                        oldest_start = _parse_gmt_datetime(
                            summary.get("startTimeGMT"), "startTimeGMT"
                        )
                    except Exception:  # parse problems are the normalizer's to report
                        oldest_start = None
                    continue
                # Incremental default (raw-first audit): the overlap window is
                # re-recorded in raw_ingest; upserts dedupe the normalized
                # tables and the activity is NOT treated as new.
                await fetch.store_raw(
                    session, user_id, fetch.PAYLOAD_ACTIVITY_SUMMARY, summary
                )
                report.raw_rows_stored += 1
                try:
                    oldest_start = _parse_gmt_datetime(
                        summary.get("startTimeGMT"), "startTimeGMT"
                    )
                except Exception:  # parse problems are the normalizer's to report
                    oldest_start = None
                continue
            await fetch.store_raw(
                session, user_id, fetch.PAYLOAD_ACTIVITY_SUMMARY, summary
            )
            report.raw_rows_stored += 1
            new_ids.append(external_id)

            try:
                oldest_start = _parse_gmt_datetime(
                    summary.get("startTimeGMT"), "startTimeGMT"
                )
            except Exception:  # parse problems are the normalizer's to report
                oldest_start = None

        if checkpoint and tz is not None and discipline_index is not None:
            await normalize_pending(session, user_id, tz, discipline_index, report)
            await session.commit()

        if len(page) < page_size:
            break  # short page -> history exhausted
        if since is not None and oldest_start is not None and oldest_start <= since:
            break  # boundary reached; overlap is absorbed by idempotent upserts
        start += len(page)
        await _pace(delay_s)
    report.new_activities = len(new_ids)
    return new_ids


async def fetch_streams(
    session: AsyncSession,
    user_id: int,
    client: Any,
    activity_ids: list[str],
    delay_s: float,
    report: SyncReport,
    tz: ZoneInfo | None = None,
    discipline_index: dict[str, int] | None = None,
    checkpoint: bool = False,
) -> None:
    """Store per-activity stream samples as raw rows (context carried in
    payload_type, raw bytes untouched). checkpoint=True normalizes + commits
    after each activity so a killed run never re-fetches streams."""
    for external_id in activity_ids:
        try:
            samples = await client.get_activity_samples(int(external_id))
        except Exception as exc:
            logger.warning(
                "garmin streams fetch failed for activity %s: %s", external_id, exc
            )
            await _pace(delay_s)
            continue
        if not samples:
            await _pace(delay_s)
            continue
        await fetch.store_raw(
            session, user_id, f"{fetch.PAYLOAD_ACTIVITY_STREAMS}:{external_id}", samples
        )
        report.raw_rows_stored += 1
        report.streams_fetched += 1
        if checkpoint and tz is not None and discipline_index is not None:
            await normalize_pending(session, user_id, tz, discipline_index, report)
            await session.commit()
        await _pace(delay_s)


async def fetch_wellness(
    session: AsyncSession,
    user_id: int,
    client: Any,
    tz: ZoneInfo,
    *,
    from_day: date,
    to_day: date,
    delay_s: float,
    empty_gap_days: int,
    report: SyncReport,
    discipline_index: dict[str, int] | None = None,
    checkpoint: bool = False,
) -> None:
    """Store daily wellness payloads (sleep/hrv/stress/stats/body composition).

    Forward mode (incremental): from_day..to_day inclusive.
    Backward mode (backfill, to_day=None semantics handled by caller passing
    an empty to_day): walks from from_day backwards, stopping after
    `empty_gap_days` consecutive days with no data at all — that gap is the
    source's history boundary, not a missed fetch.

    checkpoint=True (live backfills): days that already carry a sleep_session
    are skipped outright (no API calls — the resume walk is fast), and every
    landed day is normalized + committed as it goes.
    """
    backward = from_day > to_day
    step = -1 if backward else 1
    consecutive_empty = 0
    skipped_days = 0
    day = from_day
    while True:
        if checkpoint:
            already = await session.scalar(
                select(SleepSession.id).where(
                    SleepSession.user_id == user_id,
                    SleepSession.local_date == day,
                )
            )
            if already is not None:
                # A prior checkpoint pass normalized this day — skip it. The
                # day had data, so it must not count toward the empty gap.
                consecutive_empty = 0
                skipped_days += 1
                if day == to_day:
                    break
                day = day + timedelta(days=step)
                continue
        payloads = {
            fetch.PAYLOAD_SLEEP: await client.get_sleep_data(day.isoformat()),
            fetch.PAYLOAD_HRV: await client.get_hrv_data(day.isoformat()),
            fetch.PAYLOAD_STRESS: await client.get_stress_data(day.isoformat()),
            fetch.PAYLOAD_STATS: await client.get_stats(day.isoformat()),
            fetch.PAYLOAD_BODY_COMPOSITION: await client.get_body_composition(day.isoformat()),
        }
        day_has_data = False
        for payload_type, payload in payloads.items():
            if not payload:  # upstream returns {} / None outside history
                continue
            day_has_data = True
            stored_type = payload_type
            if payload_type in (fetch.PAYLOAD_STATS, fetch.PAYLOAD_BODY_COMPOSITION):
                stored_type = f"{payload_type}:{day.isoformat()}"
            await fetch.store_raw(session, user_id, stored_type, payload)
            report.raw_rows_stored += 1
        report.wellness_days += 1

        if checkpoint and discipline_index is not None:
            await normalize_pending(session, user_id, tz, discipline_index, report)
            await session.commit()

        if day_has_data:
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if backward and consecutive_empty >= empty_gap_days:
                report.notes.append(
                    f"backfill stopped after {consecutive_empty} empty days "
                    f"(history boundary at {(day + timedelta(days=1)).isoformat()})"
                )
                break

        if day == to_day:
            break
        day = day + timedelta(days=step)
        await _pace(delay_s)
    if skipped_days:
        report.notes.append(
            f"resume walk skipped {skipped_days} already-synced wellness days"
        )


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
                totals.activity_streams_upserted += stats.activity_streams_upserted
                totals.sleep_upserted += stats.sleep_upserted
                totals.hrv_upserted += stats.hrv_upserted
                totals.stress_upserted += stats.stress_upserted
                totals.biometrics_upserted += stats.biometrics_upserted
                totals.discipline_fallbacks.extend(stats.discipline_fallbacks)
        except NormalizationError as exc:
            logger.warning(
                "garmin normalizer: raw row %s (%s) stays unprocessed: %s",
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


async def sync_user_garmin(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    *,
    page_size: int,
    page_delay_s: float,
    empty_gap_days: int,
    now: datetime | None = None,
    checkpoint: bool = False,
) -> SyncReport:
    """One full sync pass for one user. Caller owns commit and escalation
    bookkeeping (§21 lives in run_user_sync_with_escalation).

    checkpoint=True (live multi-hour backfills): normalize + commit per page,
    per stream and per wellness day, and skip already-synced days/activities
    on re-walks — an interrupted backfill resumes instead of restarting from
    zero. Tests keep the default False (single commit at the end)."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(user.timezone)
    backfill = integration.last_synced_at is None
    report = SyncReport(user_id=user.id, mode="backfill" if backfill else "incremental")

    rows = await session.execute(select(Discipline.name, Discipline.id))
    discipline_index = dict(rows.all())

    since = None if backfill else integration.last_synced_at
    new_ids = await fetch_activities(
        session,
        user.id,
        client,
        since=since,
        page_size=page_size,
        delay_s=page_delay_s,
        report=report,
        tz=tz,
        discipline_index=discipline_index,
        checkpoint=checkpoint,
    )
    await fetch_streams(
        session, user.id, client, new_ids, page_delay_s, report,
        tz=tz, discipline_index=discipline_index, checkpoint=checkpoint,
    )

    local_today = now.astimezone(tz).date()
    if backfill:
        await fetch_wellness(
            session,
            user.id,
            client,
            tz,
            from_day=local_today - timedelta(days=1),
            to_day=local_today - timedelta(days=36500),  # loop stops at the gap
            delay_s=page_delay_s,
            empty_gap_days=empty_gap_days,
            report=report,
            discipline_index=discipline_index,
            checkpoint=checkpoint,
        )
    else:
        assert integration.last_synced_at is not None
        from_day = integration.last_synced_at.astimezone(tz).date() - timedelta(days=1)
        await fetch_wellness(
            session,
            user.id,
            client,
            tz,
            from_day=from_day,
            to_day=local_today,
            delay_s=page_delay_s,
            empty_gap_days=empty_gap_days,
            report=report,
            discipline_index=discipline_index,
            checkpoint=checkpoint,
        )

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
    empty_gap_days: int,
    now: datetime | None = None,
    checkpoint: bool = False,
) -> SyncReport | None:
    """§21: a failing sync increments consecutive_failures; every third
    consecutive failure fires a sync_failure alert. Success resets the
    counter. Raises nothing — returns the report, or None on failure.

    (Delegates to the connector-generic helper in app/connectors/escalation.py
    — same behavior, shared with the Technogym connector since Phase 6.)"""
    from app.connectors.escalation import run_sync_with_escalation

    return await run_sync_with_escalation(
        session,
        user,
        integration,
        sync_user_garmin,
        client,
        source_label="Garmin",
        page_size=page_size,
        page_delay_s=page_delay_s,
        empty_gap_days=empty_gap_days,
        now=now,
        checkpoint=checkpoint,
    )
