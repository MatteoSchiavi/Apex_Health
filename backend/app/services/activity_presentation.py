"""Sport-specific view data. All values retain canonical units and provenance.

Set logs are associated by actual activity windows, never by plan calendar date.
A partial weighted total is useful, but cannot produce a volume progression delta.
"""
from collections import defaultdict
from datetime import timedelta
from math import isfinite

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityLap, ActivityStream, Discipline
from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog

GROUPS = {"legs", "push", "pull", "core", "full_body"}
STRENGTH = {"strength", "gym_general"}


def sport_kind(discipline: str | None, metrics: dict | None = None) -> str:
    if discipline in {None, "gym_general", "hiit"} and any(
        isinstance(block, dict) and block.get("type_key") in ("hiit", "high_intensity_interval_training")
        for block in (metrics or {}).values()
    ):
        return "hiit"
    if discipline in STRENGTH:
        return "strength"
    if discipline == "running":
        return "running"
    if discipline in {"road_cycling", "mountain_biking", "gravel_cycling"}:
        return "cycling"
    if discipline == "sailing":
        return "sailing"
    if discipline in {"skiing", "snowboard"}:
        return "skiing"
    if discipline == "hiit":
        return "hiit"
    return "other"


def number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if isfinite(result) else None


def provider_number(metrics: dict | None, *keys: str) -> float | None:
    for block in (metrics or {}).values():
        if not isinstance(block, dict):
            continue
        for key in keys:
            value = number(block.get(key))
            if value is not None and value >= 0:
                return value
    return None


def recorded_zones(metrics: dict | None) -> list[dict]:
    """Only reported zone durations/bounds. No derived FTP or max-HR bands."""
    zones = []
    for metric in ("hr", "power"):
        for block in (metrics or {}).values():
            if not isinstance(block, dict):
                continue
            rows = block.get(metric + "_zones")
            if not isinstance(rows, list):
                continue
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                duration = number(row.get("duration_s"))
                if duration is None or duration < 0:
                    continue
                name = row.get("name")
                zones.append({"metric": metric, "name": str(name) if isinstance(name, (str, int)) else str(i + 1),
                              "duration_s": duration, "lower": number(row.get("lower")), "upper": number(row.get("upper"))})
            # Preserve one provider's zone partition, not duplicates from merges.
            if rows and any(z["metric"] == metric for z in zones):
                break
    return zones


def slope_count(metrics: dict | None, laps: list[ActivityLap]) -> int | None:
    explicit = provider_number(metrics, "slope_count", "number_of_runs", "numberOfRuns")
    if explicit is not None and explicit.is_integer():
        return int(explicit)
    marked = [lap for lap in laps if isinstance(lap.extras, dict) and (
        lap.extras.get("is_run") is True or lap.extras.get("lap_type") in ("run", "ski_run", "downhill_run")
    )]
    return len(marked) if marked else None


def strength_summary(exercise_id, name: str, group: str | None, sets: list[dict], previous: dict | None = None) -> dict:
    from app.services.exercise_catalog import identify

    identified = identify(name, group)
    name, group = identified["name"], identified["muscle_group"]
    known = [s for s in sets if s["weight_kg"] is not None]
    volume = sum(s["reps"] * s["weight_kg"] for s in known) if known else None
    result = {"exercise_id": exercise_id, "name": name, "muscle_group": group if isinstance(group, str) and group in GROUPS else None,
              "sets": len(sets), "reps": sum(s["reps"] for s in sets), "volume_kg": volume,
              "weighted_sets": len(known), "recorded_sets": [{"reps": s["reps"], "weight_kg": s["weight_kg"]} for s in sets],
              "previous": None, "delta_sets": None, "delta_reps": None, "delta_volume_kg": None}
    if previous is not None:
        result["previous"] = {k: previous[k] for k in ("date", "sets", "reps", "volume_kg", "weighted_sets")}
        result["delta_sets"] = result["sets"] - previous["sets"]
        result["delta_reps"] = result["reps"] - previous["reps"]
        if len(known) == len(sets) and previous["weighted_sets"] == previous["sets"]:
            result["delta_volume_kg"] = volume - previous["volume_kg"]
    return result


def imported_strength(metrics: dict | None) -> list[dict]:
    """Recorded provider sets only; plan targets and generic HR are not sets."""
    for block in (metrics or {}).values():
        if not isinstance(block, dict) or not isinstance(block.get("exercises"), list):
            continue
        exercises = []
        for exercise in block["exercises"]:
            if not isinstance(exercise, dict) or not isinstance(exercise.get("name"), str):
                continue
            records = exercise.get("recorded_sets")
            explicit = isinstance(records, list)
            if not explicit:
                records = exercise.get("sets")
            if not isinstance(records, list):
                continue
            sets = []
            for row in records:
                if not isinstance(row, dict) or (not explicit and row.get("completed") is not True and row.get("status") != "completed"):
                    continue
                if row.get("completed") is False or row.get("status") in ("planned", "rest", "skipped"):
                    continue
                reps = number(row.get("reps"))
                weight = number(row.get("weight_kg"))
                if reps is None or reps < 0 or not reps.is_integer():
                    continue
                sets.append({"reps": int(reps), "weight_kg": weight if weight is not None and weight >= 0 else None})
            if sets:
                exercises.append(strength_summary(None, exercise["name"], exercise.get("muscle_group"), sets))
        if exercises:
            return exercises
    return []


