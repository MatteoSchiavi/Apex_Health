"""Per-metric trend API — the backbone of "every metric gets its own page".

- GET /metrics          — the metric catalog (key, label, unit, source column)
- GET /metrics/{key}    — one metric's daily series over a range + summary stats

A metric maps to one canonical column (DailyFeature / DailyBiometric /
SleepSession) plus an optional companion series (e.g. rolling baseline).
Adding a metric = adding one catalog entry; the SPA page renders itself
from the catalog response, so new metrics never need new frontend routes.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.features import DailyFeature
from app.models.user import User
from app.models.wellness import DailyBiometric, SleepSession
from app.schemas.ui import MetricPoint, MetricTrendOut

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _fl(value) -> float | None:
    return float(value) if value is not None else None


# Catalog law: (key → model, column, unit, better_direction, label-en, label-it)
# better_direction: 'up' | 'down' | 'band' — the UI colors deltas accordingly.
CATALOG: dict[str, dict] = {
    "readiness": {"model": "feature", "column": "readiness_score", "unit": "/100", "direction": "up"},
    "recovery": {"model": "feature", "column": "recovery_score", "unit": "/100", "direction": "up"},
    "strain": {"model": "feature", "column": "strain_score", "unit": "/100", "direction": "band"},
    "sleep_score": {"model": "feature", "column": "sleep_architecture_score", "unit": "/100", "direction": "up"},
    "acwr": {"model": "feature", "column": "acwr", "unit": "ratio", "direction": "band"},
    "acute_load": {"model": "feature", "column": "training_load_acute", "unit": "TSS/d", "direction": "band"},
    "chronic_load": {"model": "feature", "column": "training_load_chronic", "unit": "TSS/d", "direction": "up"},
    "hrv_deviation": {"model": "feature", "column": "hrv_deviation_from_baseline", "unit": "%", "direction": "up"},
    "illness_risk": {"model": "feature", "column": "illness_risk_score", "unit": "/100", "direction": "down"},
    "injury_risk": {"model": "feature", "column": "injury_risk_score", "unit": "/100", "direction": "down"},
    "resting_hr": {"model": "biometric", "column": "resting_hr", "unit": "bpm", "direction": "down"},
    "weight": {"model": "biometric", "column": "weight_kg", "unit": "kg", "direction": "band"},
    "body_fat": {"model": "biometric", "column": "body_fat_pct", "unit": "%", "direction": "band"},
    "vo2max": {"model": "biometric", "column": "vo2max", "unit": "ml/kg/min", "direction": "up"},
    "steps": {"model": "biometric", "column": "steps", "unit": "steps", "direction": "up"},
    "floors": {"model": "biometric", "column": "floors", "unit": "floors", "direction": "up"},
    "spo2": {"model": "biometric", "column": "spo2_avg", "unit": "%", "direction": "up"},
    "hydration": {"model": "biometric", "column": "hydration_ml", "unit": "ml", "direction": "up"},
    "sleep_duration": {"model": "sleep", "column": "total_sleep_s", "unit": "h", "scale": 3600.0, "direction": "band"},
    "sleep_deep": {"model": "sleep", "column": "deep_s", "unit": "h", "scale": 3600.0, "direction": "band"},
    "sleep_rem": {"model": "sleep", "column": "rem_s", "unit": "h", "scale": 3600.0, "direction": "band"},
    "sleep_light": {"model": "sleep", "column": "light_s", "unit": "h", "scale": 3600.0, "direction": "band"},
    "respiration": {"model": "sleep", "column": "respiration_avg", "unit": "br/min", "direction": "band"},
    "restlessness": {"model": "sleep", "column": "restlessness", "unit": "%", "direction": "down"},
}


@router.get("")
async def metric_catalog(
    user: User = Depends(get_current_user),
) -> dict:
    return {
        key: {
            "unit": spec["unit"],
            "direction": spec["direction"],
        }
        for key, spec in CATALOG.items()
    }


@router.get("/{key}", response_model=MetricTrendOut)
async def metric_trend(
    key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=90, ge=7, le=730),
    end: date | None = None,
) -> MetricTrendOut:
    spec = CATALOG.get(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown metric {key!r}")

    end_d = end or date.today()
    start_d = end_d - timedelta(days=days - 1)

    if spec["model"] == "feature":
        rows = (
            await session.execute(
                select(DailyFeature.date, getattr(DailyFeature, spec["column"]))
                .where(
                    DailyFeature.user_id == user.id,
                    DailyFeature.date >= start_d,
                    DailyFeature.date <= end_d,
                )
                .order_by(DailyFeature.date)
            )
        ).all()
    elif spec["model"] == "biometric":
        rows = (
            await session.execute(
                select(DailyBiometric.date, getattr(DailyBiometric, spec["column"]))
                .where(
                    DailyBiometric.user_id == user.id,
                    DailyBiometric.date >= start_d,
                    DailyBiometric.date <= end_d,
                )
                .order_by(DailyBiometric.date)
            )
        ).all()
    else:  # sleep — one row per local_date, longest night wins in SQL
        rows = (
            await session.execute(
                select(
                    SleepSession.local_date,
                    func.max(getattr(SleepSession, spec["column"])),
                )
                .where(
                    SleepSession.user_id == user.id,
                    SleepSession.local_date >= start_d,
                    SleepSession.local_date <= end_d,
                )
                .group_by(SleepSession.local_date)
                .order_by(SleepSession.local_date)
            )
        ).all()

    scale = spec.get("scale", 1.0)
    points = [
        MetricPoint(date=d.isoformat(), value=_fl(v) / scale if v is not None else None)
        for d, v in rows
    ]
    values = [p.value for p in points if p.value is not None]
    stats = {}
    if values:
        stats = {
            "count": len(values),
            "mean": round(sum(values) / len(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "latest": values[-1],
            "delta_30d": (
                round(values[-1] - sum(values[-30:]) / len(values[-30:]), 2)
                if len(values) >= 8
                else None
            ),
        }

    return MetricTrendOut(
        metric=key,
        label=key,
        unit=spec["unit"],
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        points=[p for p in points],
        stats=stats,
    )
