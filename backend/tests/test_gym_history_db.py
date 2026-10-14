"""Actual PostgreSQL gym history/revision contracts on disposable test fixtures."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models.activity import Activity, Discipline
from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog
from app.models.lab import ChangeAudit
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User
from app.services.gym_advisor import generate_day_plan, planning_inputs
from app.queries.gym_detail import plan_revision

DAY=date(2026,10,9)

async def user(session,name):
    row=User(name=name,timezone="UTC",locale="en")
    session.add(row); await session.flush()
    return row

async def logged_legs(session,athlete):
    ex=await session.scalar(select(GymExercise).where(GymExercise.muscle_group=="legs").order_by(GymExercise.id).limit(1))
    plan=GymDayPlan(user_id=athlete.id,date=DAY-timedelta(days=1),title="Recorded lower",source="manual",status="confirmed")
    session.add(plan); await session.flush()
    row=GymDayExercise(gym_day_plan_id=plan.id,exercise_id=ex.id,position=1,sets=6,reps_min=8,reps_max=8,rest_seconds=90)
    session.add(row); await session.flush()
    for n in range(1,7):
        session.add(GymSetLog(user_id=athlete.id,gym_day_exercise_id=row.id,set_number=n,reps_done=8,weight_kg=Decimal("40"),
            done_at=datetime.combine(DAY-timedelta(days=1),time(10,n),tzinfo=timezone.utc)))
    await session.flush()

async def test_actual_logs_refresh_stale_draft_with_owned_revision_snapshot(db_session):
    athlete=await user(db_session,"Gym history disposable athlete")
    plan,before,_=await generate_day_plan(db_session,athlete,DAY)
    assert any(r["muscle_group"]=="legs" for r in before)
    initial=await plan_revision(db_session,athlete.id,plan.id)
    await logged_legs(db_session,athlete)
    actual=await planning_inputs(db_session,athlete,DAY)
    observed=next(h for h in actual["history"] if h["source"]=="gym set logs")
    assert observed["groups"]["legs"]==6 and observed["volume_kg"]==1920
    refreshed,after,note=await generate_day_plan(db_session,athlete,DAY)
    assert refreshed.id==plan.id and all(r["muscle_group"]!="legs" for r in after)
    assert "2026-10-08" in note and await plan_revision(db_session,athlete.id,plan.id)==initial+1
    audit=await db_session.scalar(select(ChangeAudit).where(ChangeAudit.user_id==athlete.id,ChangeAudit.action=="gym_draft_refreshed"))
    assert audit.payload["before"]["exercises"] and audit.payload["after"]["exercises"]
    await db_session.rollback()

async def test_canonical_upper_and_upcoming_intervals_are_read_from_actual_plans(db_session):
    athlete=await user(db_session,"Gym canonical disposable athlete")
    strength=await db_session.scalar(select(Discipline).where(Discipline.name.in_(("strength","gym_general"))).limit(1))
    running=await db_session.scalar(select(Discipline).where(Discipline.name=="running"))
    push=await db_session.scalar(select(GymExercise).where(GymExercise.muscle_group=="push").order_by(GymExercise.id).limit(1))
    plan=TrainingPlan(user_id=athlete.id,created_by="manual",week_start=DAY,status="active",protected=True,revision=4)
    db_session.add(plan); await db_session.flush()
    upper=PlannedSession(training_plan_id=plan.id,date=DAY,discipline_id=strength.id,session_type="Upper body",description=push.name,protected=True)
    interval=PlannedSession(training_plan_id=plan.id,date=DAY+timedelta(days=1),discipline_id=running.id,session_type="intervals",description="6 repeats")
    db_session.add_all([upper,interval]); await db_session.flush()
    from app.services.structured_workouts import approved_plan_steps
    from app.schemas.workouts import WorkoutStep
    await approved_plan_steps(db_session,athlete.id,upper,[WorkoutStep(id="bench",kind="strength",exercise=push.name,sets=5,reps=6,load_kg=70)])
    await db_session.flush()
    inputs=await planning_inputs(db_session,athlete,DAY)
    assert inputs["intended"][0]["protected"] is True and inputs["intended"][0]["workout_revision"]==1
    assert inputs["upcoming"][0]["hard"] is True
    await logged_legs(db_session,athlete)
    generated,rows,_=await generate_day_plan(db_session,athlete,DAY)
    assert generated.title=="Upper body" and [r["exercise_id"] for r in rows]==[push.id]
    assert rows[0]["sets"]==5 and rows[0]["reps_min"]==6
    assert plan.revision==4 and plan.protected is True and upper.protected is True
    await db_session.rollback()

async def test_missing_exercise_details_do_not_infer_leg_work_and_other_users_are_excluded(db_session):
    athlete=await user(db_session,"Gym unknown disposable athlete")
    other=await user(db_session,"Gym other disposable athlete")
    await logged_legs(db_session,other)
    strength=await db_session.scalar(select(Discipline).where(Discipline.name.in_(("strength","gym_general"))).limit(1))
    db_session.add(Activity(user_id=athlete.id,discipline_id=strength.id,start_time=datetime.combine(DAY-timedelta(days=1),time(12),tzinfo=timezone.utc),
        local_date=DAY-timedelta(days=1),start_tz_offset_minutes=0,duration_s=1800,
        source_metrics={"garmin":{"exercises":[{"name":"Back Squat","sets":[{"reps":10,"weight_kg":50}]}]}}))
    await db_session.flush()
    inputs=await planning_inputs(db_session,athlete,DAY)
    assert len(inputs["history"])==1 and inputs["history"][0]["unknown_strength"] is True
    assert inputs["history"][0]["groups"]=={}
    _,_,note=await generate_day_plan(db_session,athlete,DAY)
    assert "without exercise details" in note and "Lower-body work recorded" not in note
    await db_session.rollback()

async def test_confirmation_requires_reviewed_revision_and_preserves_legacy_manual(db_session,monkeypatch):
    from app.api.coach import GymConfirmationIn,post_confirm_gym_plan
    async def flush_only():
        await db_session.flush()
    monkeypatch.setattr(db_session,"commit",flush_only)
    athlete=await user(db_session,"Gym confirmation disposable athlete")
    plan,_,_=await generate_day_plan(db_session,athlete,DAY)
    with pytest.raises(HTTPException) as missing:
        await post_confirm_gym_plan(DAY,None,db_session,athlete)
    assert missing.value.status_code==409 and plan.status=="draft"
    original_updated_at = plan.updated_at
    original_note = plan.adjustment_note
    await logged_legs(db_session,athlete)
    # The displayed revision is still current, but its generation inputs
    # changed after sync. Confirmation must reject without refreshing it.
    with pytest.raises(HTTPException) as changed_inputs:
        await post_confirm_gym_plan(DAY,GymConfirmationIn(expected_revision=1),db_session,athlete)
    assert changed_inputs.value.status_code == 409 and "refresh" in changed_inputs.value.detail
    assert plan.status == "draft" and plan.updated_at == original_updated_at
    assert plan.adjustment_note == original_note and await plan_revision(db_session,athlete.id,plan.id) == 1
    await generate_day_plan(db_session,athlete,DAY)
    with pytest.raises(HTTPException) as stale:
        await post_confirm_gym_plan(DAY,GymConfirmationIn(expected_revision=1),db_session,athlete)
    assert stale.value.status_code==409 and plan.status=="draft"
    revision=await plan_revision(db_session,athlete.id,plan.id)
    result=await post_confirm_gym_plan(DAY,GymConfirmationIn(expected_revision=revision),db_session,athlete)
    assert result["status"]=="confirmed"
    manual=GymDayPlan(user_id=athlete.id,date=DAY+timedelta(days=2),title="Legacy manual",source="manual",status="draft")
    db_session.add(manual); await db_session.flush()
    assert (await post_confirm_gym_plan(manual.date,None,db_session,athlete))["status"]=="confirmed"
    await db_session.rollback()
