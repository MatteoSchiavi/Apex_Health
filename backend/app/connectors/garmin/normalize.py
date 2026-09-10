"""Normalizer/ETL (§3 stage 3): typed, idempotent upserts from raw JSON.

Keyed per §17 "all sync/ingest operations are idempotent upserts":
- activities       -> activity_source_links UNIQUE (source, external_id)
- activity_streams -> PK (activity_id, t_offset_s), insert-or-ignore (immutable)
- sleep_sessions   -> natural key (user_id, start_time)
- hrv_readings     -> natural key (user_id, timestamp, reading_type)
- stress_readings  -> natural key (user_id, timestamp)
- daily_biometrics -> PK (user_id, date)

Raw purity: raw_json is stored exactly as upstream returned it. Fetch context
(which activity / which calendar day a payload was requested for) lives in
payload_type suffixes, never inside the payload:

- activity_summary            (activityId is inside the payload)
- activity_streams:{activity_id}
- sleep                       (payload carries its own timestamps)
- hrv                         (idem)
- stress                      (idem)
- stats:{YYYY-MM-DD}          (daily aggregate, addressed by date)
- body_composition:{YYYY-MM-DD}

Day-boundary rule (§17): every local_date/date column is derived from the
instant in the USER's timezone (users.timezone), never UTC. A sleep session's
date is the wake-up (end_time) local date; an activity's date is the local
start date.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin import fetch
from app.connectors.garmin.type_map import resolve_type_key
from app.gear.service import auto_link_gear
from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.integration import RawIngest
from app.models.wellness import DailyBiometric, HrvReading, SleepSession, StressReading

logger = logging.getLogger("connectors.garmin.normalize")

# Garmin stores GPS positions in semicircles (2^31 == 180 degrees) in the raw
# samples API; stream payloads carrying degree floats are accepted as-is.
_SEMICIRCLE = 180.0 / (2**31)
# Above this magnitude a position value must be semicircles, not degrees.
_SEMICIRCLE_THRESHOLD = 200.0


class NormalizationError(Exception):
    """The payload cannot be parsed against its expected shape. The raw row
    stays unprocessed (§3: reprocess from raw JSON)."""


@dataclass
class NormalizerStats:
    """Counters for one normalization pass (per raw rows consumed)."""

    activities_upserted: int = 0
    activity_streams_upserted: int = 0
    sleep_upserted: int = 0
    hrv_upserted: int = 0
    stress_upserted: int = 0
    biometrics_upserted: int = 0
    discipline_fallbacks: list[str] = field(default_factory=list)
    unprocessed: list[int] = field(default_factory=list)  # raw ids that failed parsing


def _base_type(payload_type: str) -> str:
    return payload_type.split(":", 1)[0]


def _suffix(payload_type: str) -> str:
    _, _, suffix = payload_type.partition(":")
    return suffix


def _epoch_ms(value: Any, label: str) -> datetime:
    if not isinstance(value, (int, float)) or value <= 0:
        raise NormalizationError(f"{label}: expected epoch milliseconds, got {value!r}")
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


def _parse_gmt_datetime(value: Any, label: str) -> datetime:
    """Garmin activity summaries carry startTimeGMT like '2025-03-08 05:30:00'
    (wall clock in UTC)."""
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"{label}: expected GMT datetime string, got {value!r}")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise NormalizationError(f"{label}: unparsable GMT datetime {value!r}") from exc


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


def _pos_to_degrees(value: Any) -> float | None:
    value = _num(value)
    if value is None:
        return None
    if abs(value) > _SEMICIRCLE_THRESHOLD:  # semicircles
        return round(value * _SEMICIRCLE, 7)
    return value


async def normalize_raw_row(
    session: AsyncSession, raw: RawIngest, tz: ZoneInfo, discipline_index: dict[str, int]
) -> NormalizerStats:
    """Dispatch one raw_ingest row to its typed upsert. Raises on payloads that
    don't match their expected shape — caller decides how to bookkeep."""
    stats = NormalizerStats()
    payload = raw.raw_json
    kind = _base_type(raw.payload_type)
    if kind == fetch.PAYLOAD_ACTIVITY_SUMMARY:
        await _upsert_activity(session, raw, payload, tz, discipline_index, stats)
    elif kind == fetch.PAYLOAD_ACTIVITY_STREAMS:
        await _upsert_streams(session, raw, payload, stats)
    elif kind == fetch.PAYLOAD_SLEEP:
        await _upsert_sleep(session, raw, payload, tz, stats)
    elif kind == fetch.PAYLOAD_HRV:
        await _upsert_hrv(session, raw, payload, stats)
    elif kind == fetch.PAYLOAD_STRESS:
        await _upsert_stress(session, raw, payload, stats)
    elif kind in (fetch.PAYLOAD_STATS, fetch.PAYLOAD_BODY_COMPOSITION):
        await _upsert_biometrics(session, raw, payload, kind, stats)
    else:
        raise NormalizationError(f"unknown payload_type {raw.payload_type!r}")
    raw.processed = True
    return stats


