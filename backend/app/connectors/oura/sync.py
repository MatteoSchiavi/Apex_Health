"""Oura sync driver: fetch collections -> raw_ingest -> normalize.

Same shape as the Whoop driver: caller owns commit and escalation
bookkeeping. Backfill walks from Oura's consumer origin (the API simply
returns what exists for the account); incremental syncs re-fetch with a
1-day overlap so late-scored sleep rows are picked up (upserts make the
overlap free of side effects).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.garmin.sync import SyncReport
from app.connectors.oura.fetch import SOURCE, store_raw
from app.connectors.oura.normalize import NormalizationError, normalize_raw_row
from app.models.integration import Integration, RawIngest
from app.models.user import User

logger = logging.getLogger("connectors.oura.sync")

_OURA_ORIGIN = datetime(2015, 1, 1, tzinfo=UTC)
_INCREMENTAL_OVERLAP = timedelta(days=1)


async def sync_user_oura(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,  # LiveOuraClient (OuraClient) or a fixture double
    *,
    now: datetime | None = None,
    page_delay_s: float | None = None,
) -> SyncReport:
    now = now or datetime.now(UTC)
    backfill = integration.last_synced_at is None
    report = SyncReport(user_id=user.id, mode="backfill" if backfill else "incremental")
    if page_delay_s is not None:
        client.page_delay_s = page_delay_s

    start = _OURA_ORIGIN if backfill else (
        integration.last_synced_at.astimezone(UTC) - _INCREMENTAL_OVERLAP
    )
    end = now

    pulls = (
        ("daily_sleep", client.fetch_daily_sleep(start, end)),
        ("sleep", client.fetch_sleep_periods(start, end)),
        ("heartrate", client.fetch_heartrate(start, end)),
    )
    errors: list[str] = []
    for payload_type, coro in pulls:
        try:
            records = await coro
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            logger.warning("oura sync: %s pull failed: %s", payload_type, exc)
            errors.append(f"{payload_type}: {exc}")
            continue
        for record in records:
            if not isinstance(record, dict) or not record:
                continue
            await store_raw(session, user.id, payload_type, record, fetched_at=now)
            report.raw_rows_stored += 1
        report.notes.append(f"{payload_type}: {len(records)} records")
        report.wellness_days += len(records)

    try:
        personal = await client.fetch_personal_info()
        if personal:
            await store_raw(session, user.id, "personal_info", personal, fetched_at=now)
            report.raw_rows_stored += 1
    except Exception as exc:  # noqa: BLE001
        errors.append(f"personal_info: {exc}")

    # -- normalize pending (per-row savepoints) -------------------------------
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
    tz = ZoneInfo(user.timezone)
    totals = NormalizerStats()
    for row in rows:
        try:
            async with session.begin_nested():
                stats = NormalizerStats()
                await normalize_raw_row(session, row, row.raw_json, tz, stats)
                totals.sleep_upserted += stats.sleep_upserted
                totals.hrv_upserted += stats.hrv_upserted
                totals.biometrics_upserted += stats.biometrics_upserted
                row.processed = True
        except NormalizationError as exc:
            logger.warning(
                "oura normalizer: raw row %s (%s) stays unprocessed: %s",
                row.id, row.payload_type, exc,
            )
            report.raw_rows_unprocessed += 1
            totals.unprocessed.append(row.id)
    report.stats = totals
    if errors:
        report.notes.append("collection errors: " + "; ".join(errors))

    integration.last_synced_at = now
    return report


async def run_user_sync_with_oura(
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
        sync_user_oura,
        client,
        source_label="oura",
        **kwargs,
    )
