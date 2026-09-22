"""Gym session queries: the in-gym surface (API + Connect IQ window).

Answers "what is my next exercise, how many sets/reps, how long do I
rest?" from a confirmed/draft GymDayPlan plus the set log. Ownership is
enforced on every read/write (user_id scoping, §22 isolation law).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog


class PlanNotFoundError(Exception):
    pass


class NotPlanOwnerError(Exception):
    pass


async def get_owned_plan(
    session: AsyncSession, user_id: int, plan_id: int
) -> GymDayPlan:
    plan = await session.get(GymDayPlan, plan_id)
    if plan is None:
        raise PlanNotFoundError(plan_id)
    if plan.user_id != user_id:
        raise NotPlanOwnerError(plan_id)
    return plan


async def plan_for_date(
    session: AsyncSession, user_id: int, day: date
) -> GymDayPlan | None:
    return await session.scalar(
        select(GymDayPlan).where(
            GymDayPlan.user_id == user_id, GymDayPlan.date == day
        )
    )


async def plan_rows(
    session: AsyncSession, plan_id: int
) -> list[tuple[GymDayExercise, GymExercise]]:
    return (
        (
            await session.execute(
                select(GymDayExercise, GymExercise)
                .join(GymExercise, GymExercise.id == GymDayExercise.exercise_id)
                .where(GymDayExercise.gym_day_plan_id == plan_id)
                .order_by(GymDayExercise.position)
            )
        )
        .all()
    )


async def done_counts(
    session: AsyncSession, plan_id: int
) -> dict[int, int]:
    """Logged set count per gym_day_exercise_id for one plan."""
    rows = await session.execute(
        select(GymSetLog.gym_day_exercise_id, func.count(GymSetLog.id))
        .join(GymDayExercise, GymDayExercise.id == GymSetLog.gym_day_exercise_id)
        .where(GymDayExercise.gym_day_plan_id == plan_id)
        .group_by(GymSetLog.gym_day_exercise_id)
    )
    return {gde_id: count for gde_id, count in rows.all()}


def _row_dict(day_row: GymDayExercise, ex: GymExercise, done: int) -> dict:
    return {
        "gym_day_exercise_id": day_row.id,
        "exercise_id": day_row.exercise_id,
        "name": ex.name,
        "muscle_group": ex.muscle_group,
        "movement_pattern": ex.movement_pattern,
        "impact_level": ex.impact_level,
        "position": day_row.position,
        "sets": day_row.sets,
        "reps_min": day_row.reps_min,
        "reps_max": day_row.reps_max,
        "rest_seconds": day_row.rest_seconds,
        "notes": day_row.notes,
        "sets_done": done,
        "complete": done >= day_row.sets,
    }


async def session_view(
    session: AsyncSession, user_id: int, plan_id: int
) -> dict:
    """Full plan view with per-exercise completion — the tracker page payload."""
    plan = await get_owned_plan(session, user_id, plan_id)
    rows = await plan_rows(session, plan.id)
    counts = await done_counts(session, plan.id)
    exercises = [
        _row_dict(day_row, ex, counts.get(day_row.id, 0))
        for day_row, ex in rows
    ]
    total_sets = sum(e["sets"] for e in exercises)
    done_sets = sum(e["sets_done"] for e in exercises)
    return {
        "plan_id": plan.id,
        "date": plan.date.isoformat(),
        "title": plan.title,
        "source": plan.source,
        "status": plan.status,
        "adjustment_note": plan.adjustment_note,
        "exercises": exercises,
        "progress": {
            "sets_done": done_sets,
            "sets_total": total_sets,
            "complete": total_sets > 0 and done_sets >= total_sets,
        },
    }


async def next_up(session: AsyncSession, user_id: int, plan_id: int) -> dict | None:
    """The next exercise (first incomplete by position) + rest timer hint."""
    view = await session_view(session, user_id, plan_id)
    for exercise in view["exercises"]:
        if not exercise["complete"]:
            sets_left = exercise["sets"] - exercise["sets_done"]
            return {
                "plan_id": plan_id,
                "exercise": exercise,
                "sets_left": sets_left,
                "reps_target": f"{exercise['reps_min']}"
                + (f"-{exercise['reps_max']}" if exercise["reps_max"] else ""),
                "rest_seconds": exercise["rest_seconds"],
            }
    return {
        "plan_id": plan_id,
        "exercise": None,
        "sets_left": 0,
        "reps_target": None,
        "rest_seconds": None,
        "done": True,
    }


async def log_set(
    session: AsyncSession,
    user_id: int,
    plan_id: int,
    gym_day_exercise_id: int,
    set_number: int,
    reps_done: int,
    weight_kg: float | None,
    *,
    done_at: datetime | None = None,
) -> dict:
    """Log one completed set. Returns the rest-timer value for the UI/watch."""
    plan = await get_owned_plan(session, user_id, plan_id)
    day_row = await session.get(GymDayExercise, gym_day_exercise_id)
    if day_row is None or day_row.gym_day_plan_id != plan.id:
        raise PlanNotFoundError(gym_day_exercise_id)
    session.add(
        GymSetLog(
            user_id=user_id,
            gym_day_exercise_id=gym_day_exercise_id,
            set_number=set_number,
            reps_done=reps_done,
            weight_kg=weight_kg,
            done_at=done_at or datetime.now(tz=ZoneInfo("UTC")),
        )
    )
    await session.flush()
    nxt = await next_up(session, user_id, plan_id)
    return {
        "logged": True,
        "rest_seconds": day_row.rest_seconds,
        "next": nxt,
    }


async def catalog(session: AsyncSession) -> list[dict]:
    rows = (await session.scalars(select(GymExercise).order_by(GymExercise.id))).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "muscle_group": e.muscle_group,
            "movement_pattern": e.movement_pattern,
            "impact_level": e.impact_level,
            "equipment": e.equipment,
        }
        for e in rows
    ]
