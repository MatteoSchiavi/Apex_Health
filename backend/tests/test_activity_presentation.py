"""Sport views use actual recorded sets and full, owned activity windows."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.activities import _owned_activity
from app.models.activity import Activity, ActivityStream, Discipline
from app.models.gym_detail import GymDayExercise, GymDayPlan, GymExercise, GymSetLog
from app.models.user import User
from app.services.activity_presentation import (
    activity_presentation, gym_strength, imported_strength, recorded_zones,
    slope_count, sport_kind, strength_summary,
)


def test_partial_volume_does_not_invent_missing_weight_or_progression():
    previous = strength_summary(1, "Squat", "legs", [{"reps": 8, "weight_kg": 20}])
    previous["date"] = "2026-01-01"
    current = strength_summary(1, "Squat", "legs", [{"reps": 10, "weight_kg": 25}, {"reps": 9, "weight_kg": None}], previous)
    assert current["volume_kg"] == 250
    assert current["recorded_sets"] == [{"reps": 10, "weight_kg": 25}, {"reps": 9, "weight_kg": None}]
    assert current["weighted_sets"] == 1
    assert current["delta_reps"] == 11
    assert current["delta_volume_kg"] is None
    unknown = strength_summary(1, "Squat", "legs", [{"reps": 8, "weight_kg": None}])
    assert unknown["volume_kg"] is None


def test_imported_strength_rejects_plan_targets_and_unrecorded_groups():
    records = imported_strength({"garmin": {"exercises": [
        {"name": "Planned squat", "sets": [{"reps": 10, "weight_kg": 50}]},
        {"name": "Recorded press", "muscle_group": "push", "recorded_sets": [{"reps": 8, "weight_kg": 20}, {"reps": 7}]},
        {"name": "Unknown", "muscle_group": "invented", "sets": [{"completed": True, "reps": 8}]},
    ]}})
    assert [r["name"] for r in records] == ["Recorded press", "Unknown"]
    assert records[0]["volume_kg"] == 160
    assert records[0]["weighted_sets"] == 1
    assert records[0]["recorded_sets"] == [{"reps": 8, "weight_kg": 20}, {"reps": 7, "weight_kg": None}]
    assert records[1]["muscle_group"] is None
    assert records[1]["volume_kg"] is None
    assert imported_strength({"garmin": {"averageHR": 150}}) == []


def test_only_recorded_run_labels_and_reported_zones_are_used():
    assert slope_count(None, [SimpleNamespace(extras={}), SimpleNamespace(extras={"lap_type": "lift"})]) is None
    assert slope_count(None, [SimpleNamespace(extras={"is_run": True}), SimpleNamespace(extras={"lap_type": "lift"})]) == 1
    assert slope_count({"garmin": {"numberOfRuns": 7}}, []) == 7
    zones = recorded_zones({"garmin": {"hr_zones": [{"name": "Z1", "duration_s": 20}, {"duration_s": "nan"}],
                                          "power_zones": [{"name": "Z2", "duration_s": 50, "lower": 100, "upper": 150}]},
                            "strava": {"hr_zones": [{"name": "Duplicate", "duration_s": 99}]}})
    assert len(zones) == 2
    assert zones[0]["lower"] is None
    assert zones[1]["metric"] == "power"
    assert sport_kind("gym_general", {"garmin": {"type_key": "hiit"}}) == "hiit"
    assert sport_kind(None, {"garmin": {"type_key": "unknown"}}) == "other"


async def test_strength_uses_owned_time_windows_and_previous_same_exercise(db_session):
    session = db_session
    owner, friend = User(name="Sport owner"), User(name="Sport friend")
    session.add_all([owner, friend])
    await session.flush()
    discipline = await session.scalar(select(Discipline).where(Discipline.name == "strength"))
    start = datetime(2026, 8, 2, 10, tzinfo=timezone.utc)
    def activity(user, at):
        return Activity(user_id=user.id, discipline_id=discipline.id, start_time=at,
                        start_tz_offset_minutes=0, local_date=at.date(), duration_s=1800)
    previous = activity(owner, start - timedelta(hours=2))
    current = activity(owner, start)
    foreign = activity(friend, start)
    session.add_all([previous, current, foreign])
    squat = GymExercise(name="Sport squat " + uuid4().hex, muscle_group="legs", movement_pattern="squat")
    press = GymExercise(name="Sport press " + uuid4().hex, muscle_group="push", movement_pattern="press")
    own_plan = GymDayPlan(user_id=owner.id, date=start.date(), title="Own")
    foreign_plan = GymDayPlan(user_id=friend.id, date=start.date(), title="Friend")
    session.add_all([squat, press, own_plan, foreign_plan])
    await session.flush()
    def day_ex(plan, ex, position):
        return GymDayExercise(gym_day_plan_id=plan.id, exercise_id=ex.id, position=position, sets=3, reps_min=8)
    own_squat, own_press, foreign_squat = day_ex(own_plan, squat, 1), day_ex(own_plan, press, 2), day_ex(foreign_plan, squat, 1)
    session.add_all([own_squat, own_press, foreign_squat])
    await session.flush()
    def log(user, ex, at, reps, weight):
        return GymSetLog(user_id=user.id, gym_day_exercise_id=ex.id, set_number=1, done_at=at, reps_done=reps, weight_kg=weight)
    session.add_all([
        log(owner, own_squat, previous.start_time + timedelta(minutes=3), 8, 20),
        log(owner, own_squat, start + timedelta(minutes=3), 10, 25),
        log(owner, own_press, start + timedelta(minutes=5), 9, None),
        log(owner, own_squat, start + timedelta(hours=1), 99, 100), # same day plan, outside current
        log(friend, foreign_squat, start + timedelta(minutes=4), 99, 100),
        log(friend, own_squat, start + timedelta(minutes=4), 99, 100), # wrong log owner
        log(owner, foreign_squat, start + timedelta(minutes=4), 99, 100), # wrong plan owner
    ])
    await session.flush()
    result = await gym_strength(session, current)
    assert len(result) == 2
    assert result[0]["sets"] == 1 and result[0]["reps"] == 10
    assert result[0]["recorded_sets"] == [{"reps": 10, "weight_kg": 25}]
    assert result[0]["previous"]["reps"] == 8
    assert result[0]["delta_volume_kg"] == 90
    assert result[1]["volume_kg"] is None and result[1]["previous"] is None
    with pytest.raises(HTTPException) as denied:
        await _owned_activity(session, friend, current.id)
    assert denied.value.status_code == 404
    await session.rollback()


async def test_maximum_speed_uses_full_stream_and_falls_back_to_recorded_summary(db_session):
    session = db_session
    owner = User(name="Speed owner")
    session.add(owner)
    await session.flush()
    ski = await session.scalar(select(Discipline).where(Discipline.name == "skiing"))
    start = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)
    activity = Activity(user_id=owner.id, discipline_id=ski.id, start_time=start, start_tz_offset_minutes=0,
                        local_date=start.date(), duration_s=1300, source_metrics={"garmin": {"max_speed_m_s": 30}})
    session.add(activity)
    await session.flush()
    fallback = await activity_presentation(session, activity, "skiing", [])
    assert fallback["max_speed_m_s"] == 30
    # Put the peak at a point the 1200-point chart omits.
    picked = {i * 1300 // 1199 for i in range(1200)}
    peak = next(i for i in range(1301) if i not in picked)
    session.add_all([ActivityStream(activity_id=activity.id, t_offset_s=i, speed=55 if i == peak else 10)
                     for i in range(1301)])
    await session.flush()
    result = await activity_presentation(session, activity, "skiing", [])
    assert result["max_speed_m_s"] == 55
    assert result["slope_count"] is None
    await session.rollback()
