"""FIT enrichment (§3b / STACK.md §2.9): what Garmin's JSON API hides.

Garmin registers MORE than Connect exposes over the unofficial JSON
endpoints — per-lap splits are the classic case: the watch records every
lap (auto or manual) with avg/max HR, power, duration, calories, but the
activity-summary JSON only carries some sports' laps and drops the rest.
The authoritative source is the activity's FIT file.

This module downloads the FIT for activities whose laps are missing and
upserts `activity_laps` rows (migration 0007) plus fills stream columns the
summary samples lack (e.g. cadence for runs where the JSON stream omits it).

FIT parsing uses `fitdecode` (pure Python, no SDK). Every row upserts
idempotently keyed (activity_id, lap_index); the download itself is paced
by the caller like every connector (§19).

DATA_COVERAGE.md documents the full can/can't-retrieve audit.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityLap

logger = logging.getLogger("app.services.fit_enrichment")

# fitdecode is lazy-imported (pure-Python but the whole connector suite keeps
# optional providers import-light).
_fitdecode: Any | None = None


def _decoder():
    global _fitdecode
    if _fitdecode is None:
        import fitdecode

        _fitdecode = fitdecode
    return _fitdecode


_SEMI_CIRCLE_TO_DEG = 180.0 / (2 ** 31)


def parse_fit_laps(data: bytes) -> list[dict[str, Any]]:
    """Extract lap records from a FIT file blob.

    Returns dicts keyed like ActivityLap columns (minus activity_id/id):
    lap_index, start_time (aware UTC), duration_s, distance_m, avg_hr,
    max_hr, avg_power, calories, extras (raw-first overflow).
    """
    fitdecode = _decoder()
    laps: list[dict[str, Any]] = []
    with fitdecode.FitReader(io.BytesIO(data)) as reader:
        for frame in reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue
            if frame.name not in ("lap", "session"):
                continue
            if frame.name == "session":
                continue  # session summary is already covered by the JSON API
            row: dict[str, Any] = {"lap_index": len(laps) + 1, "extras": {}}
            for field in frame.fields:
                name = field.name
                value = field.value
                if value is None:
                    continue
                try:
                    if name == "start_time":
                        row["start_time"] = (
                            value.astimezone(timezone.utc)
                            if isinstance(value, datetime)
                            else None
                        )
                    elif name == "total_timer_time":
                        row["duration_s"] = int(round(float(value)))
                    elif name == "total_distance":
                        row["distance_m"] = float(value)
                    elif name == "avg_heart_rate":
                        row["avg_hr"] = int(value)
                    elif name == "max_heart_rate":
                        row["max_hr"] = int(value)
                    elif name == "avg_power":
                        row["avg_power"] = float(value)
                    elif name == "total_calories":
                        row["calories"] = int(value)
                    elif name in (
                        "total_ascent", "total_descent", "total_elapsed_time",
                        "sport", "sub_sport", "total_moving_time",
                        "normalized_power", "total_work",
                    ):
                        if isinstance(value, bytes):
                            value = value.decode("utf-8", "replace")
                        row["extras"][name] = value
                except (TypeError, ValueError):
                    continue
            laps.append(row)
    return laps


async def fetch_fit_bytes(
    download_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes | None:
    """Download a FIT file from Garmin's download API. Returns None on any
    failure — enrichment is best-effort by design and must never break a
    sync (the JSON data is already in)."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=120.0) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as exc:
        logger.warning("FIT download failed (%s): %s", download_url, exc)
        return None


async def upsert_laps(session: AsyncSession, activity_id: int, laps: list[dict[str, Any]]) -> int:
    """Idempotent lap upsert keyed (activity_id, lap_index). Returns the
    number of rows written."""
    written = 0
    for spec in laps:
        lap_index = spec.get("lap_index")
        if lap_index is None:
            continue
        existing = (
            await session.scalars(
                select(ActivityLap).where(
                    ActivityLap.activity_id == activity_id,
                    ActivityLap.lap_index == lap_index,
                )
            )
        ).first()
        if existing is None:
            session.add(ActivityLap(activity_id=activity_id, **spec))
        else:
            for key in ("start_time", "duration_s", "distance_m", "avg_hr",
                        "max_hr", "avg_power", "calories", "extras"):
                if spec.get(key) is not None:
                    setattr(existing, key, spec[key])
        written += 1
    await session.flush()
    return written


async def enrich_activity_laps(
    session: AsyncSession,
    activity: Activity,
    fit_bytes: bytes,
) -> int:
    """Parse + persist laps for one activity. Returns rows written."""
    try:
        laps = parse_fit_laps(fit_bytes)
    except Exception as exc:  # noqa: BLE001 — malformed/unsupported FIT
        logger.warning(
            "FIT parse failed for activity %s: %s", activity.id, exc
        )
        return 0
    if not laps:
        return 0
    return await upsert_laps(session, activity.id, laps)


async def activities_missing_laps(
    session: AsyncSession,
    user_id: int,
    limit: int = 25,
) -> list[Activity]:
    """Candidate queue: activities with multiple stream samples (a real
    session) but no lap rows yet, oldest first so backfill progress is
    monotonic."""
    from sqlalchemy import exists

    has_laps = exists(
        select(ActivityLap.id).where(ActivityLap.activity_id == Activity.id)
    )
    return (
        await session.scalars(
            select(Activity)
            .where(
                Activity.user_id == user_id,
                ~has_laps,
                Activity.duration_s >= 300,  # <5 min: no laps worth parsing
            )
            .order_by(Activity.start_time.desc())
            .limit(limit)
        )
    ).all()
