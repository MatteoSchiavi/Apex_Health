"""Strava raw ingestion (§3): summary activities land in raw_ingest first."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import RawIngest

SOURCE = "strava"


async def store_raw(
    session: AsyncSession,
    user_id: int,
    payload_type: str,
    payload: Any,
    *,
    fetched_at: datetime | None = None,
) -> RawIngest:
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
