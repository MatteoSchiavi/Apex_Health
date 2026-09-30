"""Metric/activity reads (§8.2 shared query layer, added in Phase 5).

get_metric_trend serves §8.3's get_metric_trend tool: daily_features rows,
or discipline_features rows when a discipline is scoped (§17 discipline
decoupling). get_activity_summary aggregates activities over a window.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, Discipline
from app.models.features import DailyFeature, DisciplineFeature

# Friendly metric names → DailyFeature columns (§8.3 compact table output).
DAILY_METRICS: dict[str, str] = {
    "readiness": "readiness_score",
    "recovery": "recovery_score",
    "strain": "strain_score",
    "acwr": "acwr",
    "acute_load": "training_load_acute",
    "chronic_load": "training_load_chronic",
    "sleep_architecture": "sleep_architecture_score",
    "hrv_deviation_pct": "hrv_deviation_from_baseline",
    "illness_risk": "illness_risk_score",
    "injury_risk": "injury_risk_score",
    "cross_discipline_fatigue": "cross_discipline_fatigue_index",
    "iron_status_flag": "iron_status_flag",
}

# Discipline-scoped metrics (§17: discipline features are decoupled by design).
DISCIPLINE_METRICS: dict[str, str] = {
    "estimated_ftp": "estimated_ftp",
    "aerobic_decoupling_pct": "aerobic_decoupling_pct",
    "efficiency_factor": "efficiency_factor",
}


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def get_metric_trend(
    session: AsyncSession,
    user_id: int,
    metric: str,
    start_date: date,
    end_date: date,
    discipline_id: int | None = None,
) -> list[dict]:
    """One metric's daily series over [start_date, end_date] (§8.3). Raises
    ValueError for unknown metric names — the agent loop converts that into a
    tool-error result the model can read and correct."""
    if discipline_id is not None:
        column = DISCIPLINE_METRICS.get(metric)
        if column is None:
            raise ValueError(
                f"unknown discipline metric {metric!r} "
                f"(available: {sorted(DISCIPLINE_METRICS)})"
            )
        rows = (
            await session.execute(
                select(DisciplineFeature.date, DisciplineFeature.__table__.c[column])
                .where(
                    DisciplineFeature.user_id == user_id,
                    DisciplineFeature.discipline_id == discipline_id,
                    DisciplineFeature.date >= start_date,
                    DisciplineFeature.date <= end_date,
                )
                .order_by(DisciplineFeature.date)
            )
        ).all()
    else:
        column = DAILY_METRICS.get(metric)
        if column is None:
            raise ValueError(
                f"unknown metric {metric!r} (available: {sorted(DAILY_METRICS)})"
            )
        rows = (
            await session.execute(
                select(DailyFeature.date, DailyFeature.__table__.c[column])
                .where(
                    DailyFeature.user_id == user_id,
                    DailyFeature.date >= start_date,
                    DailyFeature.date <= end_date,
                )
                .order_by(DailyFeature.date)
            )
        ).all()
    return [{"date": d.isoformat(), "metric": metric, "value": _num(v)} for d, v in rows]


async def get_activity_summary(
    session: AsyncSession,
    user_id: int,
    start_date: date,
    end_date: date,
    discipline_id: int | None = None,
) -> dict:
    """Aggregates from activities over [start_date, end_date] (§8.3): totals
    plus a per-discipline breakdown."""
    conditions = [
        Activity.user_id == user_id,
        Activity.local_date >= start_date,
        Activity.local_date <= end_date,
    ]
    if discipline_id is not None:
        conditions.append(Activity.discipline_id == discipline_id)
    rows = (
        await session.execute(
            select(
                Activity.discipline_id,
                Discipline.name,
                func.count().label("sessions"),
                func.sum(Activity.duration_s).label("duration_s"),
                func.sum(Activity.distance_m).label("distance_m"),
                func.sum(Activity.training_load).label("training_load"),
            )
            .join(Discipline, Activity.discipline_id == Discipline.id)
            .where(*conditions)
            .group_by(Activity.discipline_id, Discipline.name)
            .order_by(Discipline.name)
        )
    ).all()
    by_discipline = [
        {
            "discipline_id": discipline_id_,
            "discipline": name,
            "sessions": count,
            "duration_s": int(duration or 0),
            "distance_km": round(float(distance or 0) / 1000, 1),
            "training_load": _num(load),
        }
        for discipline_id_, name, count, duration, distance, load in rows
    ]
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_sessions": sum(d["sessions"] for d in by_discipline),
        "total_duration_s": sum(d["duration_s"] for d in by_discipline),
        "total_training_load": round(
            sum(d["training_load"] or 0 for d in by_discipline), 1
        ),
        "by_discipline": by_discipline,
    }


async def discipline_id_by_slug(session: AsyncSession, slug: str) -> int | None:
    """Resolve a discipline slug like 'road_cycling' to its id (tools accept
    slugs from the model; the seed stores canonical names)."""
    row = await session.scalar(select(Discipline.id).where(Discipline.name == slug))
    return row
