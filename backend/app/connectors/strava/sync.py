"""Strava sync driver: fetch activity pages -> raw_ingest -> normalize.

Backfill (last_synced_at is None) fetches ALL history (after=0); incremental
syncs use after=last_synced_at-2h overlap. Pages are paced (rate limits).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.garmin.sync import SyncReport
from app.connectors.strava.fetch import SOURCE, store_raw
from app.connectors.strava.normalize import NormalizationError, normalize_raw_row
from app.connectors.strava.type_map import build_discipline_index
from app.models.integration import Integration, RawIngest
from app.models.user import User

logger = logging.getLogger("connectors.strava.sync")

_INCREMENTAL_OVERLAP = timedelta(hours=2)


async def sync_user_strava(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,  # LiveStravaClient or a fixture double
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

    after_epoch = (
        0
        if backfill
        else int(
            (integration.last_synced_at.astimezone(UTC) - _INCREMENTAL_OVERLAP).timestamp()
        )
    )
    report.activity_pages += 1
    try:
        activities = await client.fetch_activities(after_epoch=after_epoch)
    except Exception as exc:  # noqa: BLE001 - single collection, raise through
        logger.warning("strava sync: activities pull failed: %s", exc)
        raise
    for record in activities:
        if not isinstance(record, dict) or not record:
            continue
        await store_raw(session, user.id, "activity_summary", record, fetched_at=now)
        report.raw_rows_stored += 1
    report.activities_seen = len(activities)
    report.notes.append(f"activities: {len(activities)} records")

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
                await normalize_raw_row(session, row, row.raw_json, tz, discipline_index, stats)
                totals.activities_upserted += stats.activities_upserted
                totals.discipline_fallbacks.extend(stats.discipline_fallbacks)
                row.processed = True
        except NormalizationError as exc:
            logger.warning(
                "strava normalizer: raw row %s stays unprocessed: %s", row.id, exc
            )
            report.raw_rows_unprocessed += 1
            totals.unprocessed.append(row.id)
    report.stats = totals
    if totals.discipline_fallbacks:
        report.notes.append(
            "discipline fallback used for: "
            + ", ".join(sorted(set(totals.discipline_fallbacks)))
        )

    integration.last_synced_at = now
    return report


async def run_user_sync_with_escalation(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    **kwargs: Any,
) -> SyncReport | None:
    from app.connectors.escalation import run_sync_with_escalation

    return await run_sync_with_escalation(
        session,
        user,
        integration,
        sync_user_strava,
        client,
        source_label="strava",
        **kwargs,
    )