# ---------------------------------------------------------------- activities


async def _upsert_activity(
    session: AsyncSession,
    raw: RawIngest,
    payload: dict[str, Any],
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    if not isinstance(payload, dict) or "activityId" not in payload:
        raise NormalizationError(f"activity summary missing activityId: {payload!r}")

    external_id = str(payload["activityId"])
    start_time = _parse_gmt_datetime(payload.get("startTimeGMT"), "startTimeGMT")
    duration = _num(payload.get("duration"))
    if duration is None:
        raise NormalizationError(f"activity {external_id}: missing duration")
    duration_s = max(0, round(duration))

    local_start = start_time.astimezone(tz)
    local_date = local_start.date()  # §17: local calendar day of the start
    tz_offset_minutes = round((local_start.utcoffset() or timedelta(0)).total_seconds() / 60)

    type_key = (payload.get("activityType") or {}).get("typeKey")
    discipline_id, source = resolve_type_key(type_key, discipline_index)
    if source == "fallback":
        stats.discipline_fallbacks.append(f"{external_id}:{type_key!r}")

    manual = bool(payload.get("manual"))
    has_signal = payload.get("averageHR") is not None or payload.get("averagePower") is not None
    if manual:
        completeness = "manual"
    elif has_signal:
        completeness = "full"
    else:
        completeness = "partial"

    values = dict(
        user_id=raw.user_id,
        discipline_id=discipline_id,
        start_time=start_time,
        start_tz_offset_minutes=tz_offset_minutes,
        local_date=local_date,
        duration_s=duration_s,
        distance_m=_num(payload.get("distance")),
        elevation_gain_m=_num(payload.get("elevationGain")),
        avg_hr=_int_or_none(payload.get("averageHR")),
        max_hr=_int_or_none(payload.get("maxHR")),
        avg_power=_num(payload.get("averagePower")),
        np_power=_num(payload.get("normalizedPower")),
        calories=_int_or_none(payload.get("calories")),
        training_load=_num(payload.get("activityTrainingLoad")),
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

    # Garmin reports VO2max per-activity (vO2MaxValue); the latest estimate of
    # a local day wins (activities are processed chronologically).
    vo2 = _num(payload.get("vO2MaxValue"))
    if vo2 is not None:
        bio = await session.scalar(
            select(DailyBiometric).where(
                DailyBiometric.user_id == raw.user_id,
                DailyBiometric.date == local_date,
            )
        )
        if bio is None:
            bio = DailyBiometric(user_id=raw.user_id, date=local_date)
            session.add(bio)
        bio.vo2max = vo2


async def _upsert_streams(
    session: AsyncSession, raw: RawIngest, payload: Any, stats: NormalizerStats
) -> None:
    suffix = _suffix(raw.payload_type)
    if not suffix.isdigit():
        raise NormalizationError(
            f"streams raw row {raw.id}: payload_type must be 'activity_streams:<id>'"
        )
    external_id = suffix

    # The suffix carries the UPSTREAM id — resolve the activity through its
    # source link, the same (source, external_id) key every sync writes.
    link = await session.scalar(
        select(ActivitySourceLink).where(
            ActivitySourceLink.source == fetch.SOURCE,
            ActivitySourceLink.external_id == external_id,
        )
    )
    if link is None:
        raise NormalizationError(f"streams reference unknown external activity {external_id}")
    activity = await session.get(Activity, link.activity_id)
    if activity is None:  # pragma: no cover - broken link implies data corruption
        raise NormalizationError(f"streams link {external_id} points at missing activity")
    if not isinstance(payload, list) or not payload:
        raise NormalizationError(f"streams payload for raw row {raw.id}: expected non-empty list")

    start_time = activity.start_time
    rows: list[dict[str, Any]] = []
    for sample in payload:
        if not isinstance(sample, dict):
            raise NormalizationError(f"streams raw row {raw.id}: non-dict sample")
        ts = sample.get("timestamp")
        if ts is None:
            continue  # gap-filler samples carry no reading
        if not isinstance(ts, (int, float)):
            raise NormalizationError(f"streams raw row {raw.id}: bad timestamp {ts!r}")
        offset = round((datetime.fromtimestamp(ts / 1000.0, tz=UTC) - start_time).total_seconds())
        rows.append(
            dict(
                activity_id=activity.id,
                t_offset_s=offset,
                hr=_int_or_none(sample.get("heartRate")),
                power=_num(sample.get("power")),
                cadence=_num(sample.get("cadence")),
                speed=_num(sample.get("speed")),
                altitude=_num(sample.get("altitude")),
                lat=_pos_to_degrees(sample.get("positionLat")),
                lon=_pos_to_degrees(sample.get("positionLong")),
            )
        )

    if rows:
        stmt = pg_insert(ActivityStream).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["activity_id", "t_offset_s"])
        await session.execute(stmt)
        stats.activity_streams_upserted += len(rows)


# ------------------------------------------------------------------- sleep


async def _upsert_sleep(
    session: AsyncSession,
    raw: RawIngest,
    payload: dict[str, Any],
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("dailySleepDTO"), dict):
        raise NormalizationError(f"sleep raw row {raw.id}: missing dailySleepDTO")
    dto = payload["dailySleepDTO"]

    start = _epoch_ms(dto.get("sleepStartTimestampGMT"), "sleepStartTimestampGMT")
    end = _epoch_ms(dto.get("sleepEndTimestampGMT"), "sleepEndTimestampGMT")
    if end <= start:
        raise NormalizationError(f"sleep raw row {raw.id}: end before start")

    score = None
    if isinstance(payload.get("sleepScore"), dict):
        score = _num(payload["sleepScore"].get("value"))

    values = dict(
        user_id=raw.user_id,
        local_date=end.astimezone(tz).date(),  # §17: wake-up day, local calendar
        start_time=start,
        end_time=end,
        total_sleep_s=_int_or_none(dto.get("sleepTimeSeconds")),
        deep_s=_int_or_none(dto.get("deepSleepSeconds")),
        light_s=_int_or_none(dto.get("lightSleepSeconds")),
        rem_s=_int_or_none(dto.get("remSleepSeconds")),
        awake_s=_int_or_none(dto.get("awakeSleepSeconds")),
        sleep_score=score,
        respiration_avg=_num(dto.get("avgRespirationValue")),
        spo2_avg=_num(dto.get("avgSpO2Value")),
        restlessness=_num(dto.get("restlessness")),
    )

    existing = await session.scalar(
        select(SleepSession).where(
            SleepSession.user_id == raw.user_id, SleepSession.start_time == start
        )
    )
    if existing is None:
        session.add(SleepSession(**values))
    else:
        for key, val in values.items():
            setattr(existing, key, val)
    stats.sleep_upserted += 1


# --------------------------------------------------------------------- hrv


async def _upsert_hrv(
    session: AsyncSession, raw: RawIngest, payload: dict[str, Any], stats: NormalizerStats
) -> None:
    if not isinstance(payload, dict):
        raise NormalizationError(f"hrv raw row {raw.id}: expected object")
    readings = payload.get("hrvReadings") or []
    summary = payload.get("hrvSummary") or {}
    if not isinstance(readings, list):
        raise NormalizationError(f"hrv raw row {raw.id}: hrvReadings must be a list")

    last_ts: datetime | None = None
    for reading in readings:
        if not isinstance(reading, dict):
            raise NormalizationError(f"hrv raw row {raw.id}: non-dict reading")
        ts = _epoch_ms(reading.get("timestamp"), "hrv timestamp")
        hrv = _num(reading.get("hrvValue"))
        if hrv is None:
            continue
        last_ts = max(last_ts, ts) if last_ts else ts
        baseline = _num(summary.get("baseline", {}).get("avg")) if isinstance(summary.get("baseline"), dict) else None
        await _upsert_hrv_reading(session, raw.user_id, ts, hrv, "5min", baseline, stats)

    if last_ts is not None and _num(summary.get("lastNightAvg")) is not None:
        # Garmin's overnight average has no first-class timestamp of its own;
        # anchor it at the night's last 5-min reading (documented choice). It
        # coexists with the 5-min row at the same timestamp: reading_type is
        # part of the natural key.
        await _upsert_hrv_reading(
            session, raw.user_id, last_ts, float(summary["lastNightAvg"]), "overnight_avg", None, stats
        )


async def _upsert_hrv_reading(
    session: AsyncSession,
    user_id: int,
    ts: datetime,
    hrv_ms: float,
    reading_type: str,
    baseline: float | None,
    stats: NormalizerStats,
) -> None:
    """Upsert on (user_id, timestamp, reading_type)."""
    existing = await session.scalar(
        select(HrvReading).where(
            HrvReading.user_id == user_id,
            HrvReading.timestamp == ts,
            HrvReading.reading_type == reading_type,
        )
    )
    if existing is None:
        session.add(
            HrvReading(
                user_id=user_id,
                timestamp=ts,
                hrv_ms=hrv_ms,
                reading_type=reading_type,
                rolling_baseline_ms=baseline,
            )
        )
    else:
        existing.hrv_ms = hrv_ms
        existing.rolling_baseline_ms = baseline
    stats.hrv_upserted += 1


# ------------------------------------------------------------------ stress


async def _upsert_stress(
    session: AsyncSession, raw: RawIngest, payload: dict[str, Any], stats: NormalizerStats
) -> None:
    if not isinstance(payload, dict):
        raise NormalizationError(f"stress raw row {raw.id}: expected object")
    graph = payload.get("stressGraph") or []
    if not graph:
        raise NormalizationError(f"stress raw row {raw.id}: empty stressGraph")
    battery = {
        p.get("timestamp"): p.get("value")
        for p in (payload.get("bodyBatteryChart") or [])
        if isinstance(p, dict)
    }

    for point in graph:
        if not isinstance(point, dict):
            raise NormalizationError(f"stress raw row {raw.id}: non-dict point")
        ts = _epoch_ms(point.get("timestamp"), "stress timestamp")
        level = _num(point.get("stressLevel"))
        bb = _num(battery.get(point.get("timestamp")))
        existing = await session.scalar(
            select(StressReading).where(
                StressReading.user_id == raw.user_id, StressReading.timestamp == ts
            )
        )
        if existing is None:
            session.add(
                StressReading(
                    user_id=raw.user_id, timestamp=ts, stress_level=level, body_battery=bb
                )
            )
        else:
            existing.stress_level = level
            if bb is not None:
                existing.body_battery = bb
        stats.stress_upserted += 1


# -------------------------------------------------------------- biometrics


async def _upsert_biometrics(
    session: AsyncSession,
    raw: RawIngest,
    payload: dict[str, Any],
    kind: str,
    stats: NormalizerStats,
) -> None:
    if not isinstance(payload, dict):
        raise NormalizationError(f"biometrics raw row {raw.id}: expected object")

    label = _suffix(raw.payload_type)
    try:
        day = datetime.strptime(label, "%Y-%m-%d").date()
    except ValueError as exc:
        raise NormalizationError(
            f"biometrics raw row {raw.id}: payload_type must carry a YYYY-MM-DD day"
        ) from exc
    if not isinstance(day, date):  # pragma: no cover - strptime guarantees date
        raise NormalizationError(f"biometrics raw row {raw.id}: bad date")

    if kind == fetch.PAYLOAD_STATS:
        values = dict(
            resting_hr=_int_or_none(payload.get("restingHeartRate")),
            steps=_int_or_none(payload.get("totalSteps")),
            floors=_int_or_none(payload.get("floorsAscended")),
            spo2_avg=_num(payload.get("averageSpo2")),
        )
    else:  # body composition — weight is reported in grams upstream
        total = payload.get("totalAverage") or {}
        weight_g = _num(total.get("weight"))
        values = dict(
            weight_kg=(weight_g / 1000.0) if weight_g is not None else None,
            body_fat_pct=_num(total.get("bodyFat")),
        )

    existing = await session.scalar(
        select(DailyBiometric).where(
            DailyBiometric.user_id == raw.user_id, DailyBiometric.date == day
        )
    )
    if existing is None:
        existing = DailyBiometric(user_id=raw.user_id, date=day)
        session.add(existing)
    for key, val in values.items():
        if val is not None:
            setattr(existing, key, val)
    stats.biometrics_upserted += 1
