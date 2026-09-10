"""Raw ingestion (§3, §17): every payload from any external source lands in
`raw_ingest` BEFORE normalization — an upstream schema change breaks the
parser, not the history. Reprocessing starts from these rows.

Rows are stored with processed=false; the normalizer flips them only after a
successful pass, so a malformed payload stays visible and replayable.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import RawIngest

logger = logging.getLogger("connectors.garmin.fetch")

SOURCE = "garmin"

# payload_type values used by the Garmin connector
PAYLOAD_ACTIVITY_SUMMARY = "activity_summary"
PAYLOAD_ACTIVITY_STREAMS = "activity_streams"
PAYLOAD_SLEEP = "sleep"
PAYLOAD_HRV = "hrv"
PAYLOAD_STRESS = "stress"
PAYLOAD_STATS = "stats"
PAYLOAD_BODY_COMPOSITION = "body_composition"


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
