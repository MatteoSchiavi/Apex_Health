"""Canonical records reach explicit goal and interval API results."""
from datetime import timedelta
from app.models.athlete import AthleteProfile
from app.models.activity import ActivityStream
from app.models.gym_detail import GymDayPlan, GymDayExercise, GymExercise, GymSetLog
from app.models.user import User
from app.services.sport_progress import sport_overview, strength_overview
from tests.conftest import csrf_headers
from tests.test_sport_progress import AT, DAY, Row, create_activity, authenticate
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def test_explicit_recorded_weekly_goal_api_not_baseline(db_session, client):
    a = await create_activity(db_session,at=AT-timedelta(days=1),distance_m=18000)
    db_session.add(AthleteProfile(user_id=1,training_focus=["running"],context={"focuses":{"running":{
        "weekly_distance_km":999,"measurable_goal":{"metric":"weekly_distance_km","target":20}}}},revision=2))
    await db_session.commit()
    body = await sport_overview(db_session,Row(id=1,timezone="UTC"),"running",DAY-timedelta(days=7),DAY,now=AT)
    goal = body["goal_context"]["goal_progress"]
    assert goal["value"]["measurement"] == 18 and goal["value"]["progress_pct"] == 90
    assert f"activity:{a.id}" in goal["source_dependencies"]
    await authenticate(client)
    result = await client.get("/athlete/sports/running/overview?start=2026-10-05&end=2026-10-12")
    assert result.status_code == 200
    assert result.json()["goal_context"]["goal_progress"]["value"]["target"] == 20


async def test_interval_candidates_are_visible_in_owned_activity_detail_api(db_session,client):
    a = await create_activity(db_session,duration_s=480)
    db_session.add_all([ActivityStream(activity_id=a.id,t_offset_s=i,speed=5 if 120 <= i < 180 or 240 <= i < 300 else 3)
        for i in range(481)])
    await db_session.commit()
    assert (await client.get(f"/activities/{a.id}/endurance")).status_code == 401
    await authenticate(client)
    result = await client.get(f"/activities/{a.id}/endurance")
    assert result.status_code == 200
    metric = next(m for m in result.json()["metrics"] if m["key"] == "automatic_intervals")
    assert metric["value"]["candidate_count"] == 2
    assert metric["source_dependencies"][0] == f"streams:{a.id}:speed"


async def test_strength_goal_reuses_owned_canonical_sets_and_api(db_session,client):
    other = User(name="Other strength owner")
    exercise = GymExercise(name="Goal integration squat",muscle_group="legs",movement_pattern="squat",equipment="barbell")
    db_session.add_all([other,exercise])
    await db_session.flush()
    plans = [GymDayPlan(user_id=uid,date=DAY,title="Recorded sets",source="manual",status="done") for uid in (1,other.id)]
    db_session.add_all(plans)
    await db_session.flush()
    exercises = [GymDayExercise(gym_day_plan_id=p.id,exercise_id=exercise.id,position=0,sets=1,reps_min=5) for p in plans]
    db_session.add_all(exercises)
    await db_session.flush()
    logs = [GymSetLog(user_id=uid,gym_day_exercise_id=e.id,set_number=1,reps_done=5,weight_kg=weight,done_at=AT-timedelta(hours=1))
        for uid,e,weight in ((1,exercises[0],60),(other.id,exercises[1],200))]
    db_session.add_all(logs)
    await db_session.commit()
    await authenticate(client)
    profile_response = await client.put("/athlete/profile",headers=csrf_headers(client),json={"expected_revision":0,"training_focus":["gym"],"context":{"focuses":{"gym":{
        "measurable_goal":{"metric":"exercise_estimated_1rm_kg","target":100,"exercise":exercise.name}}}}})
    assert profile_response.status_code == 200, profile_response.text
    body = await strength_overview(db_session,Row(id=1,timezone="UTC"),DAY,DAY,now=AT)
    assert body["goal_context"]["goal_progress"]["value"]["measurement"] == 70
    assert body["progression"]["sample_count"] == 1
    assert f"gym_set_log:{logs[1].id}" not in body["goal_context"]["goal_progress"]["source_dependencies"]
    await authenticate(client)
    response = await client.get("/athlete/sports/strength/overview?start=2026-10-12&end=2026-10-12")
    assert response.status_code == 200 and response.json()["progression"]["sample_count"] == 1


async def test_strength_weekly_duration_goal_uses_canonical_owned_activities(db_session,client):
    await create_activity(db_session,sport="strength",at=AT-timedelta(days=1),duration_s=3600)
    await create_activity(db_session,sport="running",at=AT-timedelta(days=1),duration_s=9000)
    await db_session.commit()
    await authenticate(client)
    profile_response = await client.put("/athlete/profile",headers=csrf_headers(client),json={"expected_revision":0,"training_focus":["gym"],"context":{"focuses":{"gym":{
        "measurable_goal":{"metric":"weekly_duration_min","target":120}}}}})
    assert profile_response.status_code == 200, profile_response.text
    body = await strength_overview(db_session,Row(id=1,timezone="UTC"),DAY-timedelta(days=7),DAY,now=AT)
    assert body["goal_context"]["goal_progress"]["value"]["measurement"] == 60
    assert body["goal_context"]["goal_progress"]["value"]["progress_pct"] == 50
