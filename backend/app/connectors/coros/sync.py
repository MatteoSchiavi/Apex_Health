"""COROS sync driver skeleton — inert until the owner's developer access is
approved. The driver pulls paged activity summaries + details into raw_ingest
and leaves normalization to the pipeline that lands with real payloads
(shapes cannot be verified pre-approval — no speculative schema code)."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.coros.client import SOURCE
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
    now = now or datetime.now(UTC)
    report = SyncReport(
        user_id=user.id,
        mode="backfill" if integration.last_synced_at is None else "incremental",
    )
    report.notes.append(
        "coros: doc-first shell — driver runs only after developer approval"
    )

    # Paged summary pull; every response lands raw-first. Details are fetched
    # per sport_id once summaries parse in production.
    page = 1
    seen = 0
    while True:
        payload = await client.fetch_sports_list(page=page)
        items = payload.get("data") or {}
        rows = items.get("data_list") if isinstance(items, dict) else None
        if not rows:
            break
        for record in rows:
            if not isinstance(record, dict) or not record:
                continue
            session.add(
                RawIngest(
                    user_id=user.id,
                    source=SOURCE,
                    payload_type="sports_list",
                    raw_json=record,
                    processed=False,
                )
            )
            report.raw_rows_stored += 1
            seen += 1
        page += 1
        if page > 100:  # hard stop — pacing/limit guard
            break

    integration.last_synced_at = now
    return report


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
