"""Whoop normalizer: typed, idempotent upserts from raw JSON (§3 stage 3).

Annotation law enforcement happens HERE — see module docstring in
app/connectors/whoop/__init__.py for the full field-mapping table. The
unchanged laws: idempotent upserts; a populated canonical field is never
degraded to NULL by a provider that lacks it; provider-only quantities go
to source_metrics, keyed by provider.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.whoop.fetch import SOURCE
from app.models.activity import Activity, ActivitySourceLink
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
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


def _parse_dt(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise NormalizationError(f"{label}: expected ISO timestamp, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(f"{label}: unparsable timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed


def _millis_to_s(value: object) -> int | None:
    ms = _int_or_none(value)
    return None if ms is None else round(ms / 1000)


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


# ----------------------------------------------------------------- sleep


async def _upsert_sleep(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
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
        local_date=end.astimezone(tz).date(),  # wake-up day, local calendar
        start_time=start,
        end_time=end,
        total_sleep_s=total_sleep_s,
        deep_s=deep_s,
        light_s=light_s,
        rem_s=rem_s,
        awake_s=awake_s,
        # sleep_performance_percentage is 0-100 — same scale as Garmin's
        # sleep score band, so it maps onto sleep_score directly.
        sleep_score=_num(score.get("sleep_performance_percentage")),
        respiration_avg=_num(score.get("respiratory_rate")),
        spo2_avg=None,  # Whoop does not report SpO2 per sleep
        restlessness=None,  # Whoop does not report restlessness
    )

    existing = await session.scalar(
        select(SleepSession).where(
            SleepSession.user_id == values["user_id"],
            SleepSession.start_time == start,
        )
    )
    if existing is None:
        session.add(SleepSession(**values))
    else:
        for key, val in values.items():
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
    hrv = _num(score.get("hrv_rmssd_milli"))
    rhr = _num(score.get("resting_heart_rate"))
    spo2 = _num(score.get("spo2_percentage"))
    recovery_score = _num(score.get("recovery_score"))
    skin_temp = _num(score.get("skin_temp_celsius"))
    if hrv is None and rhr is None and spo2 is None and recovery_score is None:
        return
    user_id = getattr(raw, "user_id")

    # Overnight-average HRV: anchor at the recovery's related cycle start in
    # user-local morning — Whoop's recovery row represents the state at the
    # end of the sleep that closed the previous cycle. reading_type mirrors
    # Garmin's "overnight_avg".
    cycle_start = _safe_dt(payload.get("cycle_start"))
    ts = cycle_start or (getattr(raw, "fetched_at", None) or datetime.now(tz=tz))
    if hrv is not None:
        existing = await session.scalar(
            select(HrvReading).where(
                HrvReading.user_id == user_id,
                HrvReading.timestamp == ts,
                HrvReading.reading_type == "overnight_avg",
            )
        )
        if existing is None:
            session.add(
                HrvReading(
                    user_id=user_id,
                    timestamp=ts,
                    hrv_ms=hrv,
                    reading_type="overnight_avg",
                    rolling_baseline_ms=None,
                )
            )
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
    if rhr is not None and bio.resting_hr is None:
        bio.resting_hr = round(rhr)
    if spo2 is not None and bio.spo2_avg is None:
        bio.spo2_avg = spo2
    metrics = dict(bio.source_metrics or {})
    whoop = dict(metrics.get("whoop") or {})
    if recovery_score is not None:
        whoop["recovery_score"] = recovery_score
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
    start = _safe_dt(payload.get("start")) or (
        getattr(raw, "fetched_at", None) or datetime.now(tz=tz)
    )
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

    if payload.get("score_state") not in (None, "SCORED"):
        return
    external_id = str(payload.get("id") or "")
    if not external_id:
        raise NormalizationError(f"workout raw row {getattr(raw, 'id', '?')}: missing id")
    user_id = getattr(raw, "user_id")
    start = _parse_dt(payload.get("start"), "workout.start")
    end = _parse_dt(payload.get("end"), "workout.end")
    duration_s = max(int((end - start).total_seconds()), 0)

    score = payload.get("score") or {}
    avg_hr = _int_or_none(score.get("average_heart_rate"))
    max_hr = _int_or_none(score.get("max_heart_rate"))
    kilojoule = _num(score.get("kilojoule"))
    calories = round(kilojoule / _KJ_PER_KCAL) if kilojoule is not None else None
    distance_m = _int_or_none(score.get("distance_meter"))
    altitude_gain = _num(score.get("altitude_gain_meter"))
    strain = _num(score.get("strain"))
    zones = score.get("zone_durations") or {}

    sport_name = payload.get("sport_name")
    discipline_id, fallback_note = resolve_discipline(sport_name, discipline_index)
    if fallback_note:
        stats.discipline_fallbacks.append(fallback_note)

    link = await session.scalar(
        select(ActivitySourceLink).where(
            ActivitySourceLink.source == SOURCE,
            ActivitySourceLink.external_id == external_id,
        )
    )
    activity_id: int
    if link is None:
        # Device priority law (services/device_merge.py): when the MAIN
        # device already recorded this same effort, Whoop does NOT get its
        # own canonical row — its identity link attaches to the winner and
        # the Whoop-specific quantities (strain, zone minutes) merge into
        # source_metrics so nothing measured is lost.
        from app.services.device_merge import resolve_activity_winner

        decision = await resolve_activity_winner(
            session,
            await session.get(User, getattr(raw, "user_id")),
            start,
            duration_s,
            SOURCE,
        )
        if not decision.write and decision.winner_activity_id is not None:
            winner = await session.get(Activity, decision.winner_activity_id)
            if winner is not None:
                session.add(
                    ActivitySourceLink(
                        activity_id=winner.id,
                        source=SOURCE,
                        external_id=external_id,
                        raw_ingest_id=getattr(raw, "id", None),
                    )
                )
                whoop_meta = {
                    "sport_name": sport_name,
                    "strain": strain,
                    "duration_s": duration_s,
                    "avg_hr": avg_hr,
                    "calories": calories,
                }
                merged = dict(winner.source_metrics or {})
                whoop_block = merged.get("whoop") or {}
                merged["whoop"] = {**whoop_block, **whoop_meta}
                winner.source_metrics = merged
                stats.activities_merged += 1
                return
        activity = Activity(
            user_id=user_id,
            discipline_id=discipline_id,
            start_time=start,
            start_tz_offset_minutes=_tz_offset_minutes(payload.get("timezone_offset"), tz, start),
            local_date=start.astimezone(tz).date(),
            duration_s=duration_s,
            distance_m=distance_m,
            elevation_gain_m=altitude_gain,
            avg_hr=avg_hr,
            max_hr=max_hr,
            calories=calories,
            training_load=None,  # strain is NOT TRIMP-load (annotation law)
            data_completeness="partial",  # summary-only, no streams
            source_metrics={
                "whoop": {
                    "sport_name": sport_name,
                    "strain": strain,
                    "zone_minutes": {
                        k.replace("zone_", "").replace("_milli", ""): round(v / 60000)
                        for k, v in zones.items()
                        if isinstance(v, (int, float))
                    }
                    or None,
                }
            },
        )
        session.add(activity)
        await session.flush()
        activity_id = activity.id
        session.add(
            ActivitySourceLink(
                activity_id=activity_id,
                source=SOURCE,
                external_id=external_id,
                raw_ingest_id=getattr(raw, "id", None),
            )
        )
        stats.activities_upserted += 1
    else:
        # §17 upsert law: this source's own row updates in place; a populated
        # canonical field is never degraded to NULL.
        activity = await session.get(Activity, link.activity_id)
        if activity is None:  # pragma: no cover - dangling link
            raise NormalizationError(f"workout {external_id}: dangling activity link")
        activity_id = activity.id
        if duration_s:
            activity.duration_s = duration_s
        if avg_hr is not None:
            activity.avg_hr = avg_hr
        if max_hr is not None:
            activity.max_hr = max_hr
        if calories is not None:
            activity.calories = calories
        if distance_m is not None:
            activity.distance_m = distance_m
        if altitude_gain is not None:
            activity.elevation_gain_m = altitude_gain
        if discipline_id is not None:
            activity.discipline_id = discipline_id
        metrics = dict(activity.source_metrics or {})
        whoop = dict(metrics.get("whoop") or {})
        whoop["sport_name"] = sport_name
        if strain is not None:
            whoop["strain"] = strain
        metrics["whoop"] = whoop
        activity.source_metrics = metrics
        stats.activities_upserted += 1


# ------------------------------------------------------------ body / util


async def _upsert_body(
    session: AsyncSession,
    raw: object,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    weight = _num(payload.get("weight_kilogram"))
    if weight is None:
        return
    user_id = getattr(raw, "user_id")
    fetched = getattr(raw, "fetched_at", None) or datetime.now(tz=tz)
    day = fetched.astimezone(tz).date()
    bio = await session.scalar(
        select(DailyBiometric).where(
            DailyBiometric.user_id == user_id, DailyBiometric.date == day
        )
    )
    if bio is None:
        bio = DailyBiometric(user_id=user_id, date=day)
        session.add(bio)
    if bio.weight_kg is None:
        bio.weight_kg = weight
    stats.biometrics_upserted += 1


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
    if isinstance(raw_offset, str) and len(raw_offset) >= 5:
        sign = 1 if raw_offset[0] == "+" else -1
        try:
            hh, mm = int(raw_offset[1:3]), int(raw_offset[4:6])
            return sign * (hh * 60 + mm)
        except ValueError:
            pass
    local = at.astimezone(tz)
    return int(local.utcoffset().total_seconds() // 60) if local.utcoffset() else None
