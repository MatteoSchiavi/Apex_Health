"""Whoop normalizer: typed, idempotent upserts from raw JSON (§3 stage 3).

Annotation law enforcement happens HERE — see module docstring in
app/connectors/whoop/__init__.py for the full field-mapping table. The
unchanged laws: idempotent upserts; a populated canonical field is never
degraded to NULL by a provider that lacks it; provider-only quantities go
to source_metrics, keyed by provider.
"""

import logging
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.whoop.fetch import SOURCE
from app.connectors.validation import (
    valid_hrv_ms,
    valid_respiration_bpm,
    valid_resting_hr_bpm,
    valid_sleep_score,
    valid_spo2_pct,
    valid_weight_kg,
)
from app.models.activity import Activity, ActivitySourceLink
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.services.biometric_provenance import set_biometric
from app.connectors.garmin.normalize import NormalizerStats

logger = logging.getLogger("connectors.whoop.normalize")


class NormalizationError(Exception):
    """Raised for payloads this normalizer cannot interpret — the raw row
    stays processed=false and the pass continues (§3)."""


_KJ_PER_KCAL = 4.184


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_dt(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise NormalizationError(f"{label}: expected ISO timestamp, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"{label}: unparsable timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(UTC)


def _millis_to_s(value: object) -> int | None:
    ms = _int_or_none(value)
    return None if ms is None or ms < 0 else round(ms / 1000)


async def normalize_raw_row(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    """Dispatch one raw_ingest row to its typed upsert. Raises on payloads
    that cannot be parsed — the caller's savepoint keeps history intact."""
    # Take the account lock before canonical rows, matching ingest/erase order.
    from app.services.evidence import scope_lock
    await scope_lock(session, raw.user_id, "changes")
    if not isinstance(payload, dict):
        raise NormalizationError("WHOOP payload must be an object")
    score = payload.get("score")
    if score is not None and not isinstance(score, dict):
        raise NormalizationError("WHOOP score must be an object")
    for nested in ("stage_summary", "zone_durations"):
        if score and score.get(nested) is not None and not isinstance(score[nested], dict):
            raise NormalizationError(f"WHOOP {nested} must be an object")
    payload_type = getattr(raw, "payload_type", "")
    if payload_type == "sleep":
        await _upsert_sleep(session, raw, payload, tz, stats)
    elif payload_type == "recovery":
        await _upsert_recovery(session, raw, payload, tz, stats)
    elif payload_type == "cycle":
        await _upsert_cycle(session, raw, payload, tz, stats)
    elif payload_type == "workout":
        await _upsert_workout(session, raw, payload, tz, discipline_index, stats)
    elif payload_type == "body_measurement":
        await _upsert_body(session, raw, payload, tz, stats)
    else:
        logger.warning("whoop normalizer: unknown payload_type %s", payload_type)
    from app.connectors.whoop.evidence import index_whoop_payload

    await index_whoop_payload(session, raw, payload, tz)


# ----------------------------------------------------------------- sleep


async def _upsert_sleep(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    if payload.get("score_state") not in (None, "SCORED"):
        return
    start = _parse_dt(payload.get("start"), "sleep.start")
    end = _parse_dt(payload.get("end"), "sleep.end")
    if end <= start:
        raise NormalizationError(f"sleep raw row {getattr(raw, 'id', '?')}: end before start")
    if payload.get("nap") is True:
        return  # main sleep only — naps would distort nightly architecture

    score = payload.get("score") or {}
    stages = score.get("stage_summary") or {}
    # Whoop stages are MILLISECONDS; canonical is SECONDS (Garmin annotation).
    deep_s = _millis_to_s(stages.get("total_slow_wave_sleep_time_milli"))
    light_s = _millis_to_s(stages.get("total_light_sleep_time_milli"))
    rem_s = _millis_to_s(stages.get("total_rem_sleep_time_milli"))
    awake_s = _millis_to_s(stages.get("total_awake_time_milli"))
    # asleep time = light+deep+rem when the stages are all reported
    stage_parts = [deep_s, light_s, rem_s]
    total_sleep_s = (
        sum(stage_parts) if all(p is not None for p in stage_parts) else None
    )
    values = dict(
        user_id=getattr(raw, "user_id"),
        origin="whoop",
        source_metrics={"whoop": {"sleep_performance_pct": valid_sleep_score(score.get("sleep_performance_percentage"))}},
        local_date=end.astimezone(tz).date(),  # wake-up day, local calendar
        start_time=start,
        end_time=end,
        total_sleep_s=total_sleep_s,
        deep_s=deep_s,
        light_s=light_s,
        rem_s=rem_s,
        awake_s=awake_s,
        # Sleep need performance is provider context, not generic sleep quality.
        sleep_score=None,
        respiration_avg=valid_respiration_bpm(score.get("respiratory_rate")),
        spo2_avg=None,  # Whoop does not report SpO2 per sleep
        restlessness=None,  # Whoop does not report restlessness
    )

    existing = await session.scalar(
        select(SleepSession).where(
            SleepSession.user_id == values["user_id"],
            SleepSession.origin == "whoop",
            SleepSession.local_date == values["local_date"],
            SleepSession.start_time >= start - timedelta(hours=4),
            SleepSession.start_time <= start + timedelta(hours=4),
        ).order_by(SleepSession.start_time).limit(1)
    )
    if existing is None:
        session.add(SleepSession(**values))
    else:
        main = await _is_main(session, values["user_id"])
        for key, val in values.items():
            # Keep the row identity/timing from the device that created it.
            if key in {"user_id", "local_date", "start_time", "end_time"}:
                continue
            if val is not None and (main or getattr(existing, key) is None):
                setattr(existing, key, val)
    stats.sleep_upserted += 1


# -------------------------------------------------------------- recovery


async def _upsert_recovery(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    if payload.get("score_state") not in (None, "SCORED"):
        return  # PENDING_SCORE etc. — nothing to normalize yet
    score = payload.get("score") or {}
    # P-02 audit: drop implausible values before they enter typed tables.
    hrv = valid_hrv_ms(score.get("hrv_rmssd_milli"))
    rhr = valid_resting_hr_bpm(score.get("resting_heart_rate"))
    spo2 = valid_spo2_pct(score.get("spo2_percentage"))
    recovery_score = valid_sleep_score(score.get("recovery_score"))
    skin_temp = _num(score.get("skin_temp_celsius"))
    if hrv is None and rhr is None and spo2 is None and recovery_score is None and skin_temp is None:
        return
    user_id = getattr(raw, "user_id")

    # Recovery has no timestamp in the API. Sync joins related sleep/cycle
    # records; the wake time must never be replaced by the ingestion time.
    ts = _safe_dt(payload.get("sleep_end")) or _safe_dt(payload.get("cycle_start"))
    if ts is None:
        raise NormalizationError("recovery is missing related sleep/cycle timing context")
    day = ts.astimezone(tz).date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
    day_end = (datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(days=1)).astimezone(UTC)
    main = await _is_main(session, user_id)
    if hrv is not None:
        existing = await session.scalar(
            select(HrvReading).where(
                HrvReading.user_id == user_id,
                HrvReading.timestamp >= day_start,
                HrvReading.timestamp < day_end,
                HrvReading.reading_type == "overnight_avg",
                HrvReading.origin == "whoop",
            ).order_by(HrvReading.timestamp.desc()).limit(1)
        )
        if existing is None:
            session.add(
                HrvReading(
                    user_id=user_id,
                    timestamp=ts,
                    hrv_ms=hrv,
                    reading_type="overnight_avg",
                    origin="whoop", method="RMSSD",
                    rolling_baseline_ms=None,
                )
            )
            stats.hrv_upserted += 1
        elif main:
            existing.hrv_ms = hrv
            stats.hrv_upserted += 1

    # Daily biometrics: merge, never null-out; provider-only values live in
    # source_metrics["whoop"].
    day = ts.astimezone(tz).date()
    bio = await session.scalar(
        select(DailyBiometric).where(
            DailyBiometric.user_id == user_id, DailyBiometric.date == day
        )
    )
    if bio is None:
        bio = DailyBiometric(user_id=user_id, date=day)
        session.add(bio)
    # The main device updates canonical values; secondary measurements fill gaps.
    if rhr is not None and (main or bio.resting_hr is None):
        set_biometric(bio, "resting_hr", rhr, "whoop")
    if spo2 is not None and (main or bio.spo2_avg is None):
        set_biometric(bio, "spo2_avg", spo2, "whoop")
    metrics = dict(bio.source_metrics or {})
    whoop = dict(metrics.get("whoop") or {})
    for key, value in {
        "hrv_rmssd_ms": hrv, "resting_hr_bpm": rhr, "spo2_pct": spo2,
        "recovery_score": recovery_score, "sleep_id": payload.get("sleep_id"),
        "cycle_id": payload.get("cycle_id"), "measured_at": ts.isoformat(),
        "user_calibrating": score.get("user_calibrating"),
    }.items():
        if value is not None:
            whoop[key] = value
    if skin_temp is not None:
        whoop["skin_temp_c"] = skin_temp
    if whoop:
        metrics["whoop"] = whoop
        bio.source_metrics = metrics
    stats.biometrics_upserted += 1


# ----------------------------------------------------------------- cycle


async def _upsert_cycle(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    if payload.get("score_state") not in (None, "SCORED"):
        return
    score = payload.get("score") or {}
    day_strain = _num(score.get("strain"))
    avg_hr = _num(score.get("average_heart_rate"))
    if day_strain is None and avg_hr is None:
        return
    user_id = getattr(raw, "user_id")
    # A historical cycle must carry its own start, never an import timestamp.
    start = _safe_dt(payload.get("start"))
    if start is None:
        raise NormalizationError("cycle is missing its start timestamp")
    day = start.astimezone(tz).date()
    bio = await session.scalar(
        select(DailyBiometric).where(
            DailyBiometric.user_id == user_id, DailyBiometric.date == day
        )
    )
    if bio is None:
        bio = DailyBiometric(user_id=user_id, date=day)
        session.add(bio)
    metrics = dict(bio.source_metrics or {})
    whoop = dict(metrics.get("whoop") or {})
    if day_strain is not None:
        whoop["day_strain"] = day_strain
    if avg_hr is not None:
        whoop["cycle_avg_hr"] = avg_hr
    metrics["whoop"] = whoop
    bio.source_metrics = metrics
    stats.biometrics_upserted += 1


# --------------------------------------------------------------- workout


async def _upsert_workout(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    discipline_index: dict[str, int],
    stats: NormalizerStats,
) -> None:
    from app.connectors.whoop.type_map import resolve_discipline
    from app.services.device_merge import resolve_activity_winner

    if payload.get("score_state") not in (None, "SCORED"):
        return
    external_id = str(payload.get("id") or "")
    if not external_id:
        raise NormalizationError(f"workout raw row {getattr(raw, 'id', '?')}: missing id")
    user_id = getattr(raw, "user_id")
    start = _parse_dt(payload.get("start"), "workout.start")
    end = _parse_dt(payload.get("end"), "workout.end")
    if end <= start:
        raise NormalizationError("workout end must be after start")
    duration_s = round((end - start).total_seconds())
    score = payload.get("score") or {}
    kilojoule = _num(score.get("kilojoule"))
    strain = _num(score.get("strain"))
    if strain is not None and not 0 <= strain <= 21:
        strain = None
    zones = score.get("zone_durations") or {}
    zone_seconds = {
        key.removeprefix("zone_").removesuffix("_milli"): seconds
        for key, value in zones.items()
        if key.startswith("zone_") and key.endswith("_milli")
        and (seconds := _millis_to_s(value)) is not None
    }
    sport_name = payload.get("sport_name")
    discipline_id, fallback_note = resolve_discipline(sport_name, discipline_index)
    if fallback_note:
        stats.discipline_fallbacks.append(fallback_note)
    values = {
        "user_id": user_id, "discipline_id": discipline_id,
        "start_time": start, "local_date": start.astimezone(tz).date(),
        "start_tz_offset_minutes": _tz_offset_minutes(payload.get("timezone_offset"), tz, start),
        "duration_s": duration_s,
        "distance_m": _num(score.get("distance_meter")),
        "elevation_gain_m": _num(score.get("altitude_gain_meter")),
        "avg_hr": _int_or_none(score.get("average_heart_rate")),
        "max_hr": _int_or_none(score.get("max_heart_rate")),
        "calories": round(kilojoule / _KJ_PER_KCAL) if kilojoule is not None and kilojoule >= 0 else None,
    }
    provider_metrics = {
        "external_id": external_id, "sport_name": sport_name,
        "sport_id": payload.get("sport_id"), "strain": strain,
        "duration_s": duration_s, "start_time": start.isoformat(),
        "timezone_offset": payload.get("timezone_offset"),
        "avg_hr": values["avg_hr"], "max_hr": values["max_hr"],
        "distance_m": values["distance_m"], "calories": values["calories"],
        "percent_recorded": _num(score.get("percent_recorded")),
        "zone_seconds": zone_seconds or None,
        # Retain the existing consumer key without discarding sub-minute data.
        "zone_minutes": {key: value / 60 for key, value in zone_seconds.items()} or None,
    }
    link = await session.scalar(select(ActivitySourceLink).where(
        ActivitySourceLink.source == SOURCE,
        ActivitySourceLink.external_id == external_id,
        ActivitySourceLink.user_id == user_id,
    ))
    merged = False
    if link is not None:
        activity = await session.get(Activity, link.activity_id)
        if activity is None:
            raise NormalizationError(f"workout {external_id}: dangling activity link")
        other_sources = (await session.scalars(select(ActivitySourceLink.source).where(
            ActivitySourceLink.user_id == user_id,
            ActivitySourceLink.activity_id == activity.id,
            ActivitySourceLink.source != SOURCE,
        ))).all()
        write_canonical = not other_sources or await _is_main(session, user_id)
        link.raw_ingest_id = getattr(raw, "id", None)
        merged = bool(other_sources)
    else:
        user = await session.get(User, user_id)
        if user is None:
            raise NormalizationError("workout account no longer exists")
        decision = await resolve_activity_winner(session, user, start, duration_s, SOURCE)
        activity = (
            await session.get(Activity, decision.winner_activity_id)
            if decision.winner_activity_id is not None else None
        )
        # Distinct simultaneous sports are distinct efforts when both are known.
        if activity is not None and discipline_id is not None and activity.discipline_id is not None and activity.discipline_id != discipline_id:
            activity = None
        merged = activity is not None
        write_canonical = decision.write or activity is None
        if activity is None:
            activity = Activity(**values, training_load=None, data_completeness="partial")
            session.add(activity)
            await session.flush()
        session.add(ActivitySourceLink(
            user_id=user_id, activity_id=activity.id, source=SOURCE,
            external_id=external_id, raw_ingest_id=getattr(raw, "id", None),
        ))
    if write_canonical:
        for key, value in values.items():
            if value is not None:
                setattr(activity, key, value)
    metrics = dict(activity.source_metrics or {})
    whoop = dict(metrics.get(SOURCE) or {})
    whoop.update({key: value for key, value in provider_metrics.items() if value is not None})
    metrics[SOURCE] = whoop
    activity.source_metrics = metrics
    if merged:
        stats.activities_merged += 1
    else:
        stats.activities_upserted += 1


# ------------------------------------------------------------ body / util


async def _upsert_body(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    weight = valid_weight_kg(payload.get("weight_kilogram"))
    if weight is None:
        return
    user_id = getattr(raw, "user_id")
    # P-12 audit: NEVER fall back to datetime.now() — only the raw row's
    # fetched_at is a trustworthy measurement timestamp. Drop the record
    # when neither is present (backfill-safety).
    fetched = getattr(raw, "fetched_at", None)
    if fetched is None:
        logger.warning(
            "whoop body_measurement raw row %s: no fetched_at — dropping",
            getattr(raw, "id", "?"),
        )
        return
    day = fetched.astimezone(tz).date()
    bio = await session.scalar(
        select(DailyBiometric).where(
            DailyBiometric.user_id == user_id, DailyBiometric.date == day
        )
    )
    if bio is None:
        bio = DailyBiometric(user_id=user_id, date=day)
        session.add(bio)
    if bio.weight_kg is None or await _is_main(session, user_id):
        set_biometric(bio, "weight_kg", weight, "whoop")
    metrics = dict(bio.source_metrics or {})
    whoop = dict(metrics.get("whoop") or {})
    whoop.update({"weight_kg": weight, "body_measurement_fetched_at": fetched.isoformat()})
    for field in ("height_meter", "max_heart_rate"):
        value = _num(payload.get(field))
        if value is not None:
            whoop[field] = value
    metrics["whoop"] = whoop
    bio.source_metrics = metrics
    stats.biometrics_upserted += 1


async def _is_main(session: AsyncSession, user_id: int) -> bool:
    from app.services.device_merge import main_provider

    user = await session.get(User, user_id)
    return user is not None and await main_provider(session, user) == SOURCE


def _safe_dt(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            return _parse_dt(value, "timestamp")
        except NormalizationError:
            return None
    return None


def _tz_offset_minutes(raw_offset: object, tz: ZoneInfo, at: datetime) -> int | None:
    """Whoop sends "+02:00"-style offsets; canonical is minutes east of UTC
    at the activity's local wall clock (Garmin annotation)."""
    if isinstance(raw_offset, str) and len(raw_offset) == 6 and raw_offset[0] in {"+", "-"} and raw_offset[3] == ":":
        sign = 1 if raw_offset[0] == "+" else -1
        try:
            hh, mm = int(raw_offset[1:3]), int(raw_offset[4:6])
            if hh <= 23 and mm <= 59:
                return sign * (hh * 60 + mm)
        except ValueError:
            pass
    local = at.astimezone(tz)
    return int(local.utcoffset().total_seconds() // 60) if local.utcoffset() else 0
