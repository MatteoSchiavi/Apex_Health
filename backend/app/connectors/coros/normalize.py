"""Normalize the documented COROS MCP activity envelope.

The MCP tool must return canonical activity fields. Provider-specific payloads
that do not meet this contract remain in raw_ingest for later review.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.reconciliation import (
    activity_has_other_selected_main,
    find_reconcilable_activity,
    reconcile_activity,
)
from app.connectors.strava.type_map import resolve_discipline
from app.models.activity import Activity, ActivitySourceLink

SOURCE = "coros"


class NormalizationError(Exception):
    pass


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


async def normalize_activity(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    # Take the account lock before canonical rows, matching ingest/erase order.
    from app.services.evidence import scope_lock
    await scope_lock(session, raw.user_id, "changes")
    external_id = payload.get("id") or payload.get("external_id")
    if external_id is None or not str(external_id).strip():
        raise NormalizationError("activity is missing id/external_id")
    start_value = payload.get("start_time")
    if not isinstance(start_value, str):
        raise NormalizationError(f"activity {external_id}: missing start_time")
    try:
        start = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"activity {external_id}: invalid start_time") from exc
    if start.tzinfo is None:
        raise NormalizationError(f"activity {external_id}: start_time must include timezone")
    duration = _number(payload.get("duration_s"))
    if duration is None or duration <= 0:
        raise NormalizationError(f"activity {external_id}: duration_s must be positive")
    user_id = getattr(raw, "user_id")
    sport = payload.get("sport_type") or payload.get("discipline")
    discipline_id, fallback_note = resolve_discipline(sport, discipline_index)
    if fallback_note:
        stats.discipline_fallbacks.append(f"coros:{fallback_note}")

    link = await session.scalar(
        select(ActivitySourceLink).where(
            ActivitySourceLink.source == SOURCE,
            ActivitySourceLink.external_id == str(external_id),
            ActivitySourceLink.user_id == user_id,
        )
    )
    values = {
        "discipline_id": discipline_id,
        "start_time": start,
        "start_tz_offset_minutes": int(start.utcoffset().total_seconds() // 60),
        "local_date": start.astimezone(tz).date(),
        "duration_s": round(duration),
        "distance_m": _number(payload.get("distance_m")),
        "elevation_gain_m": _number(payload.get("elevation_gain_m")),
        "avg_hr": _as_int(payload.get("avg_hr")),
        "max_hr": _as_int(payload.get("max_hr")),
        "calories": _as_int(payload.get("calories")),
        "data_completeness": "partial",
    }
    coros_metrics = {
        key: value
        for key, value in payload.items()
        if key not in {
            "id",
            "external_id",
            "start_time",
            "duration_s",
            "distance_m",
            "elevation_gain_m",
            "avg_hr",
            "max_hr",
            "calories",
        }
        and value is not None
    }
    if link is None:
        candidate = (
            await find_reconcilable_activity(
                session,
                user_id=user_id,
                start_time=start,
                discipline_id=discipline_id,
                source=SOURCE,
            )
            if discipline_id is not None
            else None
        )
        if candidate is not None:
            await reconcile_activity(
                session,
                existing=candidate,
                incoming_values=values,
                source=SOURCE,
                external_id=str(external_id),
                raw_ingest_id=getattr(raw, "id", None),
            )
            activity = candidate
            merged = True
        else:
            activity = Activity(user_id=user_id, **values)
            session.add(activity)
            await session.flush()
            session.add(
                ActivitySourceLink(
                    user_id=user_id,
                    activity_id=activity.id,
                    source=SOURCE,
                    external_id=str(external_id),
                    raw_ingest_id=getattr(raw, "id", None),
                )
            )
            merged = False
    else:
        activity = await session.get(Activity, link.activity_id)
        if activity is None:
            raise NormalizationError(f"activity {external_id}: dangling source link")
        # A refresh from a secondary integration can fill gaps in the
        # selected main device's activity, but never replace populated values.
        preserve_main = await activity_has_other_selected_main(session, activity, SOURCE)
        for key, value in values.items():
            if value is not None and (not preserve_main or getattr(activity, key) is None):
                setattr(activity, key, value)
        link.raw_ingest_id = getattr(raw, "id", None)
        merged = False

    # Merge provider-owned metadata without erasing another connector's
    # source_metrics or earlier COROS values omitted by this response.
    metrics = dict(activity.source_metrics or {})
    coros = dict(metrics.get(SOURCE) or {})
    coros.update(coros_metrics)
    metrics[SOURCE] = coros
    activity.source_metrics = metrics
    if merged:
        stats.activities_merged += 1
    else:
        stats.activities_upserted += 1


def _as_int(value: object) -> int | None:
    number = _number(value)
    return round(number) if number is not None else None
