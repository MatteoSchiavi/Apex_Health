"""Shared Lab/goal calculations from canonical recorded gym sets."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.gym_detail import GymSetLog, GymDayExercise, GymExercise, GymDayPlan
from app.services.endurance_metrics import positive

VERSION = "epley-recorded-sets-v1"
SET_LIMIT = 5000


async def recorded_sets(session, user, start, end):
    tz = ZoneInfo(user.timezone)
    rows = (await session.execute(select(GymSetLog, GymExercise)
        .join(GymDayExercise, GymSetLog.gym_day_exercise_id == GymDayExercise.id)
        .join(GymDayPlan, GymDayExercise.gym_day_plan_id == GymDayPlan.id)
        .join(GymExercise, GymDayExercise.exercise_id == GymExercise.id)
        .where(GymSetLog.user_id == user.id, GymDayPlan.user_id == user.id,
            GymSetLog.done_at >= datetime.combine(start, datetime.min.time(), tzinfo=tz),
            GymSetLog.done_at < datetime.combine(end+timedelta(days=1), datetime.min.time(), tzinfo=tz))
        .order_by(GymSetLog.done_at, GymSetLog.id).limit(SET_LIMIT+1))).all()
    return rows[:SET_LIMIT], len(rows) <= SET_LIMIT


def gym_progression(rows, timezone, *, complete=True):
    """Epley and volume use the Lab's existing 1–10 rep convention."""
    tz, groups = ZoneInfo(timezone), {}
    for log, exercise in rows:
        key = (exercise.id, str(log.done_at.astimezone(tz).date()))
        bucket = groups.setdefault(key, {"exercise":exercise.name, "exercise_id":exercise.id,
            "equipment":getattr(exercise,"equipment",None), "date":key[1], "sets":0,
            "reps":None, "duration_s":None, "volume_kg":None, "observed_weight_sets":0, "e1rm_kg":None, "source_dependencies":[]})
        bucket["sets"] += 1
        if log.reps_done is not None:
            bucket["reps"] = (bucket["reps"] or 0) + log.reps_done
        if getattr(log, "duration_s", None) is not None:
            bucket["duration_s"] = (bucket["duration_s"] or 0) + log.duration_s
        bucket["source_dependencies"].append(f"gym_set_log:{log.id}")
        weight = positive(log.weight_kg, zero=True)
        if weight is not None and log.reps_done is not None:
            bucket["observed_weight_sets"] += 1
            bucket["volume_kg"] = (bucket["volume_kg"] or 0)+weight*log.reps_done
            if 1 <= log.reps_done <= 10 and weight > 0:
                estimate = round(weight*(1+log.reps_done/30),1)
                bucket["e1rm_kg"] = max(bucket["e1rm_kg"] or 0, estimate)
    return {"sample_count":len(rows), "sessions":list(groups.values()), "history_complete":complete,
        "formula_version":VERSION, "formula":"Epley: recorded load × (1 + reps/30), only 1–10 reps",
        "limitations":["Estimated strength from recorded sets, not a tested maximum. Machine loads and different exercises are not comparable."]}
