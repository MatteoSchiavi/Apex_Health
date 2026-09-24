"""Sleep API for the web UI: range list + night detail.

- GET /sleep            — sessions across a local-date range (wake-date §17)
- GET /sleep/{date}     — one night: session + overnight biometrics + HRV series

The night detail powers the hypnogram page; HRV readings are returned in
timestamp order so the SPA can plot the overnight envelope without a second
round-trip.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import BigInteger, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.connectors.garmin.stages import extract_sleep_stage_segments
from app.core.db import get_session
from app.models.integration import RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.schemas.ui import SleepDayOut, SleepListOut, SleepSessionOut, SleepStagesOut

router = APIRouter(prefix="/sleep", tags=["sleep"])


def _fl(value) -> float | None:
    return float(value) if value is not None else None


def _session_out(s: SleepSession) -> SleepSessionOut:
    return SleepSessionOut(
        local_date=s.local_date,
        start_time=s.start_time,
        end_time=s.end_time,
        total_sleep_s=s.total_sleep_s,
        deep_s=s.deep_s,
        light_s=s.light_s,
        rem_s=s.rem_s,
        awake_s=s.awake_s,
        sleep_score=_fl(s.sleep_score),
        respiration_avg=_fl(s.respiration_avg),
        spo2_avg=_fl(s.spo2_avg),
        restlessness=_fl(s.restlessness),
    )


@router.get("", response_model=SleepListOut)
async def list_sleep(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=42, ge=1, le=120),
) -> SleepListOut:
    end_d = end or date.today()
    start_d = start or end_d - timedelta(days=limit - 1)
    rows = (
        await session.scalars(
            select(SleepSession)
            .where(
                SleepSession.user_id == user.id,
                SleepSession.local_date >= start_d,
                SleepSession.local_date <= end_d,
            )
            .order_by(SleepSession.local_date.desc(), SleepSession.end_time.desc())
            .limit(limit)
        )
    ).all()
    # One row per local_date (the longest night wins).
    best: dict[date, SleepSession] = {}
    for s in rows:
        if s.local_date not in best or (s.total_sleep_s or 0) > (
            best[s.local_date].total_sleep_s or 0
        ):
            best[s.local_date] = s
    items = [_session_out(best[d]) for d in sorted(best, reverse=True)]
    return SleepListOut(
        items=items, start_date=start_d.isoformat(), end_date=end_d.isoformat()
    )


@router.get("/{day}", response_model=SleepDayOut)
async def sleep_day(
    day: date,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SleepDayOut:
    tz = ZoneInfo(user.timezone or "Europe/Rome")
    rows = (
        await session.scalars(
            select(SleepSession)
            .where(SleepSession.user_id == user.id, SleepSession.local_date == day)
            .order_by(SleepSession.end_time.desc())
        )
    ).all()
    night = rows[0] if rows else None

    biometric = (
        await session.scalars(
            select(DailyBiometric)
            .where(DailyBiometric.user_id == user.id, DailyBiometric.date == day)
            .limit(1)
        )
    ).first()

    # HRV readings for the local calendar day (00:00→24:00 user-local).
    day_start = datetime(day.year, day.month, day.day, tzinfo=tz)
    hrv_rows = (
        await session.scalars(
            select(HrvReading)
            .where(
                HrvReading.user_id == user.id,
                HrvReading.timestamp >= day_start,
                HrvReading.timestamp < day_start + timedelta(days=1),
            )
            .order_by(HrvReading.timestamp)
        )
    ).all()

    bio_out = {}
    if biometric is not None:
        bio_out = {
            "resting_hr": biometric.resting_hr,
            "spo2_avg": _fl(biometric.spo2_avg),
            "respiration_avg": _fl(night.respiration_avg) if night else None,
            "weight_kg": _fl(biometric.weight_kg),
            "steps": biometric.steps,
        }

    return SleepDayOut(
        date=day.isoformat(),
        session=_session_out(night) if night else None,
        biometrics=bio_out,
        hrv_readings=[
            {
                "timestamp": r.timestamp.isoformat(),
                "hrv_ms": float(r.hrv_ms),
                "reading_type": r.reading_type,
                "rolling_baseline_ms": _fl(r.rolling_baseline_ms),
            }
            for r in hrv_rows
        ],
    )


@router.get("/{day}/stages", response_model=SleepStagesOut)
async def sleep_stages(
    day: date,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SleepStagesOut:
    """Epoch-level stage timeline (hypnogram) for one night.

    Reads the STORED RAW Garmin payload — no remote call, no invention:
    when the night has no stage timeline in raw_ingest (non-Garmin night,
    legacy row) the response carries segments=None and the UI falls back to
    the proportional stage bar. Anchored on the normalized session's end
    time so the raw row match survives midnight/fetch-order jitter."""
    tz = ZoneInfo(user.timezone or "Europe/Rome")
    night = (
        await session.scalars(
            select(SleepSession)
            .where(SleepSession.user_id == user.id, SleepSession.local_date == day)
            .order_by(SleepSession.total_sleep_s.desc().nulls_last(), SleepSession.end_time.desc())
            .limit(1)
        )
    ).first()
    if night is None:
        return SleepStagesOut(date=day.isoformat(), segments=None, source=None)

    # Match raw rows by the DTO's sleep end epoch (ms) within ±6h of the
    # normalized end_time — the same value the normalizer used, so a hit is
    # the exact night, not merely the same calendar day.
    end_ms = int(night.end_time.timestamp() * 1000)
    end_key = RawIngest.raw_json["dailySleepDTO", "sleepEndTimestampGMT"]
    row = (
        await session.scalars(
            select(RawIngest)
            .where(
                RawIngest.user_id == user.id,
                RawIngest.source == "garmin",
                RawIngest.payload_type == "sleep",
                func.cast(end_key.astext, BigInteger).between(end_ms - 6 * 3600_000, end_ms + 6 * 3600_000),
            )
            .order_by(RawIngest.fetched_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return SleepStagesOut(date=day.isoformat(), segments=None, source="garmin")

    segments = extract_sleep_stage_segments(row.raw_json)
    return SleepStagesOut(
        date=day.isoformat(),
        segments=segments,
        source="garmin" if segments else None,
    )
