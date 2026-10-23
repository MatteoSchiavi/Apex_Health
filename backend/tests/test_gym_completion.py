"""A real gym session progresses once per saved set and reaches Your Day."""
import asyncio
import os
from types import SimpleNamespace
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.coach import SetLogIn, post_log_set
from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog
from app.models.user import User
from app.queries.gym_detail import session_view
from app.services.athlete_day import your_day
from app.services.activity_presentation import strength_summary
from app.services.gym_advisor import _catalog_rows
from app.services.gym_progression import gym_progression

DAY = date(2026, 10, 17)


async def session_fixture(db, *, status="confirmed"):
    athlete = User(name="Disposable gym workflow athlete", timezone="UTC", locale="en")
    db.add(athlete)
    await db.flush()
    plan = GymDayPlan(user_id=athlete.id, date=DAY, title="Strength session", status=status)
    db.add(plan)
    await db.flush()
    catalog = await db.scalar(select(GymExercise).order_by(GymExercise.id).limit(1))
    exercise = GymDayExercise(gym_day_plan_id=plan.id, exercise_id=catalog.id,
        position=0, sets=2, reps_min=8, reps_max=10, rest_seconds=60)
    db.add(exercise)
    await db.commit()
    return athlete, plan, exercise


def payload(exercise, number=1, reps=8):
    return SetLogIn(gym_day_exercise_id=exercise.id, set_number=number, reps_done=reps, weight_kg=40)


async def save(db, athlete, plan, exercise, number=1, reps=8):
    return await post_log_set(plan.id, payload(exercise, number, reps), session=db, user=athlete)


async def test_saved_sets_complete_workout_and_daily_state_without_counting_retries(db_session):
    athlete, plan, exercise = await session_fixture(db_session)
    first = await save(db_session, athlete, plan, exercise)
    assert first["rest_seconds"] == 60 and first["next"]["sets_left"] == 1
    assert plan.status == "active"
    assert (await your_day(db_session, athlete, DAY))["legacy_gym_sessions"][0]["status"] == "active"
    retry = await save(db_session, athlete, plan, exercise)
    assert retry["already_logged"] and retry["rest_seconds"] is None
    assert (await session_view(db_session, athlete.id, plan.id))["progress"]["sets_done"] == 1
    with pytest.raises(HTTPException) as conflict:
        await save(db_session, athlete, plan, exercise, reps=10)
    assert conflict.value.status_code == 409
    final = await save(db_session, athlete, plan, exercise, 2)
    assert final["next"]["done"] and plan.status == "done"
    view = await session_view(db_session, athlete.id, plan.id)
    assert view["progress"] == {"sets_done": 2, "sets_total": 2, "complete": True}
    daily = await your_day(db_session, athlete, DAY)
    assert daily["legacy_gym_sessions"] == [{"gym_day_plan_id": plan.id, "title": plan.title, "status": "completed"}]
    assert (await save(db_session, athlete, plan, exercise, 2))["already_logged"]
    assert await db_session.scalar(select(func.count()).select_from(GymSetLog).where(GymSetLog.gym_day_exercise_id == exercise.id)) == 2


async def test_drafts_gaps_extra_sets_and_foreign_rows_cannot_fabricate_completion(db_session):
    athlete, plan, exercise = await session_fixture(db_session, status="draft")
    with pytest.raises(HTTPException) as draft:
        await save(db_session, athlete, plan, exercise)
    assert draft.value.status_code == 409
    plan.status = "confirmed"
    await db_session.commit()
    for number in (2, 3):
        with pytest.raises(HTTPException) as invalid:
            await save(db_session, athlete, plan, exercise, number)
        assert invalid.value.status_code == 409
    friend, foreign_plan, foreign_exercise = await session_fixture(db_session)
    with pytest.raises(HTTPException) as foreign:
        await save(db_session, athlete, plan, foreign_exercise)
    assert foreign.value.status_code == 404
    with pytest.raises(HTTPException) as owner:
        await save(db_session, friend, plan, exercise)
    assert owner.value.status_code == 404
    assert (await session_view(db_session, athlete.id, plan.id))["progress"]["sets_done"] == 0


async def test_legacy_duplicate_numbers_do_not_complete_a_workout_but_valid_old_logs_do(db_session):
    athlete, plan, exercise = await session_fixture(db_session)
    for number in (1, 1, 30):
        db_session.add(GymSetLog(user_id=athlete.id, gym_day_exercise_id=exercise.id,
            set_number=number, reps_done=8, weight_kg=40))
    await db_session.commit()
    view = await session_view(db_session, athlete.id, plan.id)
    assert view["progress"] == {"sets_done": 1, "sets_total": 2, "complete": False}
    assert (await your_day(db_session, athlete, DAY))["legacy_gym_sessions"][0]["status"] == "active"
    db_session.add(GymSetLog(user_id=athlete.id, gym_day_exercise_id=exercise.id,
        set_number=2, reps_done=8, weight_kg=40))
    await db_session.commit()
    assert plan.status == "confirmed"
    assert (await your_day(db_session, athlete, DAY))["legacy_gym_sessions"][0]["status"] == "completed"


