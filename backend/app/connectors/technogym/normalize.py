"""Normalizer for the Technogym connector (§3 stage 3, §11a, §17).

Keyed per §17 idempotent-upsert law: activities -> activity_source_links
UNIQUE (source, external_id); the linked activity row is updated in place,
never duplicated.

Raw purity: raw_json is stored exactly as upstream returned it; fetch context
lives in payload_type suffixes only:

- workout                (id/startDate inside the payload)
- workout_detail:{id}    (machine-record detail; kept for raw history and
                          §12's "richer source per field" reads — the
                          normalized activity consumes the workout row)

Day-boundary rule (§17): local_date/start_tz_offset_minutes derive from the
USER's timezone, never from the payload's embedded offset or UTC.

Equipment mapping falls back to `gym_general` and is flagged — same
discipline law as the Garmin type map (§17: no ad-hoc disciplines).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.technogym import fetch
from app.connectors.technogym.type_map import resolve_equipment
from app.gear.service import auto_link_gear
from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import RawIngest

logger = logging.getLogger("connectors.technogym.normalize")


class NormalizationError(Exception):
    """The payload cannot be parsed against its expected shape. The raw row
    stays unprocessed (§3: reprocess from raw JSON)."""


@dataclass
class NormalizerStats:
    """Counters for one normalization pass (per raw rows consumed)."""

    activities_upserted: int = 0
    discipline_fallbacks: list[str] = field(default_factory=list)
    unprocessed: list[int] = field(default_factory=list)  # raw ids that failed parsing


def _parse_start(value: Any, label: str) -> datetime:
    """Technogym carries ISO-8601 instants with an explicit UTC offset
    (recorded fixtures: '2025-03-09T10:04:00+01:00')."""
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"{label}: expected ISO-8601 datetime, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"{label}: unparsable ISO datetime {value!r}") from exc
    if parsed.tzinfo is None:
        raise NormalizationError(f"{label}: datetime without tz offset: {value!r}")
    return parsed


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    v = _num(value)
    return round(v) if v is not None else None


async def normalize_raw_row(
    session: AsyncSession,
    raw: RawIngest,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
) -> NormalizerStats:
    """Consume one raw row. Raises NormalizationError to leave the row
    unprocessed (§3: parser breaks, history doesn't)."""
    stats = NormalizerStats()
    payload = raw.raw_json
    base_type = raw.payload_type.split(":", 1)[0]

    if base_type == fetch.PAYLOAD_WORKOUT:
        await _upsert_activity(session, raw, payload, tz, discipline_index, stats)
    elif base_type == fetch.PAYLOAD_WORKOUT_DETAIL:
        pass  # archival raw history; the workout row drives normalization
    else:
        raise NormalizationError(f"unknown payload_type {raw.payload_type!r}")
    raw.processed = True
    return stats


async def _upsert_activity(
    session: AsyncSession,
    raw: RawIngest,
    payload: Any,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    if not isinstance(payload, dict) or "id" not in payload:
        raise NormalizationError(f"workout missing id: {payload!r}")

    external_id = str(payload["id"])
    start_time = _parse_start(payload.get("startDate"), f"workout {external_id} startDate")
    duration = _num(payload.get("durationSeconds"))
    if duration is None:
        raise NormalizationError(f"workout {external_id}: missing durationSeconds")
    duration_s = max(0, round(duration))

    local_start = start_time.astimezone(tz)
    local_date = local_start.date()  # §17: local calendar day of the start
    tz_offset_minutes = round(
        (local_start.utcoffset() or timedelta(0)).total_seconds() / 60
    )

    equipment = payload.get("equipment")
    discipline_id, source = resolve_equipment(equipment, discipline_index)
    if source == "fallback":
        stats.discipline_fallbacks.append(f"{external_id}:{equipment!r}")

    has_signal = payload.get("avgHeartRate") is not None or payload.get("avgPowerWatts") is not None
    completeness = "full" if has_signal else "partial"

    values = dict(
        user_id=raw.user_id,
        discipline_id=discipline_id,
        start_time=start_time,
        start_tz_offset_minutes=tz_offset_minutes,
        local_date=local_date,
        duration_s=duration_s,
        distance_m=_num(payload.get("totalDistanceMeters")),
        elevation_gain_m=_num(payload.get("elevationGainMeters")),
        avg_hr=_int_or_none(payload.get("avgHeartRate")),
        max_hr=_int_or_none(payload.get("maxHeartRate")),
        avg_power=_num(payload.get("avgPowerWatts")),
        np_power=None,  # Technogym reports no normalized-power equivalent
        calories=_int_or_none(payload.get("calories")),
        training_load=None,  # §7 feature engine owns load computation
        data_completeness=completeness,
    )

    link = await session.scalar(
        select(ActivitySourceLink).where(
            ActivitySourceLink.source == fetch.SOURCE,
            ActivitySourceLink.external_id == external_id,
        )
    )
    if link is None:
        activity = Activity(**values)
        session.add(activity)
        await session.flush()
        session.add(
            ActivitySourceLink(
                activity_id=activity.id,
                source=fetch.SOURCE,
                external_id=external_id,
                raw_ingest_id=raw.id,
            )
        )
    else:
        activity = await session.get(Activity, link.activity_id)
        if activity is None:  # pragma: no cover - broken link implies data corruption
            raise NormalizationError(f"activity link {external_id} points at missing row")
        for key, val in values.items():
            setattr(activity, key, val)
        link.raw_ingest_id = raw.id
    stats.activities_upserted += 1

    # §13: auto-link the discipline's default gear at ingestion (idempotent
    # via the (activity_id, gear_id) PK — re-normalization never re-adds).
    await auto_link_gear(
        session,
        user_id=raw.user_id,
        discipline_id=discipline_id,
        activity_id=activity.id,
    )
