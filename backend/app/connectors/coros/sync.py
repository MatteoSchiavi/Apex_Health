"""Fetch the selected COROS MCP tool result, store raw, then normalize."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.coros.client import SOURCE
from app.connectors.coros.normalize import NormalizationError, normalize_activity
from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.garmin.sync import SyncReport
from app.models.integration import Integration, RawIngest
from app.models.user import User

logger = logging.getLogger("connectors.coros.sync")


async def sync_user_coros(
    session: AsyncSession,
    user: User,
    integration: Integration,
    client: Any,
    *,
    now: datetime | None = None,
    page_delay_s: float | None = None,
) -> SyncReport:
    del page_delay_s  # The MCP server owns paging and rate limits for its tool.
    now = now or datetime.now(UTC)
    backfill = integration.last_synced_at is None
    report = SyncReport(user_id=user.id, mode="backfill" if backfill else "incremental")
    result = await client.fetch_activities()
    records = _activities_from_result(result)
    if records is None:
        session.add(
            RawIngest(
                user_id=user.id,
                source=SOURCE,
                payload_type="mcp_tool_result",
                raw_json=result,
                processed=False,
            )
        )
        await session.commit()
        raise RuntimeError("COROS MCP result does not match the configured activity contract")

    report.activity_pages = 1
    report.activities_seen = len(records)
    for record in records:
        if not isinstance(record, dict) or not record:
            report.raw_rows_unprocessed += 1
        session.add(
            RawIngest(
                user_id=user.id,
                source=SOURCE,
                payload_type="activity" if isinstance(record, dict) else "unrecognized_activity",
                raw_json=record,
                processed=False,
                fetched_at=now,
            )
        )
        report.raw_rows_stored += 1
    await session.flush()

    rows = (
        await session.scalars(
            select(RawIngest)
            .where(
                RawIngest.user_id == user.id,
                RawIngest.source == SOURCE,
                RawIngest.processed.is_(False),
                RawIngest.payload_type == "activity",
            )
            .order_by(RawIngest.id)
        )
    ).all()
    stats = NormalizerStats()
    discipline_index = await _discipline_index(session)
    for row in rows:
        try:
            async with session.begin_nested():
                await normalize_activity(
                    session,
                    row,
                    row.raw_json,
                    ZoneInfo(user.timezone),
                    discipline_index,
                    stats,
                )
                row.processed = True
        except NormalizationError as exc:
            logger.warning("coros normalizer: raw row %s stays unprocessed: %s", row.id, exc)
            report.raw_rows_unprocessed += 1
            stats.unprocessed.append(row.id)
    report.stats = stats
    if stats.activities_upserted + stats.activities_merged == 0:
        # Keep raw data available for contract review, but do not report a
        # successful sync or advance the incremental checkpoint.
        await session.commit()
        raise RuntimeError("COROS MCP returned no valid canonical activities")

    integration.last_synced_at = now
    report.notes.append(f"activities: {len(records)} records from configured MCP tool")
    if stats.discipline_fallbacks:
        report.notes.append(
            "discipline fallback used for: "
            + ", ".join(sorted(set(stats.discipline_fallbacks)))
        )
    return report


def _activities_from_result(result: dict[str, Any]) -> list[Any] | None:
    """Read the documented structuredContent.activities MCP contract."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("activities"), list):
        return structured["activities"]
    # MCP servers that cannot return structuredContent may return a single
    # JSON text block. Only accept the same contract shape.
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            try:
                decoded = json.loads(item["text"])
            except ValueError:
                continue
            if isinstance(decoded, dict) and isinstance(decoded.get("activities"), list):
                return decoded["activities"]
    return None


async def _discipline_index(session: AsyncSession) -> dict[str, int]:
    from app.models.activity import Discipline

    rows = await session.execute(select(Discipline.name, Discipline.id))
    return {str(name).lower(): int(identifier) for name, identifier in rows.all()}


async def run_user_sync_with_coros(
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
        sync_user_coros,
        client,
        source_label="coros",
        **kwargs,
    )
