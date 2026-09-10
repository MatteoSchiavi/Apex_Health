"""Raw ingestion for the weather connector (§17: raw-ingest-before-normalize).

The same law the Garmin/Technogym connectors follow: every upstream payload
lands in `raw_ingest` (processed=false) BEFORE anything is normalized, so an
Open-Meteo schema change breaks the parser, not the history.

Weather payloads are global (keyed by coordinates), not per-user, but
raw_ingest.user_id is NOT NULL — global rows are attributed to the owner
account (the platform is single-owner this round; documented judgment call).
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import RawIngest

logger = logging.getLogger("connectors.weather.fetch")

SOURCE = "open-meteo"

# payload_type values used by the weather connector
PAYLOAD_FORECAST = "forecast"
PAYLOAD_ARCHIVE = "archive"


async def owner_user_id(session: AsyncSession) -> int | None:
    """The owner account id (auth_credentials.role = 'owner')."""
    row = await session.scalar(
        text(
            "SELECT user_id FROM auth_credentials WHERE role = 'owner' "
            "ORDER BY user_id LIMIT 1"
        )
    )
    return int(row) if row is not None else None


async def store_raw(
    session: AsyncSession,
    user_id: int,
    payload_type: str,
    payload: Any,
    *,
    fetched_at: datetime | None = None,
) -> RawIngest:
    """Persist one raw Open-Meteo payload (mirrors the Garmin connector's
    store_raw; source differs)."""
    row = RawIngest(
        user_id=user_id,
        source=SOURCE,
        payload_type=payload_type,
        raw_json=payload,
        processed=False,
    )
    if fetched_at is not None:
        row.fetched_at = fetched_at
    session.add(row)
    await session.flush()
    return row
