"""Gym session queries: the in-gym surface (API + Connect IQ window).

Answers "what is my next exercise, how many sets/reps, how long do I
rest?" from a confirmed/draft GymDayPlan plus the set log. Ownership is
enforced on every read/write (user_id scoping, §22 isolation law).
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog


class PlanNotFoundError(Exception):
    pass


class NotPlanOwnerError(Exception):
    pass


class SetLogConflictError(Exception):
    """The submitted set no longer matches the confirmed session state."""


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
        select(GymSetLog.gym_day_exercise_id, func.count(func.distinct(GymSetLog.set_number)))
        .join(GymDayExercise, GymDayExercise.id == GymSetLog.gym_day_exercise_id)
        .where(GymDayExercise.gym_day_plan_id == plan_id,
            GymSetLog.set_number >= 1, GymSetLog.set_number <= GymDayExercise.sets)
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
        "duration_min_s": day_row.duration_min_s,
        "duration_max_s": day_row.duration_max_s,
        "rest_seconds": day_row.rest_seconds,
        "notes": day_row.notes,
        "sets_done": done,
        "complete": done >= day_row.sets,
    }


async def plan_revision(session: AsyncSession, user_id: int, plan_id: int) -> int:
    """Audited advisor revision; legacy/manual plans start at one."""
    from app.models.lab import ChangeAudit
    audit = await session.scalar(select(ChangeAudit).where(ChangeAudit.user_id == user_id,
        ChangeAudit.action.in_(("gym_draft_generated", "gym_draft_refreshed")),
        ChangeAudit.payload["plan_id"].astext == str(plan_id)).order_by(ChangeAudit.id.desc()).limit(1))
    return int(audit.payload.get("revision", 1)) if audit else 1


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
        "revision": await plan_revision(session, user_id, plan.id),
        "date": plan.date.isoformat(),
        "title": plan.title,
        "source": plan.source,
        "status": plan.status,
        "adjustment_note": plan.adjustment_note,
        "exercises": exercises,
        "progress": {
            "sets_done": done_sets,
            "sets_total": total_sets,
            "complete": bool(exercises) and all(e["complete"] for e in exercises),
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
                "reps_target": (f"{exercise['reps_min']}"
                    + (f"-{exercise['reps_max']}" if exercise["reps_max"] else "")) if exercise["reps_min"] is not None else None,
                "duration_target_s": {"min": exercise["duration_min_s"], "max": exercise["duration_max_s"]} if exercise["duration_min_s"] is not None else None,
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
    reps_done: int | None,
    weight_kg: float | None,
    *,
    done_at: datetime | None = None,
    duration_s: int | None = None,
) -> dict:
    """Log one completed set. Returns the rest-timer value for the UI/watch."""
    plan = await get_owned_plan(session, user_id, plan_id)
    from app.services.evidence import scope_lock

    await scope_lock(session, user_id, "changes")
    await scope_lock(session, user_id, f"gym-plan:{plan.date}")
    # The plan may have changed while this transaction waited for the lock.
    await session.refresh(plan)
    day_row = await session.get(GymDayExercise, gym_day_exercise_id)
    if day_row is None or day_row.gym_day_plan_id != plan.id:
        raise PlanNotFoundError(gym_day_exercise_id)
    if day_row.duration_min_s is not None:
        if duration_s is None or reps_done is not None or not 1 <= duration_s <= 86400:
            raise SetLogConflictError("This exercise requires duration in seconds, not repetitions")
    elif reps_done is None or duration_s is not None or not 1 <= reps_done <= 500:
        raise SetLogConflictError("This exercise requires repetitions, not duration")
    if not 1 <= set_number <= day_row.sets:
        raise SetLogConflictError("Set number is outside the prescribed session")
    previous = (await session.scalars(select(GymSetLog).where(
        GymSetLog.gym_day_exercise_id == day_row.id,
        GymSetLog.set_number == set_number).order_by(GymSetLog.id))).all()
    if previous:
        # Mobile/watch retries must not inflate progress or overwrite evidence.
        weight = Decimal(str(weight_kg)) if weight_kg is not None else None
        if any(row.reps_done != reps_done or row.duration_s != duration_s or row.weight_kg != weight for row in previous):
            raise SetLogConflictError("This set was already saved with different values")
        return {"logged": True, "already_logged": True, "rest_seconds": None,
            "next": await next_up(session, user_id, plan_id)}
    if plan.status not in {"confirmed", "active"}:
        raise SetLogConflictError("Only a confirmed, unfinished session can record new sets")
    numbers = set((await session.scalars(select(GymSetLog.set_number).where(
        GymSetLog.gym_day_exercise_id == day_row.id))).all())
    next_number = next((n for n in range(1, day_row.sets + 1) if n not in numbers), None)
    if set_number != next_number:
        raise SetLogConflictError("Reload the workout and record the next unfinished set")
    session.add(
        GymSetLog(
            user_id=user_id,
            gym_day_exercise_id=gym_day_exercise_id,
            set_number=set_number,
            reps_done=reps_done,
            duration_s=duration_s,
            weight_kg=weight_kg,
            done_at=done_at or datetime.now(tz=ZoneInfo("UTC")),
        )
    )
    await session.flush()
    nxt = await next_up(session, user_id, plan_id)
    plan.status = "done" if nxt.get("done") else "active"
    plan.updated_at = datetime.now(tz=ZoneInfo("UTC"))
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
