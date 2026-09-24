"""GET /dashboard/overview — the Overview page's single feed.

One round-trip for everything the home dashboard renders: today's scores
(DailyFeature), last night's sleep, the vitals strip (DailyBiometric +
overnight HRV), load block (acute/chronic/ACWR), today's activities,
integration health and open alerts. Deltas are computed against the 7-day
mean ending yesterday, so the SPA never re-fetches history to show
"+7 vs 7d".
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import Activity, Discipline
from app.models.features import DailyFeature
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.queries.snapshot import integrations_overview, open_alerts
from app.schemas.ui import OverviewOut, ScoreBlock

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

WINDOW_DAYS = 7
# How far the anchor may fall back when "today" has nothing recorded at all
# (fresh connect reality: the backfill populated history, today's row only
# appears once the device reports it — without this the home page renders
# empty for days despite years of data).
ANCHOR_FALLBACK_DAYS = 45


def _fl(value) -> float | None:
    return float(value) if value is not None else None


def _delta(today: float | int | None, history: list[float]) -> float | None:
    """Signed delta vs the mean of the previous WINDOW_DAYS days."""
    if today is None or not history:
        return None
    base = sum(history) / len(history)
    return round(float(today) - base, 1)


@router.get("/overview", response_model=OverviewOut)
async def dashboard_overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    date: str | None = Query(default=None, description="Local date YYYY-MM-DD"),
) -> OverviewOut:
    # Resolve the anchor local date (user's tz, §17). Default: today.
    tzname = user.timezone or "Europe/Rome"
    tz = ZoneInfo(tzname)
    now = datetime.now(UTC).astimezone(tz)
    anchor = now.date()
    explicit_date = False
    if date:
        try:
            anchor = datetime.strptime(date, "%Y-%m-%d").date()
            explicit_date = True
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "date must be YYYY-MM-DD"
            ) from exc
    window_start = anchor - timedelta(days=WINDOW_DAYS - 1)

    # --- anchor fallback -------------------------------------------------------
    # When the caller did not pin a date and "today" carries nothing recorded
    # (no feature row, no biometric, no sleep, no activity, no HRV sample),
    # slide the anchor back to the most recent day that does — within
    # ANCHOR_FALLBACK_DAYS. The UI labels this state so the dashboard never
    # renders a full panel of dashes while real history exists.
    anchor_is_today = anchor == now.date()
    if anchor_is_today and not explicit_date:
        from sqlalchemy import func, union_all

        fallback_floor = anchor - timedelta(days=ANCHOR_FALLBACK_DAYS)
        feat_days = select(DailyFeature.date).where(
            DailyFeature.user_id == user.id,
            DailyFeature.date >= fallback_floor,
            DailyFeature.date <= anchor,
        )
        bio_days = select(DailyBiometric.date).where(
            DailyBiometric.user_id == user.id,
            DailyBiometric.date >= fallback_floor,
            DailyBiometric.date <= anchor,
        )
        sleep_days = select(SleepSession.local_date).where(
            SleepSession.user_id == user.id,
            SleepSession.local_date >= fallback_floor,
            SleepSession.local_date <= anchor,
        )
        act_days = select(Activity.local_date).where(
            Activity.user_id == user.id,
            Activity.local_date >= fallback_floor,
            Activity.local_date <= anchor,
        )
        hrv_days = (
            select(func.date(HrvReading.timestamp).label("date"))
            .where(
                HrvReading.user_id == user.id,
                HrvReading.timestamp
                >= datetime(
                    fallback_floor.year, fallback_floor.month, fallback_floor.day,
                    tzinfo=tz,
                ),
                HrvReading.timestamp
                < datetime(anchor.year, anchor.month, anchor.day, tzinfo=tz)
                + timedelta(days=1),
            )
        )
        latest = (
            await session.execute(
                select(func.max(union_all(feat_days, bio_days, sleep_days, act_days, hrv_days).subquery().c.date))
            )
        ).scalar()
        if latest is not None and latest != anchor:
            anchor = latest
            window_start = anchor - timedelta(days=WINDOW_DAYS - 1)
    anchor_is_today = anchor == now.date()

    # --- DailyFeature window: anchor + the 7 days before it ------------------
    feat_rows = (
        await session.execute(
            select(DailyFeature)
            .where(
                DailyFeature.user_id == user.id,
                DailyFeature.date >= window_start - timedelta(days=WINDOW_DAYS),
                DailyFeature.date <= anchor,
            )
            .order_by(DailyFeature.date)
        )
    ).scalars().all()
    by_date = {f.date: f for f in feat_rows}
    feature = by_date.get(anchor)

    def _score(column) -> ScoreBlock:
        today_val = _fl(getattr(feature, column)) if feature else None
        history = [
            _fl(getattr(by_date[d], column))
            for d in (anchor - timedelta(days=i) for i in range(1, WINDOW_DAYS + 1))
            if d in by_date and getattr(by_date[d], column) is not None
        ]
        return ScoreBlock(value=today_val, delta_7d=_delta(today_val, history))

    # --- vitals ----------------------------------------------------------------
    biometric = (
        await session.scalars(
            select(DailyBiometric)
            .where(DailyBiometric.user_id == user.id, DailyBiometric.date == anchor)
            .limit(1)
        )
    ).first()
    bio_hist = (
        await session.execute(
            select(DailyBiometric)
            .where(
                DailyBiometric.user_id == user.id,
                DailyBiometric.date >= window_start - timedelta(days=WINDOW_DAYS),
                DailyBiometric.date < anchor,
            )
        )
    ).scalars().all()

    def _bio_mean(pick) -> list[float]:
        vals = [pick(b) for b in bio_hist]
        return [v for v in vals if v is not None]

    # --- last night's sleep (wake-date == anchor, §17) -------------------------
    night = (
        await session.scalars(
            select(SleepSession)
            .where(SleepSession.user_id == user.id, SleepSession.local_date == anchor)
            .order_by(SleepSession.end_time.desc())
            .limit(1)
        )
    ).first()

    # Overnight HRV mean + latest rolling baseline (annotation-canonical shape).
    day_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=tz)
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
    hrv_values = [float(r.hrv_ms) for r in hrv_rows]
    hrv_avg = round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None
    hrv_baseline = next(
        (_fl(r.rolling_baseline_ms) for r in reversed(hrv_rows) if r.rolling_baseline_ms),
        None,
    )

    # --- today's activities (compact cards) ------------------------------------
    acts = (
        await session.execute(
            select(Activity, Discipline.name)
            .outerjoin(Discipline, Activity.discipline_id == Discipline.id)
            .where(Activity.user_id == user.id, Activity.local_date == anchor)
            .order_by(Activity.start_time.desc())
        )
    ).all()
    activity_cards = [
        {
            "id": a.id,
            "start_time": a.start_time.isoformat(),
            "discipline": dname,
            "duration_s": a.duration_s,
            "distance_m": _fl(a.distance_m),
            "avg_hr": a.avg_hr,
            "avg_power": _fl(a.avg_power),
            "training_load": _fl(a.training_load),
            "calories": a.calories,
            "data_completeness": a.data_completeness,
        }
        for a, dname in acts
    ]

    sleep_block = None
    if night is not None:
        sleep_block = {
            "start_time": night.start_time.isoformat(),
            "end_time": night.end_time.isoformat(),
            "total_sleep_s": night.total_sleep_s,
            "sleep_score": _fl(night.sleep_score),
            "stages": {
                "deep_s": night.deep_s,
                "light_s": night.light_s,
                "rem_s": night.rem_s,
                "awake_s": night.awake_s,
            },
            "respiration_avg": _fl(night.respiration_avg),
            "spo2_avg": _fl(night.spo2_avg),
            "restlessness": _fl(night.restlessness),
        }

    norm_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=tz) - timedelta(days=30)
    norm_rows = (
        await session.scalars(
            select(HrvReading.hrv_ms).where(
                HrvReading.user_id == user.id,
                HrvReading.timestamp >= norm_start,
                HrvReading.timestamp
                < datetime(anchor.year, anchor.month, anchor.day, tzinfo=tz) + timedelta(days=1),
            )
        )
    ).all()
    hrv_norm_30d = (
        round(sum(float(v) for v in norm_rows) / len(norm_rows), 1) if norm_rows else None
    )

    integration_status = await integrations_overview(session, user.id)
    alerts = await open_alerts(session, user.id)

    rhr = biometric.resting_hr if biometric else None
    spo2 = _fl(biometric.spo2_avg) if biometric else None
    total_sleep_h = (
        round(night.total_sleep_s / 3600, 2) if night and night.total_sleep_s else None
    )

    return OverviewOut(
        date=anchor.isoformat(),
        anchor_is_today=anchor_is_today,
        readiness=_score("readiness_score"),
        recovery=_score("recovery_score"),
        strain=_score("strain_score"),
        sleep_score=ScoreBlock(
            value=_fl(night.sleep_score) if night else None,
            delta_7d=None,
        ),
        sleep_hours=total_sleep_h,
        hrv_ms=hrv_avg,
        hrv_baseline_ms=hrv_baseline,
        hrv_norm_30d=hrv_norm_30d,
        resting_hr=rhr,
        resting_hr_delta_7d=_delta(rhr, _bio_mean(lambda b: b.resting_hr)),
        spo2_avg=spo2,
        spo2_delta_7d=_delta(spo2, _bio_mean(lambda b: _fl(b.spo2_avg))),
        respiration_avg=_fl(night.respiration_avg) if night else None,
        steps=biometric.steps if biometric else None,
        weight_kg=_fl(biometric.weight_kg) if biometric else None,
        vo2max=_fl(biometric.vo2max) if biometric else None,
        acute_load=_fl(feature.training_load_acute) if feature else None,
        chronic_load=_fl(feature.training_load_chronic) if feature else None,
        acwr=_fl(feature.acwr) if feature else None,
        training_load_7d=_fl(feature.training_load_acute) if feature else None,
        activities=activity_cards,
        sleep=sleep_block,
        integration_status=integration_status,
        alerts=[
            {"type": a.type, "severity": a.severity, "message": a.message} for a in alerts
        ],
    )
