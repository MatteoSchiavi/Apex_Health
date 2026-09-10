"""Raw ingestion for the Technogym connector (§3, §11, §17).

Same law as Garmin: every payload lands in `raw_ingest` BEFORE normalization
(processed=false) — an upstream schema change breaks the parser, not the
history. The recorded-shape fixtures are the normalizer's contract until the
owner's first real manual sync captures live payloads (§24).
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import RawIngest

logger = logging.getLogger("connectors.technogym.fetch")

SOURCE = "technogym"

# payload_type values used by the Technogym connector
PAYLOAD_WORKOUT = "workout"
PAYLOAD_WORKOUT_DETAIL = "workout_detail"


async def store_raw(
    session: AsyncSession,
    user_id: int,
    payload_type: str,
    payload: Any,
    *,
    fetched_at: datetime | None = None,
) -> RawIngest:
    """Persist one raw payload. Empty payloads are skipped upstream — a record
    with nothing in it is not data."""
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