async def test_concurrent_mobile_retry_records_a_set_only_once(db_session):
    athlete, plan, exercise = await session_fixture(db_session)
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def request():
        async with factory() as db:
            return await save(db, athlete, plan, exercise)
    try:
        results = await asyncio.gather(request(), request())
        assert sum(bool(result.get("already_logged")) for result in results) == 1
        assert await db_session.scalar(select(func.count()).select_from(GymSetLog).where(GymSetLog.gym_day_exercise_id == exercise.id)) == 1
    finally:
        await engine.dispose()


async def test_timed_holds_persist_as_seconds_complete_and_never_count_as_reps_or_volume(db_session):
    athlete, plan, exercise = await session_fixture(db_session)
    exercise.reps_min = exercise.reps_max = None
    exercise.duration_min_s, exercise.duration_max_s = 30, 60
    await db_session.commit()
    with pytest.raises(HTTPException) as wrong_unit:
        await save(db_session, athlete, plan, exercise)
    assert wrong_unit.value.status_code == 409
    for number, seconds in ((1, 35), (2, 45)):
        body = SetLogIn(gym_day_exercise_id=exercise.id, set_number=number, duration_s=seconds, weight_kg=5)
        await post_log_set(plan.id, body, session=db_session, user=athlete)
        retry = await post_log_set(plan.id, body, session=db_session, user=athlete)
        assert retry["already_logged"]
    logs = list((await db_session.scalars(select(GymSetLog).where(
        GymSetLog.gym_day_exercise_id == exercise.id).order_by(GymSetLog.set_number))).all())
    assert [row.duration_s for row in logs] == [35, 45]
    assert all(row.reps_done is None for row in logs)
    assert (await session_view(db_session, athlete.id, plan.id))["progress"]["complete"]
    catalog = await db_session.get(GymExercise, exercise.exercise_id)
    result = gym_progression([(row, catalog) for row in logs], "UTC")["sessions"][0]
    assert result["duration_s"] == 80
    assert result["reps"] is result["volume_kg"] is result["e1rm_kg"] is None
    summary = strength_summary(catalog.id, catalog.name, catalog.muscle_group,
        [{"reps": row.reps_done, "duration_s": row.duration_s, "weight_kg": row.weight_kg} for row in logs])
    assert summary["duration_s"] == 80 and summary["reps"] is summary["volume_kg"] is None
    assert (await your_day(db_session, athlete, DAY))["legacy_gym_sessions"][0]["status"] == "completed"


def test_generated_core_holds_have_explicit_time_targets():
    plank = SimpleNamespace(id=1, name="Plank", muscle_group="core", movement_pattern="core_anti", impact_level="low")
    row = _catalog_rows([plank], ["core"], [], DAY, [1])[0]
    assert (row["duration_min_s"], row["duration_max_s"]) == (30, 60)
    assert row["reps_min"] is row["reps_max"] is None


@pytest.mark.parametrize("measurement", [{}, {"reps_done": 8, "duration_s": 30}, {"duration_s": 0}])
def test_log_requires_exactly_one_positive_measurement(measurement):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SetLogIn(gym_day_exercise_id=1, set_number=1, **measurement)


async def test_legacy_gap_returns_first_missing_set_and_completes_without_overwriting_saved_set(db_session):
    athlete, plan, exercise = await session_fixture(db_session)
    db_session.add(GymSetLog(user_id=athlete.id, gym_day_exercise_id=exercise.id,
        set_number=2, reps_done=10, weight_kg=45))
    await db_session.commit()
    view = await session_view(db_session, athlete.id, plan.id)
    row = view["exercises"][0]
    assert row["sets_done"] == 1
    assert row["next_set_number"] == 1
    result = await save(db_session, athlete, plan, exercise, row["next_set_number"])
    assert result["next"]["done"] and plan.status == "done"
    complete = await session_view(db_session, athlete.id, plan.id)
    assert complete["progress"]["complete"]
    assert complete["exercises"][0]["next_set_number"] is None
    logs = (await db_session.scalars(select(GymSetLog).where(
        GymSetLog.gym_day_exercise_id == exercise.id).order_by(GymSetLog.set_number))).all()
    assert [(row.set_number, row.reps_done, row.weight_kg) for row in logs] == [(1, 8, 40), (2, 10, 45)]
