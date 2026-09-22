"""Whoop sync driver: fetch collections -> raw_ingest -> normalize.

Same shape as the Garmin driver (sync_user_garmin): the caller owns commit
and escalation bookkeeping. Backfill (last_synced_at is None) walks Whoop
from 2012 (Whoop's origin — the API returns only what exists) to now;
incremental syncs re-fetch with a 1-day overlap so late-scored sleep and
recovery rows are picked up (upserts make the overlap free of side effects).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.garmin.sync import SyncReport
from app.connectors.whoop.fetch import SOURCE, store_raw
from app.connectors.whoop.normalize import NormalizationError, normalize_raw_row
from app.connectors.whoop.type_map import build_discipline_index
from app.models.integration import Integration, RawIngest
from app.models.user import User

logger = logging.getLogger("connectors.whoop.sync")

_WHOOP_ORIGIN = datetime(2012, 1, 1, tzinfo=UTC)
_INCREMENTAL_OVERLAP = timedelta(days=1)


async def sync_user_whoop(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,  # LiveWhoopClient or a fixture double
    *,
    now: datetime | None = None,
    page_delay_s: float | None = None,
) -> SyncReport:
    now = now or datetime.now(UTC)
    tz = ZoneInfo(user.timezone)
    backfill = integration.last_synced_at is None
    report = SyncReport(user_id=user.id, mode="backfill" if backfill else "incremental")
    if page_delay_s is not None:
        client.page_delay_s = page_delay_s

    start = _WHOOP_ORIGIN if backfill else (
        integration.last_synced_at.astimezone(UTC) - _INCREMENTAL_OVERLAP
    )
    report.activity_pages += 1

    # -- raw pulls (each collection independent: one failing collection
    #    must not abort the others; the failure is recorded and re-raised
    #    only after the rest have run)
    pulls = (
        ("sleep", client.fetch_sleeps(start, None)),
        ("recovery", client.fetch_recoveries(start, None)),
        ("cycle", client.fetch_cycles(start, None)),
        ("workout", client.fetch_workouts(start, None)),
    )
    errors: list[str] = []
    for payload_type, coro in pulls:
        try:
            records = await coro
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            logger.warning("whoop sync: %s pull failed: %s", payload_type, exc)
            errors.append(f"{payload_type}: {exc}")
            continue
        for record in records:
            if not isinstance(record, dict) or not record:
                continue
            await store_raw(session, user.id, payload_type, record, fetched_at=now)
            report.raw_rows_stored += 1
        report.notes.append(f"{payload_type}: {len(records)} records")
        report.wellness_days += len(records)

    # -- body measurement (single object, best-effort)
    try:
        body = await client.fetch_body_measurement()
        if body:
            await store_raw(session, user.id, "body_measurement", body, fetched_at=now)
            report.raw_rows_stored += 1
    except Exception as exc:  # noqa: BLE001
        errors.append(f"body_measurement: {exc}")

    # -- normalize pending (per-row savepoints: a malformed payload rolls
    #    back alone and stays processed=false)
    discipline_index = await build_discipline_index(session)
    rows = (
        await session.scalars(
            select(RawIngest)
            .where(
                RawIngest.user_id == user.id,
                RawIngest.source == SOURCE,
                RawIngest.processed.is_(False),
            )
            .order_by(RawIngest.id)
        )
    ).all()
    totals = NormalizerStats()
    for row in rows:
        try:
            async with session.begin_nested():
                stats = NormalizerStats()
                await normalize_raw_row(
                    session, row, row.raw_json, tz, discipline_index, stats
                )
                totals.activities_upserted += stats.activities_upserted
                totals.sleep_upserted += stats.sleep_upserted
                totals.hrv_upserted += stats.hrv_upserted
                totals.biometrics_upserted += stats.biometrics_upserted
                totals.discipline_fallbacks.extend(stats.discipline_fallbacks)
                row.processed = True
        except NormalizationError as exc:
            logger.warning(
                "whoop normalizer: raw row %s (%s) stays unprocessed: %s",
                row.id, row.payload_type, exc,
            )
            report.raw_rows_unprocessed += 1
            totals.unprocessed.append(row.id)
    report.stats = totals
    if totals.discipline_fallbacks:
        report.notes.append(
            "discipline fallback used for: "
            + ", ".join(sorted(set(totals.discipline_fallbacks)))
        )
    if errors:
        report.notes.append("collection errors: " + "; ".join(errors))

    integration.last_synced_at = now
    return report


async def run_user_sync_with_escalation(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    **kwargs: Any,
) -> SyncReport | None:
    """Delegates to the shared escalation wrapper (§21: sync_failure alerts
    every 3rd consecutive failure, success resets the counter)."""
    from app.connectors.escalation import run_sync_with_escalation

    return await run_sync_with_escalation(
        session,
        user,
        integration,
        sync_user_whoop,
        client,
        source_label="whoop",
        **kwargs,
    )
