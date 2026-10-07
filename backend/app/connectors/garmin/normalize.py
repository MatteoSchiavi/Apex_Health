"""Normalizer/ETL (§3 stage 3): typed, idempotent upserts from raw JSON.

Keyed per §17 "all sync/ingest operations are idempotent upserts":
- activities       -> activity_source_links UNIQUE (user_id, source, external_id)
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
from app.connectors.reconciliation import (
    activity_has_other_selected_main,
    find_reconcilable_activity,
    reconcile_activity,
    selected_main_provider,
)
from app.connectors.validation import (
    valid_body_battery,
    valid_body_fat_pct,
    valid_hrv_ms,
    valid_respiration_bpm,
    valid_resting_hr_bpm,
    valid_sleep_score,
    valid_spo2_pct,
    valid_stress_level,
    valid_weight_kg,
)
from app.gear.service import auto_link_gear
from app.services.sleep_summary import awake_seconds
from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.integration import RawIngest
from app.models.wellness import DailyBiometric, HrvReading, SleepSession, StressReading
from app.services.biometric_provenance import set_biometric

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
    activities_merged: int = 0  # secondary rows folded into a main-device row (device priority law)
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


def _timestamp_flex(value: Any, label: str) -> datetime:
    """garminconnect 0.3.x emits ISO strings ('2026-09-20T21:25:02.0') where
    older response shapes carried epoch milliseconds — accept both."""
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise NormalizationError(f"{label}: unparsable timestamp {value!r}") from exc
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return _epoch_ms(value, label)


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
    # Take the account lock before canonical rows, matching ingest/erase order.
    from app.services.evidence import scope_lock
    await scope_lock(session, raw.user_id, "changes")
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
        await _upsert_hrv(session, raw, payload, stats, tz)
    elif kind == fetch.PAYLOAD_STRESS:
        await _upsert_stress(session, raw, payload, stats)
    elif kind in (fetch.PAYLOAD_STATS, fetch.PAYLOAD_BODY_COMPOSITION):
        await _upsert_biometrics(session, raw, payload, kind, stats)
    else:
        raise NormalizationError(f"unknown payload_type {raw.payload_type!r}")
    from app.services.evidence import index_garmin_payload
    await index_garmin_payload(session, raw, tz)
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

    activity_type = payload.get("activityType") or {}
    type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else activity_type
    type_key = type_key or payload.get("sub_sport_type") or payload.get("sport_type")
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
                ActivitySourceLink.user_id == raw.user_id,
        )
    )
    if link is not None:
        activity = await session.get(Activity, link.activity_id)
        if activity is None:  # pragma: no cover - broken link implies data corruption
            raise NormalizationError(f"activity link {external_id} points at missing row")
        # §17 upsert law: this source's own row updates in place; a populated
        # field is never degraded to NULL (§12 floor rule, applied to re-syncs).
        preserve_main = await activity_has_other_selected_main(session, activity, fetch.SOURCE)
        for key, val in values.items():
            if val is not None and (not preserve_main or getattr(activity, key) is None):
                setattr(activity, key, val)
        link.raw_ingest_id = raw.id
    else:
        # §12: reconcile against a same-window session from ANOTHER source
        # (±10 min, same discipline) — merge into it instead of duplicating.
        candidate = (
            await find_reconcilable_activity(
                session,
                user_id=raw.user_id,
                start_time=start_time,
                discipline_id=discipline_id,
                source=fetch.SOURCE,
            )
            if discipline_id is not None
            else None
        )
        if candidate is not None:
            await reconcile_activity(
                session,
                existing=candidate,
                incoming_values=values,
                source=fetch.SOURCE,
                external_id=external_id,
                raw_ingest_id=raw.id,
            )
            activity = candidate  # the merged row continues the pipeline
        else:
            activity = Activity(**values)
            session.add(activity)
            await session.flush()
            session.add(
                ActivitySourceLink(
                    user_id=raw.user_id,
                    activity_id=activity.id,
                    source=fetch.SOURCE,
                    external_id=external_id,
                    raw_ingest_id=raw.id,
                )
            )
    stats.activities_upserted += 1

    # Keep the provider's original activity label intact for unknown labels,
    # later reclassification, and provenance even when no canonical sport is
    # seeded for it. Merge this provider block without replacing other sources.
    source_metrics = dict(activity.source_metrics or {})
    garmin_metrics = dict(source_metrics.get("garmin") or {})
    garmin_metrics["type_key"] = type_key
    if (recorded_load := _num(payload.get("activityTrainingLoad"))) is not None:
        garmin_metrics["training_load"] = recorded_load
        garmin_metrics["training_load_method"] = "garmin_activity_training_load"
        garmin_metrics["training_load_unit"] = "Garmin load"
    # Preserve recorded provider summary fields in their original units. The
    # presentation layer only displays a sport-specific field when it exists.
    for upstream, canonical in (("averageSpeed", "avg_speed_m_s"), ("maxSpeed", "max_speed_m_s")):
        value = _num(payload.get(upstream))
        if value is not None and value >= 0:
            garmin_metrics[canonical] = value
    cadence = payload.get("averageBikingCadenceInRevPerMinute") if type_key in {"cycling", "mountain_biking", "indoor_cycling", "gravel_cycling"} else payload.get("averageRunCadence") if type_key in {"running", "trail_running", "treadmill_running"} else None
    if (value := _num(cadence)) is not None and value >= 0:
        garmin_metrics["avg_cadence"] = value
    source_metrics["garmin"] = garmin_metrics
    activity.source_metrics = source_metrics

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
        if await _can_write_biometric(session, bio, "vo2max"):
            set_biometric(bio, "vo2max", vo2, fetch.SOURCE)


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
                ActivitySourceLink.user_id == raw.user_id,
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

    # 0.3.x no-recording days (device not worn) arrive as a structured DTO
    # with every field null instead of an empty payload — a clean skip, not
    # a parse error.
    if (
        dto.get("sleepStartTimestampGMT") is None
        and dto.get("sleepEndTimestampGMT") is None
        and dto.get("sleepTimeSeconds") is None
    ):
        return

    start = _epoch_ms(dto.get("sleepStartTimestampGMT"), "sleepStartTimestampGMT")
    end = _epoch_ms(dto.get("sleepEndTimestampGMT"), "sleepEndTimestampGMT")
    if end <= start:
        raise NormalizationError(f"sleep raw row {raw.id}: end before start")

    score = None
    if isinstance(payload.get("sleepScore"), dict):
        score = _num(payload["sleepScore"].get("value"))
    if score is None:
        score = _num(((dto.get("sleepScores") or {}).get("overall") or {}).get("value"))

    values = dict(
        user_id=raw.user_id,
        origin="garmin",
        local_date=end.astimezone(tz).date(),  # §17: wake-up day, local calendar
        start_time=start,
        end_time=end,
        total_sleep_s=_int_or_none(dto.get("sleepTimeSeconds")),
        deep_s=_int_or_none(dto.get("deepSleepSeconds")),
        light_s=_int_or_none(dto.get("lightSleepSeconds")),
        rem_s=_int_or_none(dto.get("remSleepSeconds")),
        awake_s=(
            awake_seconds(payload, start, end)
            if dto.get("awakeSleepSeconds") in (None, 0) and awake_seconds(payload, start, end) is not None
            else _int_or_none(dto.get("awakeSleepSeconds"))
        ),
        sleep_score=valid_sleep_score(score),
        respiration_avg=valid_respiration_bpm(dto.get("avgRespirationValue")),
        spo2_avg=valid_spo2_pct(dto.get("avgSpO2Value")),
        restlessness=_num(dto.get("restlessness")),
    )

    existing = await session.scalar(
        select(SleepSession).where(
            SleepSession.user_id == raw.user_id, SleepSession.start_time == start,
            SleepSession.origin == "garmin",
        )
    )
    if existing is None:
        session.add(SleepSession(**values))
    else:
        for key, val in values.items():
            if val is not None:
                setattr(existing, key, val)
    stats.sleep_upserted += 1


# --------------------------------------------------------------------- hrv


async def _upsert_hrv(
    session: AsyncSession, raw: RawIngest, payload: dict[str, Any], stats: NormalizerStats,
    tz: ZoneInfo,
) -> None:
    if not isinstance(payload, dict):
        raise NormalizationError(f"hrv raw row {raw.id}: expected object")
    readings = payload.get("hrvReadings") or []
    summary = payload.get("hrvSummary") or {}
    if not isinstance(summary, dict):
        raise NormalizationError(f"hrv raw row {raw.id}: hrvSummary must be an object")
    if not isinstance(readings, list):
        raise NormalizationError(f"hrv raw row {raw.id}: hrvReadings must be a list")

    last_ts: datetime | None = None
    for reading in readings:
        if not isinstance(reading, dict):
            raise NormalizationError(f"hrv raw row {raw.id}: non-dict reading")
        # 0.3.x: readingTimeGMT ISO string; legacy: epoch-ms timestamp.
        raw_ts = reading.get("timestamp")
        if raw_ts is None:
            raw_ts = reading.get("readingTimeGMT")
        ts = _timestamp_flex(raw_ts, "hrv timestamp")
        # P-02 audit: drop implausible HRV values BEFORE they enter typed
        # tables. A 0.5 ms glitch or a 9999 ms stuck reading must never
        # reach daily aggregates or illness-risk scoring. Raw stays for
        # replay.
        hrv = valid_hrv_ms(reading.get("hrvValue"))
        if hrv is None:
            continue
        last_ts = max(last_ts, ts) if last_ts else ts
        baseline = _num(summary.get("baseline", {}).get("avg")) if isinstance(summary.get("baseline"), dict) else None
        await _upsert_hrv_reading(session, raw.user_id, ts, hrv, "5min", baseline, stats)

    if last_ts is None:
        # Some watches expose only the nightly summary. The requested
        # calendar day is fetch context, not a fabricated provider timestamp.
        day_label = summary.get("calendarDate") or payload.get("calendarDate") or _suffix(raw.payload_type)
        if day_label:
            try:
                day = date.fromisoformat(day_label)
            except ValueError as exc:
                raise NormalizationError("HRV summary calendar date is invalid") from exc
            last_ts = datetime(day.year, day.month, day.day, 7, tzinfo=tz)
    if last_ts is not None:
        # P-02 audit: validate the overnight average too — Garmin's own
        # summary can occasionally carry a corrupt aggregate even when the
        # 5-min readings look fine.
        overnight = valid_hrv_ms(summary.get("lastNightAvg"))
        if overnight is not None:
            # Garmin's overnight average has no first-class timestamp of its own;
            # anchor it at the night's last 5-min reading (documented choice). It
            # coexists with the 5-min row at the same timestamp: reading_type is
            # part of the natural key.
            await _upsert_hrv_reading(
                session, raw.user_id, last_ts, overnight, "overnight_avg",
                valid_hrv_ms(summary.get("baseline", {}).get("avg")) if isinstance(summary.get("baseline"), dict) else None,
                stats
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
            HrvReading.origin == "garmin",
        )
    )
    if existing is None:
        session.add(
            HrvReading(
                user_id=user_id,
                timestamp=ts,
                hrv_ms=hrv_ms,
                reading_type=reading_type,
                origin="garmin", method="RMSSD",
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
    # 0.3.x renamed stressGraph -> stressValuesArray and reshaped entries from
    # {timestamp, stressLevel} dicts to [epoch_ms, level] pairs; accept both.
    graph = payload.get("stressGraph") or payload.get("stressValuesArray") or []
    if not graph:
        # Structured no-data day (0.3.x returns keyed objects with empty
        # arrays instead of {}) — a clean skip, not a parse error.
        return
    battery: dict[Any, Any] = {}
    for p in payload.get("bodyBatteryChart") or []:
        if isinstance(p, dict):
            battery[p.get("timestamp")] = p.get("value")
    for p in payload.get("bodyBatteryValuesArray") or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            battery[p[0]] = p[1]

    for point in graph:
        if isinstance(point, dict):
            ts = _epoch_ms(point.get("timestamp"), "stress timestamp")
            level = valid_stress_level(point.get("stressLevel"))
            bb = valid_body_battery(battery.get(point.get("timestamp")))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            ts = _epoch_ms(point[0], "stress timestamp")
            level = valid_stress_level(point[1])
            bb = valid_body_battery(battery.get(point[0]))
        else:
            raise NormalizationError(f"stress raw row {raw.id}: unusable point {point!r}")
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
            # P-02: only overwrite with plausibly-ranged values; an
            # out-of-range upstream value does NOT erase a previously-stored
            # plausible one (it is dropped at ingest, leaving existing
            # data intact).
            if level is not None:
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
            resting_hr=valid_resting_hr_bpm(payload.get("restingHeartRate")),
            steps=_int_or_none(payload.get("totalSteps")),
            floors=_int_or_none(payload.get("floorsAscended")),
            spo2_avg=valid_spo2_pct(payload.get("averageSpo2")),
        )
    else:  # body composition — weight is reported in grams upstream
        total = payload.get("totalAverage") or {}
        weight_g = _num(total.get("weight"))
        weight_kg = (weight_g / 1000.0) if weight_g is not None else None
        values = dict(
            weight_kg=valid_weight_kg(weight_kg),
            body_fat_pct=valid_body_fat_pct(total.get("bodyFat")),
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
        if val is not None and await _can_write_biometric(session, existing, key):
            set_biometric(existing, key, val, fetch.SOURCE)
    stats.biometrics_upserted += 1


async def _can_write_biometric(session: AsyncSession, row: DailyBiometric, field: str) -> bool:
    main = await selected_main_provider(session, row.user_id)
    if main is None or main == fetch.SOURCE or getattr(row, field) is None:
        return True
    # WHOOP does not measure these Garmin fields; its selection must not
    # freeze steps, floors, body fat, or VO2max supplied only by the watch.
    if main == "whoop" and field not in {"resting_hr", "spo2_avg", "weight_kg"}:
        return True
    return False
