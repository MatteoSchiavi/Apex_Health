"""Feature engine orchestrator (§7, §23 Phase 2).

Computes one user's daily_features + discipline_features for a given LOCAL
day (§17), then upserts by primary key — re-running for the same (user, day)
is always a safe overwrite (§6.4 correction path; §17 idempotency).

Day D's inputs (all keyed on the USER'S LOCAL calendar):
- activities with local_date in [D-28, D]  -> load series, strain ceiling,
  discipline rows for D
- sleep_sessions with local_date in [D-28, D]  -> sleep quality/architecture
  (D's session = that morning's wake-up) + respiration baseline
- hrv_readings mapped to local days via users.timezone  -> HRV daily mean
- daily_biometrics rows in [D-28, D]  -> resting HR

Row honesty rules:
- A day with no wellness signal AND no activities gets no row (nothing was
  measured — fabricating a zero-day would be a lie). If a stale row exists
  for such a day (data was corrected away), the recompute deletes it.
- data_completeness is 'partial' when a wellness staple (HRV reading,
  resting HR, sleep session) is missing, or when an activity on D carries no
  HR signal at all (§17: incomplete sensor days are flagged, never silently
  scored as complete). Baseline warm-up (fewer than MIN_OBS observations)
  and the structural absence of a journal source do NOT flag partial — they
  are not sensor gaps.
- iron_status_flag stays NULL until the labs/medical module lands (Phase 4).
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features import baselines, discipline as discipline_metrics, load, scores
from app.features.weights import cutoff_for_local_day, load_weights
from app.models.activity import Activity, ActivityStream, Discipline
from app.models.features import DailyFeature, DisciplineFeature
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession

logger = logging.getLogger("features.engine")

WINDOW_DAYS = 28
DECAY_HALF_LIFE_DAYS = 3.0


def _local_day_instant_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC bounds of local `day`: [local midnight, next local midnight)."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(), end_local.astimezone()


def _readings_by_local_day(
    readings: list[HrvReading], tz: ZoneInfo, first_day: date, last_day: date
) -> dict[date, float]:
    """Mean HRV per LOCAL day (§17: an instant belongs to the day its local
    wall clock says — readings near midnight land on the right day)."""
    buckets: dict[date, list[float]] = {}
    for reading in readings:
        local_day = reading.timestamp.astimezone(tz).date()
        if first_day <= local_day <= last_day:
            buckets.setdefault(local_day, []).append(float(reading.hrv_ms))
    return {day: sum(values) / len(values) for day, values in buckets.items()}


async def _load_window(
    session: AsyncSession, user: User, day: date
) -> dict:
    """Everything the computation for `day` needs, in one round of queries."""
    tz = ZoneInfo(user.timezone)
    first_day = day - timedelta(days=WINDOW_DAYS)
    window_start_utc, _ = _local_day_instant_bounds(first_day, tz)
    _, day_end_utc = _local_day_instant_bounds(day, tz)

    activities = (
        (
            await session.scalars(
                select(Activity)
                .where(
                    Activity.user_id == user.id,
                    Activity.local_date >= first_day,
                    Activity.local_date <= day,
                )
                .order_by(Activity.start_time)
            )
        )
        .unique()
        .all()
    )
    activity_ids = [a.id for a in activities]
    streams: list[ActivityStream] = []
    if activity_ids:
        streams = (
            (
                await session.scalars(
                    select(ActivityStream).where(
                        ActivityStream.activity_id.in_(activity_ids)
                    )
                )
            )
            .unique()
            .all()
        )
    streams_by_activity: dict[int, list[ActivityStream]] = {}
    for stream in streams:
        streams_by_activity.setdefault(stream.activity_id, []).append(stream)

    sleep_sessions = (
        (
            await session.scalars(
                select(SleepSession).where(
                    SleepSession.user_id == user.id,
                    SleepSession.local_date >= first_day,
                    SleepSession.local_date <= day,
                )
            )
        )
        .unique()
        .all()
    )
    hrv_readings = (
        (
            await session.scalars(
                select(HrvReading).where(
                    HrvReading.user_id == user.id,
                    HrvReading.timestamp >= window_start_utc,
                    HrvReading.timestamp < day_end_utc,
                )
            )
        )
        .unique()
        .all()
    )
    biometrics = (
        (
            await session.scalars(
                select(DailyBiometric).where(
                    DailyBiometric.user_id == user.id,
                    DailyBiometric.date >= first_day,
                    DailyBiometric.date <= day,
                )
            )
        )
        .unique()
        .all()
    )
    disciplines = {
        d.id: d for d in (await session.scalars(select(Discipline))).all()
    }
    return {
        "tz": tz,
        "activities": activities,
        "streams_by_activity": streams_by_activity,
        "sleep_sessions": sleep_sessions,
        "hrv_by_local_day": _readings_by_local_day(
            hrv_readings, tz, first_day, day
        ),
        "biometrics": {b.date: b for b in biometrics},
        "disciplines": disciplines,
    }


def _compute_day(user: User, day: date, window: dict) -> dict | None:
    """Pure computation for one local day. Returns None when nothing was
    measured that day (no row should exist)."""
    tz = window["tz"]
    activities = window["activities"]
    disciplines: dict[int, Discipline] = window["disciplines"]

    hrv_by_day: dict[date, float] = window["hrv_by_local_day"]
    rhr_by_day: dict[date, float] = {
        b.date: float(b.resting_hr)
        for b in window["biometrics"].values()
        if b.resting_hr is not None
    }
    resp_by_day: dict[date, float] = {
        s.local_date: float(s.respiration_avg)
        for s in window["sleep_sessions"]
        if s.respiration_avg is not None
    }
    sleep_by_day: dict[date, SleepSession] = {
        s.local_date: s for s in window["sleep_sessions"]
    }

    # --- age & load series -------------------------------------------------
    hrm = load.hr_max_for(load.age_at(user.dob, day))
    activities_with_streams = [
        (a, window["streams_by_activity"].get(a.id, [])) for a in activities
    ]
    loads = load.daily_loads(activities_with_streams, hrm)
    loads_by_discipline: dict[str, dict[date, float]] = {}
    for activity, _streams in activities_with_streams:
        name = disciplines[activity.discipline_id].name
        trimp = load.activity_trimp(activity, _streams, hrm)
        if trimp is None:
            continue
        loads_by_discipline.setdefault(name, {})
        day_loads = loads_by_discipline[name]
        day_loads[activity.local_date] = (
            day_loads.get(activity.local_date, 0.0) + trimp
        )

    day_load = loads.get(day, 0.0)
    acute7 = load.rolling_sum(loads, day, 7)
    chronic28 = load.rolling_sum(loads, day, WINDOW_DAYS)
    acwr = load.acwr_from(acute7, chronic28)

    # --- baselines (prior window [D-28, D-1], D excluded) -------------------
    hrv_baseline = baselines.mean_baseline(hrv_by_day, day)
    rhr_baseline = baselines.mean_baseline(rhr_by_day, day)
    resp_baseline = baselines.mean_baseline(resp_by_day, day)

    hrv_dev = (
        None
        if hrv_baseline is None or day not in hrv_by_day
        else (hrv_by_day[day] - hrv_baseline) / hrv_baseline * 100.0
    )
    rhr_dev = (
        None
        if rhr_baseline is None or day not in rhr_by_day
        else rhr_by_day[day] - rhr_baseline
    )
    resp_dev = (
        None
        if resp_baseline is None or day not in resp_by_day
        else (resp_by_day[day] - resp_baseline) / resp_baseline * 100.0
    )

    # --- strain & ceiling ---------------------------------------------------
    # Today's ceiling: peak of the SAME 28-day window the chronic load uses.
    peak28 = max(
        (loads.get(day - timedelta(days=i), 0.0) for i in range(WINDOW_DAYS)),
        default=0.0,
    )
    # The prior day's strain score must be exactly what its own row saw:
    # ceiling = peak of ITS 28-day window ([D-29, D-1] from here).
    prior_day = day - timedelta(days=1)
    prior_peak = max(
        (
            loads.get(prior_day - timedelta(days=i), 0.0)
            for i in range(WINDOW_DAYS)
        ),
        default=0.0,
    )
    prior_strain = scores.strain_score(loads.get(prior_day, 0.0), prior_peak)

    # --- weights (§6.4 selection rule; loaded by the async caller with
    # cutoff = start of local day D) -----------------------------------------
    w = window["weights"]

    sleep_session = sleep_by_day.get(day)
    sleep_score = (
        float(sleep_session.sleep_score) if sleep_session and sleep_session.sleep_score is not None else None
    )
    recovery = scores.recovery_score(
        w["recovery_score"], hrv_dev, rhr_dev, sleep_score, prior_strain
    )
    strain = scores.strain_score(day_load, peak28)
    sleep_architecture = scores.sleep_architecture_score(
        w["sleep_architecture_score"],
        rem_pct=(
            float(sleep_session.rem_s) / float(sleep_session.total_sleep_s) * 100.0
            if sleep_session and sleep_session.rem_s and sleep_session.total_sleep_s
            else None
        ),
        deep_pct=(
            float(sleep_session.deep_s) / float(sleep_session.total_sleep_s) * 100.0
            if sleep_session and sleep_session.deep_s and sleep_session.total_sleep_s
            else None
        ),
        total_sleep_s=(
            float(sleep_session.total_sleep_s) if sleep_session else None
        ),
        awake_s=float(sleep_session.awake_s) if sleep_session else None,
    )
    readiness = scores.readiness_score(
        w["readiness_score"], recovery, sleep_architecture, acwr
    )
    illness = scores.illness_risk_score(w["illness_risk_score"], hrv_dev, rhr_dev, resp_dev)
    mean28, std28 = load.load_distribution(loads, day)
    injury = scores.injury_risk_score(w["injury_risk_score"], acwr, day_load, mean28, std28)
    cdfi = scores.cross_discipline_fatigue_index(loads_by_discipline, day)

    # --- honesty flags (§17) ------------------------------------------------
    # partial = a wellness staple is missing, or an activity on D carries no
    # HR signal at all (no stream HR and no avg_hr). Baseline warm-up and the
    # structural journal gap are NOT sensor gaps.
    missing_wellness = (
        day not in hrv_by_day or day not in rhr_by_day or sleep_session is None
    )
    activity_hr_gaps = any(
        not any(st.hr is not None for st in streams) and activity.avg_hr is None
        for activity, streams in activities_with_streams
        if activity.local_date == day
    )
    data_completeness = (
        "partial" if (missing_wellness or activity_hr_gaps) else "full"
    )

    daily_row = {
        "user_id": user.id,
        "date": day,
        "recovery_score": recovery,
        "strain_score": strain,
        "readiness_score": readiness,
        "training_load_acute": acute7,
        "training_load_chronic": chronic28 / 4.0,
        "acwr": acwr,
        "sleep_architecture_score": sleep_architecture,
        "hrv_deviation_from_baseline": hrv_dev,
        "illness_risk_score": illness,
        "injury_risk_score": injury,
        "iron_status_flag": None,  # labs/medical module lands later (Phase 4)
        "cross_discipline_fatigue_index": cdfi,
        "data_completeness": data_completeness,
    }

    # --- discipline rows for D (§17: scoped by discipline, never pooled) ---
    per_discipline: dict[int, dict[str, list[float]]] = {}
    ftp_estimates: dict[int, list[float]] = {}
    for activity, streams in activities_with_streams:
        if activity.local_date != day:
            continue
        disc = disciplines[activity.discipline_id]
        values = per_discipline.setdefault(activity.discipline_id, {})
        decoupling = discipline_metrics.aerobic_decoupling(activity, streams)
        if decoupling is not None:
            values.setdefault("decoupling", []).append(decoupling)
        ef = discipline_metrics.efficiency_factor(activity, streams, disc.name)
        if ef is not None:
            values.setdefault("ef", []).append(ef)
        ftp = discipline_metrics.ftp_estimate(activity, streams, disc.ftp_model_type)
        if ftp is not None:
            ftp_estimates.setdefault(activity.discipline_id, []).append(ftp)

    discipline_rows = []
    for discipline_id, values in per_discipline.items():
        decoupling = (
            sum(values["decoupling"]) / len(values["decoupling"])
            if "decoupling" in values
            else None
        )
        ef = sum(values["ef"]) / len(values["ef"]) if "ef" in values else None
        ftp = (
            max(ftp_estimates[discipline_id])
            if discipline_id in ftp_estimates
            else None
        )
        if decoupling is None and ef is None and ftp is None:
            continue
        discipline_rows.append(
            {
                "user_id": user.id,
                "discipline_id": discipline_id,
                "date": day,
                "estimated_ftp": ftp,
                "aerobic_decoupling_pct": decoupling,
                "efficiency_factor": ef,
            }
        )
    for discipline_id, estimates in ftp_estimates.items():
        if any(row["discipline_id"] == discipline_id for row in discipline_rows):
            continue
        discipline_rows.append(
            {
                "user_id": user.id,
                "discipline_id": discipline_id,
                "date": day,
                "estimated_ftp": max(estimates),
                "aerobic_decoupling_pct": None,
                "efficiency_factor": None,
            }
        )

    has_wellness = (
        day in hrv_by_day
        or day in rhr_by_day
        or sleep_session is not None
        or day in resp_by_day
    )
    has_activities = any(a.local_date == day for a in activities)
    if not has_wellness and not has_activities:
        return None
    return {"daily": daily_row, "discipline_rows": discipline_rows}


async def compute_user_day(
    session: AsyncSession, user: User, day: date
) -> dict | None:
    """Compute + upsert one local day. Returns the computed rows (or None if
    the day had no data and no row exists)."""
    window = await _load_window(session, user, day)
    tz = window["tz"]
    cutoff = cutoff_for_local_day(day, tz)
    window["weights"] = {
        feature: await load_weights(session, feature, cutoff)
        for feature in (
            "recovery_score",
            "readiness_score",
            "sleep_architecture_score",
            "illness_risk_score",
            "injury_risk_score",
        )
    }
    computed = _compute_day(user, day, window)
    if computed is None:
        existing = await session.get(DailyFeature, {"user_id": user.id, "date": day})
        if existing is not None:
            await session.delete(existing)
            await session.commit()
        return None
    await _upsert_rows(session, user.id, [computed])
    return computed


async def compute_user_range(
    session: AsyncSession, user: User, start: date, end: date
) -> dict:
    """Recompute a closed local-date range (the §6.4 correction path:
    'fix the feature_weights row, then manually re-run the nightly
    feature-engine task for the affected date range'). Idempotent per day."""
    computed_days = 0
    discipline_rows_written = 0
    day = start
    while day <= end:
        result = await compute_user_day(session, user, day)
        if result is not None:
            computed_days += 1
            discipline_rows_written += len(result["discipline_rows"])
        day += timedelta(days=1)
    return {
        "user_id": user.id,
        "start": start,
        "end": end,
        "days_computed": computed_days,
        "discipline_rows_written": discipline_rows_written,
    }


def _num(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(repr(round(value, 6)))


async def _upsert_rows(
    session: AsyncSession, user_id: int, computed: list[dict]
) -> None:
    for result in computed:
        daily = result["daily"]
        stmt = pg_insert(DailyFeature).values(
            **{
                key: (_num(value) if isinstance(value, float) else value)
                for key, value in daily.items()
            }
        )
        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in DailyFeature.__table__.columns
            if col.name not in ("user_id", "date")
        }
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "date"], set_=update_cols
            )
        )
        for row in result["discipline_rows"]:
            stmt_d = pg_insert(DisciplineFeature).values(
                **{
                    key: (_num(value) if isinstance(value, float) else value)
                    for key, value in row.items()
                }
            )
            update_cols_d = {
                col.name: stmt_d.excluded[col.name]
                for col in DisciplineFeature.__table__.columns
                if col.name not in ("user_id", "discipline_id", "date")
            }
            await session.execute(
                stmt_d.on_conflict_do_update(
                    index_elements=["user_id", "discipline_id", "date"],
                    set_=update_cols_d,
                )
            )
    await session.commit()
