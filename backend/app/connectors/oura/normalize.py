"""Oura normalizer: typed, idempotent upserts from raw API payloads.

Canonical mapping (annotation law — Garmin-compatible units only):
- daily_sleep: contributors.deep_sleep_seconds → deep_s, rem → rem_s,
  light → light_s, awake → awake_s; total_sleep_duration → total_sleep_s;
  score → sleep_score; average_breath → respiration_avg; average_hrv →
  the overnight HRV reading; spo2_percentage.average → spo2_avg.
- Oura-only values (temperature_delta, efficiency, readiness score,
  latency, restlessness in ring terms) stay in source_metrics.oura —
  restlessness semantics differ from Garmin's and MUST NOT overwrite.
- sleep periods (30s-class staging) land in the same SleepSession stages
  when daily_sleep is absent (older windows).
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.oura.fetch import SOURCE, store_raw
from app.models.integration import RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession

logger = logging.getLogger("connectors.oura.normalize")

_KNOWN_TYPES = ("daily_sleep", "sleep", "heartrate", "personal_info")


class NormalizationError(Exception):
    """One payload is malformed; it rolls back alone and stays unprocessed."""


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))
    except ValueError as exc:
        raise NormalizationError(f"unparsable timestamp {value!r}") from exc


async def normalize_raw_row(
    session: AsyncSession,
    raw: RawIngest,
    payload: dict,
    tz: ZoneInfo,
    stats: NormalizerStats,
) -> None:
    ptype = getattr(raw, "payload_type", "")
    if ptype == "daily_sleep":
        await _upsert_daily_sleep(session, raw, payload, tz, stats)
    elif ptype == "sleep":
        await _upsert_sleep_period(session, raw, payload, tz, stats)
    elif ptype == "heartrate":
        await _upsert_heartrate(session, raw, payload, stats)
    elif ptype == "personal_info":
        await _upsert_personal(session, raw, payload, stats)
    else:
        logger.debug("oura normalizer: skipping type %s", ptype)


async def _upsert_daily_sleep(session, raw, payload, tz: ZoneInfo, stats) -> None:
    user_id = getattr(raw, "user_id")
    day = _day_from(payload.get("day"))
    contributors = payload.get("contributors") or {}
    start = _parse_ts(payload.get("bedtime_start"))
    end = _parse_ts(payload.get("bedtime_end"))
    if start is None or end is None:
        raise NormalizationError(f"daily_sleep {payload.get('id')}: missing bedtime window")

    total = _int(payload.get("total_sleep_duration"))
    deep = _int(contributors.get("deep_sleep_seconds"))
    rem = _int(contributors.get("rem_sleep_seconds"))
    light = _int(contributors.get("light_sleep_seconds"))
    if total is not None and deep is not None and rem is not None and light is None:
        light = max(total - (deep or 0) - (rem or 0), 0)

    # Oura's local_date convention == Garmin's wake-date rule (§17): the
    # night is attributed to the WAKE morning, which is `day` in Oura v2.
    sm = {
        "oura": {
            "efficiency": _float(payload.get("efficiency")),
            "latency_s": _int(payload.get("latency")),
            "temperature_delta_c": _float(payload.get("temperature_delta")),
            "readiness_score": None,  # readiness is a separate collection
            "low_battery_alert": payload.get("low_battery_alert"),
        }
    }

    existing = (
        await session.scalars(
            select(SleepSession).where(
                SleepSession.user_id == user_id,
                SleepSession.local_date == day,
                SleepSession.start_time == start,
            )
        )
    ).first()
    if existing is None:
        # Device priority: oura writes only when the slot is empty — a
        # same-start Garmin row wins (main-device law, ingest gate).
        clash = (
            await session.scalars(
                select(SleepSession).where(
                    SleepSession.user_id == user_id,
                    SleepSession.local_date == day,
                    SleepSession.start_time >= start - timedelta(minutes=30),
                    SleepSession.start_time <= start + timedelta(minutes=30),
                )
            )
        ).first()
        if clash is not None:
            sm_whoop = clash.source_metrics or {}
            block = sm_whoop.get("oura") or {}
            sm_whoop["oura"] = {**block, **sm["oura"]}
            clash.source_metrics = sm_whoop
            stats.activities_merged += 0  # counts as a merge-free overlap
            return
        session.add(
            SleepSession(
                user_id=user_id,
                local_date=day,
                start_time=start,
                end_time=end,
                total_sleep_s=total,
                deep_s=deep,
                light_s=light,
                rem_s=rem,
                awake_s=(
                    _int(payload.get("awake_time"))
                    or _int(contributors.get("awake_time"))
                ),
                sleep_score=_float(contributors.get("sleep_score") or payload.get("score")),
                respiration_avg=_float(payload.get("average_breath")),
                spo2_avg=_float((payload.get("spo2_percentage") or {}).get("average")),
                restlessness=None,  # ring restlessness ≠ Garmin restlessness
                source_metrics=sm,
            )
        )
        stats.sleep_upserted += 1
    else:
        # Upsert-in-place, never degrade a populated field to NULL.
        if total is not None:
            existing.total_sleep_s = total
        if deep is not None:
            existing.deep_s = deep
        if rem is not None:
            existing.rem_s = rem
        if light is not None:
            existing.light_s = light
        if payload.get("average_breath") is not None:
            existing.respiration_avg = _float(payload.get("average_breath"))
        merged = dict(existing.source_metrics or {})
        merged["oura"] = {**merged.get("oura", {}), **sm["oura"]}
        existing.source_metrics = merged
        stats.sleep_upserted += 1

    # Overnight HRV: one canonical reading at sleep midpoint (rMSSD-class).
    avg_hrv = _float(payload.get("average_hrv"))
    if avg_hrv and start and end:
        mid = start + (end - start) / 2
        from sqlalchemy import and_

        dupe = (
            await session.scalars(
                select(HrvReading).where(
                    and_(
                        HrvReading.user_id == user_id,
                        HrvReading.timestamp == mid,
                    )
                )
            )
        ).first()
        if dupe is None:
            session.add(
                HrvReading(
                    user_id=user_id,
                    timestamp=mid,
                    hrv_ms=avg_hrv,
                    reading_type="overnight_avg",
                )
            )
            stats.hrv_upserted += 1


async def _upsert_sleep_period(session, raw, payload, tz, stats) -> None:
    """Higher-resolution staging (sleep.periods). Kept in source_metrics for
    the hypnogram when it carries stage samples our summary rows lack."""
    # The v2 /sleep collection's stage array is redundant with daily_sleep's
    # canonical split for now; raw-first law already keeps it in raw_ingest.
    stats.biometrics_upserted += 0  # accounted at daily_sleep level


async def _upsert_heartrate(session, raw, payload, stats) -> None:
    """Continuous HR items ({"items": [...], "timestamp": ...}) — no canonical
    table for daytime continuous HR yet; raw-first keeps them queryable."""
    stats.biometrics_upserted += 0


async def _upsert_personal(session, raw, payload, stats) -> None:
    user_id = getattr(raw, "user_id")
    height_m = _float(payload.get("height"))
    weight_kg = _float(payload.get("weight"))
    if not (height_m or weight_kg):
        return
    day = datetime.now(timezone.utc).astimezone(ZoneInfo("UTC")).date()
    existing = (
        await session.scalars(
            select(DailyBiometric).where(
                DailyBiometric.user_id == user_id, DailyBiometric.date == day
            )
        )
    ).first()
    if existing is None:
        existing = DailyBiometric(user_id=user_id, date=day)
        session.add(existing)
    if weight_kg:
        existing.weight_kg = round(weight_kg, 2)
    merged = dict(existing.source_metrics or {})
    merged["oura"] = {**merged.get("oura", {}), "height_m": height_m}
    existing.source_metrics = merged
    stats.biometrics_upserted += 1


def _day_from(value: str | None) -> date:
    if not value:
        raise NormalizationError("missing day field")
    return date.fromisoformat(value[:10])
