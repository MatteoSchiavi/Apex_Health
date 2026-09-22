"""Strava normalizer: summary activities -> canonical activities (§3, §17).

Field mapping (Strava v3 summary activity):
  start_date (UTC ISO)      -> activities.start_time
  elapsed_time (s)          -> activities.duration_s
  distance (m)              -> activities.distance_m
  total_elevation_gain (m)  -> activities.elevation_gain_m
  average_heartrate         -> activities.avg_hr
  max_heartrate             -> activities.max_hr
  calories (kcal; fallback kilojoules/4.184) -> activities.calories
  sport_type                -> discipline via alias table
  relative_effort, type, workout_type, moving_time, device_name
                            -> activities.source_metrics["strava"]  (NOT
                               training_load — different semantics)
data_completeness = 'partial' (summary-only, no streams this phase).
Idempotent via activity_source_links UNIQUE (source, external_id).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.strava.fetch import SOURCE
from app.models.activity import Activity, ActivitySourceLink
from app.connectors.garmin.normalize import NormalizerStats

logger = logging.getLogger("connectors.strava.normalize")

_KJ_PER_KCAL = 4.184


class NormalizationError(Exception):
    pass


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def normalize_raw_row(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    from app.connectors.strava.type_map import resolve_discipline

    if getattr(raw, "payload_type", "") != "activity_summary":
        logger.warning("strava normalizer: unknown payload_type %s", getattr(raw, "payload_type", ""))
        return
    external_id = str(payload.get("id") or "")
    if not external_id:
        raise NormalizationError(
            f"activity raw row {getattr(raw, 'id', '?')}: missing id"
        )
    user_id = getattr(raw, "user_id")

    start_raw = payload.get("start_date")
    if not isinstance(start_raw, str):
        raise NormalizationError(f"activity {external_id}: missing start_date")
    try:
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"activity {external_id}: bad start_date") from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=ZoneInfo("UTC"))

    elapsed = _int_or_none(payload.get("elapsed_time"))
    if elapsed is None or elapsed <= 0:
        # zero-duration rows (device ghosts) are a clean skip, not an error
        return
    distance = _int_or_none(_num(payload.get("distance")))
    elevation = _num(payload.get("total_elevation_gain"))
    avg_hr = _int_or_none(_num(payload.get("average_heartrate")))
    max_hr = _int_or_none(_num(payload.get("max_heartrate")))
    calories = _int_or_none(_num(payload.get("calories")))
    if calories is None:
        kj = _num(payload.get("kilojoules"))
        if kj is not None:
            calories = round(kj / _KJ_PER_KCAL)
    moving_time = _int_or_none(payload.get("moving_time"))
    relative_effort = _num(payload.get("suffer_score"))
    sport_type = payload.get("sport_type") or payload.get("type")
    discipline_id, fallback_note = resolve_discipline(sport_type, discipline_index)
    if fallback_note:
        stats.discipline_fallbacks.append(fallback_note)

    link = await session.scalar(
        select(ActivitySourceLink).where(
            ActivitySourceLink.source == SOURCE,
            ActivitySourceLink.external_id == external_id,
        )
    )
    if link is None:
        activity = Activity(
            user_id=user_id,
            discipline_id=discipline_id,
            start_time=start,
            start_tz_offset_minutes=_local_offset(payload.get("start_date_local"), tz, start),
            local_date=start.astimezone(tz).date(),
            duration_s=elapsed,
            distance_m=distance,
            elevation_gain_m=elevation,
            avg_hr=avg_hr,
            max_hr=max_hr,
            calories=calories,
            training_load=None,
            data_completeness="partial",
            source_metrics={
                "strava": {
                    "sport_type": sport_type,
                    "moving_time_s": moving_time,
                    "relative_effort": relative_effort,
                    "name": payload.get("name"),
                }
            },
        )
        session.add(activity)
        await session.flush()
        session.add(
            ActivitySourceLink(
                activity_id=activity.id,
                source=SOURCE,
                external_id=external_id,
                raw_ingest_id=getattr(raw, "id", None),
            )
        )
    else:
        activity = await session.get(Activity, link.activity_id)
        if activity is None:  # pragma: no cover
            raise NormalizationError(f"activity {external_id}: dangling activity link")
        activity.duration_s = elapsed
        if distance is not None:
            activity.distance_m = distance
        if elevation is not None:
            activity.elevation_gain_m = elevation
        if avg_hr is not None:
            activity.avg_hr = avg_hr
        if max_hr is not None:
            activity.max_hr = max_hr
        if calories is not None:
            activity.calories = calories
        if discipline_id is not None:
            activity.discipline_id = discipline_id
    stats.activities_upserted += 1


def _local_offset(raw_local: object, tz: ZoneInfo, start: datetime) -> int | None:
    if isinstance(raw_local, str):
        try:
            local = datetime.fromisoformat(raw_local.replace("Z", "+00:00"))
            if local.tzinfo is not None:
                return int(local.utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
        except ValueError:
            pass
    local = start.astimezone(tz)
    return int(local.utcoffset().total_seconds() // 60) if local.utcoffset() else None