def _set(log: GymSetLog) -> dict:
    weight = number(log.weight_kg)
    return {"reps": log.reps_done, "weight_kg": weight if weight is not None and weight >= 0 else None}


async def gym_strength(session: AsyncSession, activity: Activity) -> list[dict]:
    if activity.duration_s <= 0:
        return []
    end = activity.start_time + timedelta(seconds=activity.duration_s)
    base = (select(GymSetLog, GymExercise)
            .join(GymDayExercise, GymDayExercise.id == GymSetLog.gym_day_exercise_id)
            .join(GymDayPlan, GymDayPlan.id == GymDayExercise.gym_day_plan_id)
            .join(GymExercise, GymExercise.id == GymDayExercise.exercise_id)
            .where(GymSetLog.user_id == activity.user_id, GymDayPlan.user_id == activity.user_id))
    current = (await session.execute(base.where(GymSetLog.done_at >= activity.start_time, GymSetLog.done_at < end)
                                       .order_by(GymDayExercise.position, GymSetLog.done_at))).all()
    if not current:
        return []
    grouped = defaultdict(list)
    catalog = {}
    for log, exercise in current:
        grouped[exercise.id].append(_set(log))
        catalog[exercise.id] = exercise
    # SQL joins real, owned prior activity windows; even repeated sessions on a
    # single day plan are distinct. No unbounded per-exercise N+1 queries.
    prior = (await session.execute(
        base.add_columns(Activity.id, Activity.start_time, Activity.local_date)
        .join(Activity, (Activity.user_id == GymSetLog.user_id)
              & (GymSetLog.done_at >= Activity.start_time)
              & (GymSetLog.done_at < Activity.start_time + func.make_interval(0, 0, 0, 0, 0, 0, Activity.duration_s)))
        .join(Discipline, Discipline.id == Activity.discipline_id)
        .where(Activity.start_time < activity.start_time, GymSetLog.done_at < activity.start_time,
               Discipline.name.in_(STRENGTH), GymExercise.id.in_(grouped))
        .order_by(Activity.start_time.desc(), Activity.id.desc(), GymSetLog.done_at)
    )).all()
    previous_sets = defaultdict(list)
    previous_activity = {}
    previous_dates = {}
    for log, exercise, activity_id, _, day in prior:
        previous_activity.setdefault(exercise.id, activity_id)
        if previous_activity[exercise.id] == activity_id:
            previous_sets[exercise.id].append(_set(log))
            previous_dates[exercise.id] = day.isoformat()
    out = []
    for exercise_id, sets in grouped.items():
        exercise = catalog[exercise_id]
        previous = None
        if exercise_id in previous_sets:
            previous = strength_summary(exercise_id, exercise.name, exercise.muscle_group, previous_sets[exercise_id])
            previous["date"] = previous_dates[exercise_id]
        out.append(strength_summary(exercise_id, exercise.name, exercise.muscle_group, sets, previous))
    return out


async def activity_presentation(session: AsyncSession, activity: Activity, discipline: str | None, laps: list[ActivityLap]) -> dict:
    kind = sport_kind(discipline, activity.source_metrics)
    # Aggregate the full stream in SQL: a downsampled chart misses peak speeds.
    speed_max, cadence_avg = (await session.execute(select(func.max(ActivityStream.speed), func.avg(ActivityStream.cadence))
                                                    .where(ActivityStream.activity_id == activity.id))).one()
    max_speed = number(speed_max)
    if max_speed is None:
        max_speed = provider_number(activity.source_metrics, "max_speed_m_s", "maxSpeed")
    average_speed = provider_number(activity.source_metrics, "avg_speed_m_s", "averageSpeed")
    if average_speed is None and activity.distance_m is not None and activity.duration_s > 0:
        average_speed = float(activity.distance_m) / activity.duration_s
    cadence = number(cadence_avg)
    if cadence is None:
        cadence = provider_number(activity.source_metrics, "avg_cadence", "averageBikeCadence", "averageCadence")
    strength = await gym_strength(session, activity) if kind == "strength" else []
    if kind == "strength" and not strength:
        strength = imported_strength(activity.source_metrics)
    return {"kind": kind, "avg_speed_m_s": average_speed, "max_speed_m_s": max_speed,
            "avg_cadence": cadence, "slope_count": slope_count(activity.source_metrics, laps) if kind == "skiing" else None,
            "zones": recorded_zones(activity.source_metrics), "strength": strength}
