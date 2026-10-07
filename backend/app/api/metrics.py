"""Per-metric trend API — the backbone of "every metric gets its own page".

- GET /metrics          — the metric catalog (key, label, unit, source column)
- GET /metrics/{key}    — one metric's daily series over a range + summary stats

A metric maps to one canonical column (DailyFeature / DailyBiometric /
SleepSession) plus an optional companion series (e.g. rolling baseline).
Adding a metric = adding one catalog entry; the SPA page renders itself
from the catalog response, so new metrics never need new frontend routes.
"""

from datetime import UTC, date, datetime, timedelta
import math
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.features import DailyFeature
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.models.lab import Observation
from app.services.analytics import robust_baseline
from app.schemas.ui import MetricPoint, MetricTrendOut, MetricCalculationInputs

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _fl(value) -> float | None:
    return float(value) if value is not None else None


RANGE_METRICS = {"hrv_ms", "resting_hr", "spo2", "respiration"}
ABSOLUTE_METRICS = {"steps", "floors", "hydration", "weight", "body_fat", "sleep_deep", "sleep_rem", "sleep_light"}


# Catalog law: (key → model, column, unit, better_direction, label-en, label-it)
# better_direction: 'up' | 'down' | 'band' — the UI colors deltas accordingly.
CATALOG: dict[str, dict] = {
    "readiness": {"model": "feature", "column": "readiness_score", "unit": "/100", "direction": "up"},
    "recovery": {"model": "feature", "column": "recovery_score", "unit": "/100", "direction": "up"},
    "strain": {"model": "feature", "column": "strain_score", "unit": "/100", "direction": "band"},
    "sleep_score": {"model": "feature", "column": "sleep_architecture_score", "unit": "/100", "direction": "up"},
    "acwr": {"model": "feature", "column": "acwr", "unit": "ratio", "direction": "band"},
    "acute_load": {"model": "feature", "column": "training_load_acute", "unit": "load/week", "direction": "band"},
    "chronic_load": {"model": "feature", "column": "training_load_chronic", "unit": "load/week", "direction": "band"},
    "hrv_deviation": {"model": "feature", "column": "hrv_deviation_from_baseline", "unit": "%", "direction": "band"},
    "hrv_ms": {"model": "hrv", "unit": "ms", "direction": "band"},
    "provider_sleep_score": {"model": "sleep", "column": "sleep_score", "unit": "/100", "direction": "band"},
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
            "kind": "estimate" if spec["model"] == "feature" else "measurement",
            "display_type": "range" if key in RANGE_METRICS else "absolute" if key in ABSOLUTE_METRICS else "trend",
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

    end_d = end or datetime.now(UTC).astimezone(ZoneInfo(user.timezone)).date()
    start_d = end_d - timedelta(days=days - 1)
    history_start = min(start_d, end_d - timedelta(days=30))
    reference_range = None
    acwr_snapshots = {}

    if spec["model"] == "hrv":
        rows, reference_range = await _hrv_series(session, user, history_start, end_d)
    elif key == "acwr":
        snapshots = (await session.execute(
            select(DailyFeature.date, DailyFeature.acwr,
                   DailyFeature.training_load_acute, DailyFeature.training_load_chronic,
                   DailyFeature.load_metadata)
            .where(DailyFeature.user_id == user.id, DailyFeature.date >= history_start,
                   DailyFeature.date <= end_d)
            .order_by(DailyFeature.date)
        )).all()
        # Keep the constituent snapshot from the same SELECT as each point;
        # a concurrent recompute cannot mix rows from two calculation versions.
        rows = [(row[0], row[1]) for row in snapshots]
        acwr_snapshots = {row[0]: row for row in snapshots}
    elif spec["model"] == "feature":
        rows = (
            await session.execute(
                select(DailyFeature.date, getattr(DailyFeature, spec["column"]))
                .where(
                    DailyFeature.user_id == user.id,
                    DailyFeature.date >= history_start,
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
                    DailyBiometric.date >= history_start,
                    DailyBiometric.date <= end_d,
                )
                .order_by(DailyBiometric.date)
            )
        ).all()
    else:  # Pick one complete night, rather than the maximum of each field.
        rows = (
            await session.execute(
                select(
                    SleepSession.local_date,
                    getattr(SleepSession, spec["column"]),
                )
                .where(
                    SleepSession.user_id == user.id,
                    SleepSession.local_date >= history_start,
                    SleepSession.local_date <= end_d,
                )
                .distinct(SleepSession.local_date)
                .order_by(
                    SleepSession.local_date,
                    SleepSession.total_sleep_s.desc().nulls_last(),
                    SleepSession.end_time.desc(),
                )
            )
        ).all()

    if key in RANGE_METRICS and key != "hrv_ms":
        comparable, reference_range = await _personal_series(session, user, history_start, end_d, key)
        if comparable:
            rows = comparable

    scale = spec.get("scale", 1.0)
    points = [
        MetricPoint(date=d.isoformat(), value=_fl(v) / scale if v is not None else None)
        for d, v in rows
    ]
    points = [p for p in points if p.value is None or math.isfinite(p.value)]
    history_points = points
    points = [p for p in points if p.date >= start_d.isoformat()]
    values = [p.value for p in points if p.value is not None]
    latest_day = date.fromisoformat(next((p.date for p in reversed(points) if p.value is not None), end_d.isoformat()))
    previous_30 = [p.value for p in history_points if p.value is not None and latest_day - timedelta(days=30) <= date.fromisoformat(p.date) < latest_day]
    stats = {}
    if values:
        stats = {
            "count": len(values),
            "mean": round(sum(values) / len(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "latest": values[-1],
            "delta_30d": (
                round(values[-1] - sum(previous_30) / len(previous_30), 2)
                if len(previous_30) >= 7
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
        reference_range=reference_range,
        calculation_inputs=(
            _acwr_calculation_inputs(acwr_snapshots.get(latest_day))
            if key == "acwr" and values else None
        ),
    )


def _acwr_calculation_inputs(snapshot):
    """Expose persisted constituents only; never reconstruct a missing snapshot."""
    if snapshot is None:
        return None
    day, ratio, acute, chronic, metadata = snapshot
    if any(value is None for value in (ratio, acute, chronic)):
        return None
    try:
        ratio, acute, chronic = float(ratio), float(acute), float(chronic)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in (ratio, acute, chronic)):
        return None
    if ratio < 0 or acute < 0 or chronic <= 0 or not isinstance(metadata, dict):
        return None
    method, unit = metadata.get("method"), metadata.get("unit")
    if not isinstance(method, str) or not method.strip() or not isinstance(unit, str) or not unit.strip():
        return None
    return MetricCalculationInputs(
        metric="acwr", as_of=day.isoformat(), methodology=method,
        contributors=[
            {"metric": "acute_load", "value": acute, "unit": unit + "/week"},
            {"metric": "chronic_load", "value": chronic, "unit": unit + "/week"},
        ],
    )


async def _personal_series(session, user, start, end, metric):
    """Use comparable measurements, keeping sources/devices separate.

    The displayed range is the preceding 28 days' empirical P10–P90 band,
    requiring 14 recorded days. It is not a clinical reference range and
    never includes the measurement being assessed.
    """
    records = (
        await session.scalars(
            select(Observation).where(
                Observation.user_id == user.id,
                Observation.metric == metric,
                Observation.current.is_(True),
                Observation.availability == "available",
                Observation.local_date.between(start - timedelta(days=28), end),
            ).order_by(Observation.measured_at, Observation.id)
        )
    ).all()
    records = [r for r in records if isinstance(r.value.get("value"), (int, float))
               and not isinstance(r.value["value"], bool)
               and math.isfinite(r.value["value"]) and r.value["value"] > 0]
    displayed = [r for r in records if r.local_date >= start]
    if displayed:
        # Prefer the configured main provider when it has readings in this window.
        from app.models.integration import Integration
        main = await session.scalar(select(Integration).where(
            Integration.id == user.main_integration_id, Integration.user_id == user.id
        )) if user.main_integration_id else None
        primary = [r for r in displayed if main and r.origin == main.provider]
        latest = (primary or displayed)[-1]
        context = lambda r: (r.origin, r.metadata_json.get("reading_context"), r.metadata_json.get("device_id"))
        comparable = [r for r in records if context(r) == context(latest)]
        # The last revision/measurement within a day is the daily sample.
        daily = {r.local_date: r for r in comparable}
        history = [r.value["value"] for day, r in daily.items()
                   if latest.local_date - timedelta(days=28) <= day < latest.local_date]
        # Explicit device changes warm up the band again even if IDs are absent.
        from app.models.lab import AthleteEntry
        change = await session.scalar(select(AthleteEntry.date).where(
            AthleteEntry.user_id == user.id, AthleteEntry.kind == "device_change",
            AthleteEntry.date <= latest.local_date,
            AthleteEntry.payload["metrics"].contains([metric]),
        ).order_by(AthleteEntry.date.desc()).limit(1))
        if change:
            history = [r.value["value"] for day, r in daily.items()
                       if max(change, latest.local_date - timedelta(days=28)) <= day < latest.local_date]
        band = robust_baseline(history)
        band.update({"origin": latest.origin, "as_of": str(latest.local_date),
                     "device_id": latest.metadata_json.get("device_id"),
                     "interpretation": "Personal empirical distribution; not a clinical reference range."})
        return sorted((day, r.value["value"]) for day, r in daily.items() if start <= day <= end), band

    return [], None


async def _hrv_series(session, user, start, end):
    points, band = await _personal_series(session, user, start, end, "hrv_overnight_rmssd")
    if points:
        return points, band

    # Older imports may predate the evidence index. Show their measurements
    # without inventing a comparable source/device band.
    tz = ZoneInfo(user.timezone)
    readings = (await session.scalars(select(HrvReading).where(
        HrvReading.user_id == user.id,
        HrvReading.timestamp >= datetime.combine(start, datetime.min.time(), tzinfo=tz),
        HrvReading.timestamp < datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz),
    ).order_by(HrvReading.timestamp))).all()
    groups = {}
    for row in readings:
        groups.setdefault(row.timestamp.astimezone(tz).date(), []).append(row)
    points = []
    for day, group in sorted(groups.items()):
        summaries = [r for r in group if r.reading_type == "overnight_avg"]
        value = float(summaries[-1].hrv_ms) if summaries else sum(float(r.hrv_ms) for r in group) / len(group)
        points.append((day, round(value, 2)))
    return points, None
