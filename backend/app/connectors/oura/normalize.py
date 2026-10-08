"""Oura v2 mappings verified against public OpenAPI 1.41.

`daily_sleep` provides a DAILY PROVIDER SCORE; `/sleep` provides actual period
windows, stage durations and average overnight HRV. Contributor scores are
never durations. Sleep mean/minimum HR is not a resting-HR measurement.
Undated personal_info weight remains a profile snapshot in raw ingestion.
Source: https://cloud.ouraring.com/v2/static/json/openapi-1.41.json
"""
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.semantics import provider_semantics
from app.connectors.validation import valid_hrv_ms, valid_respiration_bpm, valid_sleep_score
from app.models.integration import RawIngest
from app.models.lab import FeedState, Observation
from app.models.wellness import HrvReading, SleepSession
from app.services.evidence import METRICS, record_observation, scope_lock, update_feed


class NormalizationError(Exception):
    """Malformed payloads stay unprocessed and replayable."""


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number.is_integer() and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_ts(value):
    if not isinstance(value, str):
        raise NormalizationError("A timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise NormalizationError("Invalid timestamp") from None
    if result.tzinfo is None:
        raise NormalizationError("Timestamp has no timezone")
    return result


def _day_from(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise NormalizationError("Invalid provider day") from None


def _id(payload):
    ident = payload.get("id")
    if not isinstance(ident, str) or not ident or len(ident) > 200:
        raise NormalizationError("Missing provider record ID")
    return ident


async def normalize_raw_row(session: AsyncSession, raw: RawIngest, payload: dict, tz: ZoneInfo, stats: NormalizerStats):
    await scope_lock(session, raw.user_id, "changes")
    if not isinstance(payload, dict):
        raise NormalizationError("Expected an object")
    if raw.payload_type == "daily_sleep":
        await _upsert_daily_sleep(session, raw, payload, tz, stats)
    elif raw.payload_type == "sleep":
        await _upsert_sleep_period(session, raw, payload, tz, stats)
    elif raw.payload_type == "heartrate":
        await _upsert_heartrate(session, raw, payload, stats)
    elif raw.payload_type == "personal_info":
        await _upsert_personal(session, raw, payload, stats)
    else:
        raise NormalizationError("Unsupported Oura collection")


async def _observation(session, raw, tz, metric, value, measured, source_id, context):
    await update_feed(session, raw.user_id, "oura", metric, "available" if value is not None else "not_measured", raw.fetched_at, measured)
    return await record_observation(session, user_id=raw.user_id, metric=metric, value=value,
        unit=METRICS[metric], origin="oura", source_record_id=source_id, measured_at=measured,
        timezone=tz.key, fetched_at=raw.fetched_at, acquisition="official_api",
        raw_ingest_id=raw.id, metadata=context)


async def _upsert_daily_sleep(session, raw, payload, tz, stats):
    ident, provider_day = _id(payload), _day_from(payload.get("day"))
    measured = _parse_ts(payload.get("timestamp"))
    score = valid_sleep_score(payload.get("score"))
    await _observation(session, raw, tz, "sleep_score", score, measured, "daily_sleep:" + ident,
        {"provider": "oura", "api_version": "v2", "feed": "daily_sleep", "provider_day": str(provider_day), "kind": "provider_estimate"})
    # A daily score applies to its provider day, not to a nap or an arbitrary
    # same-time Garmin session. Oura's scoring day and our wake-day remain distinct.
    rows = (await session.scalars(select(SleepSession).where(
        SleepSession.user_id == raw.user_id, SleepSession.origin == "oura",
        SleepSession.source_metrics["oura"]["provider_day"].astext == str(provider_day),
        SleepSession.source_metrics["oura"]["type"].astext == "long_sleep"))).all()
    for row in rows:
        row.sleep_score = score


async def _upsert_sleep_period(session, raw, payload, tz, stats):
    ident = _id(payload)
    start, end = _parse_ts(payload.get("bedtime_start")), _parse_ts(payload.get("bedtime_end"))
    if end <= start or end - start > timedelta(days=2):
        raise NormalizationError("Invalid sleep window")
    provider_day = _day_from(payload.get("day"))
    period_type = payload.get("type")
    previous = (await session.scalars(select(SleepSession).where(
        SleepSession.user_id == raw.user_id, SleepSession.origin == "oura",
        (SleepSession.source_metrics["oura"]["id"].astext == ident) | (SleepSession.start_time == start)))).all()
    if period_type in ("deleted", "rest"):
        for row in previous:
            await session.execute(delete(HrvReading).where(HrvReading.user_id == raw.user_id, HrvReading.origin == "oura", HrvReading.timestamp == row.end_time))
            await session.delete(row)
        retired = await session.execute(delete(Observation).where(Observation.user_id == raw.user_id, Observation.origin == "oura", Observation.source_record_id == "sleep:" + ident))
        if previous or retired.rowcount:
            # These snapshots can retain a deleted measurement, including in an
            # answer. Purge account-owned derivatives rather than reuse stale facts.
            from app.services.derived_data import clear_derived_health_data

            await clear_derived_health_data(session, raw.user_id)
        return
    total = _int(payload.get("total_sleep_duration"))
    if total is not None and total > (end - start).total_seconds():
        raise NormalizationError("Sleep duration exceeds the recorded window")
    stages = {dest: _int(payload.get(src)) for src, dest in (
        ("deep_sleep_duration", "deep_s"), ("rem_sleep_duration", "rem_s"),
        ("light_sleep_duration", "light_s"), ("awake_time", "awake_s"))}
    if all(stages[k] is not None for k in ("deep_s", "rem_s", "light_s")) and total is not None and sum(stages[k] for k in ("deep_s", "rem_s", "light_s")) > total + 60:
        raise NormalizationError("Sleep stages exceed the recorded total")
    score_raw = await session.scalar(select(RawIngest).where(RawIngest.user_id == raw.user_id, RawIngest.source == "oura", RawIngest.payload_type == "daily_sleep", RawIngest.raw_json["day"].astext == str(provider_day)).order_by(RawIngest.fetched_at.desc(), RawIngest.id.desc()).limit(1))
    score = valid_sleep_score(score_raw.raw_json.get("score")) if score_raw and period_type == "long_sleep" else None
    # Retiming a provider period removes its old canonical aggregate, not any
    # Garmin/WHOOP night with a similar window.
    for row in previous:
        if row.end_time != end or period_type != "long_sleep":
            await session.execute(delete(HrvReading).where(HrvReading.user_id == raw.user_id, HrvReading.origin == "oura", HrvReading.timestamp == row.end_time))
        if row.start_time != start:
            await session.execute(delete(HrvReading).where(HrvReading.user_id == raw.user_id, HrvReading.origin == "oura", HrvReading.timestamp == row.end_time))
            await session.delete(row)
    existing = next((r for r in previous if r.start_time == start), None)
    if existing is None:
        existing = SleepSession(user_id=raw.user_id, origin="oura", start_time=start)
        session.add(existing)
    existing.local_date = end.astimezone(tz).date()
    existing.end_time, existing.total_sleep_s = end, total
    for key, value in stages.items():
        setattr(existing, key, value)
    existing.sleep_score = score
    existing.respiration_avg = valid_respiration_bpm(payload.get("average_breath"))
    existing.restlessness = None
    existing.source_metrics = {"oura": {"id": ident, "provider_day": str(provider_day), "type": period_type,
        "efficiency": payload.get("efficiency"), "latency_s": _int(payload.get("latency")),
        "sleep_average_hr": payload.get("average_heart_rate"), "sleep_minimum_hr": payload.get("lowest_heart_rate"),
        "ring_id": payload.get("ring_id")}}
    stats.sleep_upserted += 1
    context = {"provider": "oura", "api_version": "v2", "feed": "sleep", "provider_day": str(provider_day),
               "reading_context": "overnight" if period_type == "long_sleep" else "sleep_period",
               "aggregation_window": "provider_sleep_period", "device_id": payload.get("ring_id")}
    await _observation(session, raw, tz, "sleep_duration", total / 3600 if total is not None else None, end, "sleep:" + ident, context)
    await _observation(session, raw, tz, "respiration", float(existing.respiration_avg) if existing.respiration_avg is not None else None, end, "sleep:" + ident, context)
    if period_type != "long_sleep":
        await session.execute(delete(Observation).where(Observation.user_id == raw.user_id, Observation.origin == "oura", Observation.source_record_id == "sleep:" + ident, Observation.metric == "hrv_overnight_rmssd"))
    if period_type == "long_sleep":
        value = valid_hrv_ms(payload.get("average_hrv"))
        await _observation(session, raw, tz, "hrv_overnight_rmssd", value, end, "sleep:" + ident, {**context, "hrv_method": provider_semantics("oura", "hrv").method})
        reading = await session.scalar(select(HrvReading).where(HrvReading.user_id == raw.user_id, HrvReading.origin == "oura", HrvReading.timestamp == end))
        if value is not None:
            if reading is None:
                session.add(HrvReading(user_id=raw.user_id, timestamp=end, origin="oura", method=provider_semantics("oura", "hrv").method, reading_type="overnight_avg", hrv_ms=value))
            else:
                reading.hrv_ms = value
            stats.hrv_upserted += 1
        elif reading is not None:
            await session.delete(reading)


async def _upsert_heartrate(session, raw, payload, stats):
    await update_feed(session, raw.user_id, "oura", "continuous_hr", "not_supported", raw.fetched_at)
    feed = await session.scalar(select(FeedState).where(FeedState.user_id == raw.user_id, FeedState.provider == "oura", FeedState.feed == "continuous_hr"))
    feed.details = {"storage": "raw_only", "reason": "No continuous wellness HR display is implemented; sleep HR is not resting HR."}


async def _upsert_personal(session, raw, payload, stats):
    # The official schema has no weight measurement date. Retrieval time is
    # not a measurement time, so preserve this undated profile only in raw.
    await update_feed(session, raw.user_id, "oura", "personal_info", "available", raw.fetched_at)
    feed = await session.scalar(select(FeedState).where(FeedState.user_id == raw.user_id, FeedState.provider == "oura", FeedState.feed == "personal_info"))
    feed.details = {"storage": "raw_only", "measurement_context": "undated_profile"}
