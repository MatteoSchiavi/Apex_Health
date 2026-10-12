"""Read-only overview integration: canonical identities, ranges and ownership."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as Row
import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.models.activity import Activity, ActivitySourceLink, ActivityStream, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.lab import AthleteEntry, Observation
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User
from app.services.sport_progress import sport_overview
from tests.conftest import login
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401

DAY = date(2026,10,12)
AT = datetime(2026,10,12,10,tzinfo=UTC)


async def create_activity(session, *, uid=1, sport="running", at=AT, **fields):
    discipline = await session.scalar(select(Discipline.id).where(Discipline.name == sport))
    a = Activity(**{"user_id":uid,"discipline_id":discipline,"start_time":at,"local_date":at.date(),
        "start_tz_offset_minutes":0,"duration_s":3600,"distance_m":10000,"elevation_gain_m":None,**fields})
    session.add(a)
    await session.flush()
    return a


async def overview(session,sport="running",**kwargs):
    return await sport_overview(session,Row(id=1,timezone="UTC"),sport,DAY,DAY,now=AT+timedelta(hours=1),**kwargs)


async def authenticate(client):
    settings = get_settings()
    assert (await login(client,settings.owner_email,settings.owner_password)).status_code == 200


async def test_api_auth_dates_empty_missing_and_bounded(client):
    assert (await client.get("/athlete/sports/running/overview")).status_code == 401
    await authenticate(client)
    result = await client.get("/athlete/sports/running/overview?start=2026-10-12&end=2026-10-12")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "empty" and body["totals"]["distance_m"] is None
    assert body["recent_activities"] == [] and body["long_run_progression"] == []
    assert body["best_efforts"][0]["value"] is None
    assert (await client.get("/athlete/sports/swimming/overview")).status_code == 422
    assert (await client.get("/athlete/sports/running/overview?start=2026-10-13&end=2026-10-12")).status_code == 422
    assert (await client.get("/athlete/sports/running/overview?start=2023-01-01&end=2026-10-12")).status_code == 422


async def test_account_sport_and_range_isolation_canonical_sources_not_duplicates(db_session):
    other = User(name="Other sport athlete")
    db_session.add(other)
    await db_session.flush()
    current = await create_activity(db_session)
    await create_activity(db_session,uid=other.id,distance_m=999999)
    await create_activity(db_session,sport="road_cycling",distance_m=50000)
    await create_activity(db_session,at=AT-timedelta(days=1),distance_m=20000)
    for source in ("strava","garmin"):
        db_session.add(ActivitySourceLink(activity_id=current.id,user_id=1,source=source,external_id="progress-test"))
    await db_session.commit()
    body = await overview(db_session)
    assert body["totals"]["activity_count"] == 1 and body["totals"]["distance_m"] == 10000
    assert body["recent_activities"][0]["id"] == current.id
    long_run = body["long_run_progression"][0]["value"]
    assert long_run["reference_distance_m"] == 20000 and long_run["change_pct"] == -50
    cycling = await overview(db_session,"cycling")
    assert cycling["totals"]["distance_m"] == 50000


async def test_account_timezone_recomputed_not_stale_local_date(db_session):
    a = await create_activity(db_session,at=datetime(2026,10,13,0,30,tzinfo=UTC),local_date=date(2026,10,13))
    await db_session.commit()
    result = await sport_overview(db_session,Row(id=1,timezone="America/Los_Angeles"),"running",DAY,DAY,now=AT+timedelta(days=1))
    assert result["totals"]["activity_count"] == 1 and result["recent_activities"][0]["id"] == a.id
    assert result["recent_activities"][0]["date"] == "2026-10-12"


async def test_confirmed_adherence_explicit_association_checkin_and_draft_exclusion(db_session):
    a = await create_activity(db_session)
    discipline = a.discipline_id
    plan = TrainingPlan(user_id=1,status="active",created_by="manual",week_start=DAY,activated_on=DAY)
    draft = TrainingPlan(user_id=1,status="draft",created_by="manual",week_start=DAY)
    db_session.add_all([plan,draft])
    await db_session.flush()
    sessions = [PlannedSession(training_plan_id=p.id,date=DAY,discipline_id=discipline,target_duration_min=30) for p in (plan,plan,draft)]
    db_session.add_all(sessions)
    await db_session.flush()
    db_session.add_all([ActivityPlanLink(activity_id=a.id,user_id=1,planned_session_id=sessions[0].id,method="user_confirmed"),
        SessionCheckin(user_id=1,activity_id=a.id,planned_session_id=sessions[0].id,status="partial",rpe=4,revision=1,note="Easy run shortened")])
    await db_session.commit()
    result = await overview(db_session)
    assert result["adherence"]["value"]["planned_count"] == 2
    assert result["adherence"]["value"]["partial_count"] == 1
    assert result["adherence"]["value"]["completed_count"] == 0
    recent = result["recent_activities"][0]
    assert recent["planned_session_id"] == sessions[0].id and recent["checkin"]["note"] == "Easy run shortened"
    rpe = next(m for m in recent["metrics"] if m["key"] == "session_rpe_load")
    assert rpe["value"] == 240


async def test_cycling_hr_only_needs_no_power_and_manual_confirmed_ftp_stays_distinct(db_session):
    a = await create_activity(db_session,sport="road_cycling",avg_hr=125,duration_s=600,distance_m=4000)
    db_session.add(AthleteProfile(user_id=1,training_focus=["cycling"],context={"ftp":{"watts":250,"measured_on":"2026-10-01","confirmed":True}},revision=3))
    db_session.add_all([ActivityStream(activity_id=a.id,t_offset_s=i,hr=125,speed=6,power=None,cadence=80) for i in range(601)])
    await db_session.commit()
    result = await overview(db_session,"cycling")
    assert result["state"] == "ready" and result["totals"]["distance_m"] == 4000
    metrics = {m["key"]:m for m in result["recent_activities"][0]["metrics"]}
    assert metrics["normalized_power"]["value"] is None and metrics["cycling_speed_hr_efficiency"]["value"] == pytest.approx(6/125)
    assert metrics["hr_distribution"]["value"][0]["duration_s"] == 600
    assert all(point["value"] is None for point in result["power_duration"])
    assert result["ftp"]["value"]["mode"] == "manually_confirmed"
    assert result["body_mass"]["value"] is None


async def add_mass(session, ident=1, at=AT-timedelta(days=1), value=70, **fields):
    o = Observation(**{"id":ident,"user_id":1,"metric":"weight","value":{"value":value},"unit":"kg","origin":"garmin",
        "acquisition":"verified_import","source_record_id":str(ident),"measured_at":at,"local_date":at.date(),"timezone":"UTC",
        "fetched_at":at,"revision":1,"current":True,"availability":"available","quality_flags":[],"metadata_json":{},"content_hash":"mass-test",**fields})
    session.add(o)
    await session.flush()
    return o


async def test_power_duration_and_wkg_use_recent_owned_nonfuture_kg_mass(db_session):
    a = await create_activity(db_session,sport="road_cycling",duration_s=600,avg_power=210)
    db_session.add_all([ActivityStream(activity_id=a.id,t_offset_s=i,power=210,speed=6,hr=130) for i in range(601)])
    db_session.add(AthleteProfile(user_id=1,training_focus=["cycling"],context={"ftp":{"watts":280,"measured_on":"2026-10-01","confirmed":True}},revision=1))
    mass = await add_mass(db_session)
    await add_mass(db_session,2,AT+timedelta(hours=2),value=50)
    await db_session.commit()
    result = await overview(db_session,"cycling")
    assert result["body_mass"]["value"]["kg"] == 70
    assert result["body_mass"]["value"]["origin"] == "garmin"
    assert result["body_mass"]["value"]["user_asserted"] is False
    assert result["power_duration"][0]["quality"]["watts_per_kg"] == 3
    wkg = next(m for m in result["advanced_metrics"] if m["key"] == "confirmed_ftp_watts_per_kg")
    assert wkg["value"] == 4
    assert f"observation:{mass.id}:1" in wkg["source_dependencies"]
    db_session.add(AthleteEntry(user_id=1,kind="observation_annotation",date=DAY,payload={"observation_id":mass.id,"exclude_from_analysis":True,"notes":"Incorrect scale reading"},revision=1))
    await db_session.commit()
    excluded = await overview(db_session,"cycling")
    assert excluded["body_mass"]["value"] is None
    assert excluded["power_duration"][0]["quality"]["watts_per_kg"] is None
    db_session.add(AthleteEntry(user_id=1,kind="observation_annotation",date=DAY,payload={"observation_id":mass.id,"exclude_from_analysis":False,"notes":"Reviewed scale reading"},revision=1))
    await db_session.commit()
    restored = await overview(db_session,"cycling")
    assert restored["body_mass"]["value"]["kg"] == 70
    assert restored["power_duration"][0]["quality"]["watts_per_kg"] == 3


async def test_stream_budget_never_downsamples_or_claims_exact_power(db_session,monkeypatch):
    from app.services import sport_progress
    a = await create_activity(db_session,sport="road_cycling",duration_s=300)
    db_session.add_all([ActivityStream(activity_id=a.id,t_offset_s=i,power=200,speed=5,hr=125) for i in range(301)])
    await db_session.commit()
    monkeypatch.setattr(sport_progress,"STREAM_BUDGET",100)
    result = await overview(db_session,"cycling")
    assert result["state"] == "partial" and result["quality"]["stream_budget_exceeded"]
    assert result["totals"]["distance_m"] == 10000
    assert all(p["value"] is None for p in result["power_duration"])
    assert all(m["quality"]["stream_budget_excluded"] for m in result["recent_activities"][0]["metrics"])


async def test_activity_limit_never_uses_partial_long_run_reference(db_session,monkeypatch):
    from app.services import sport_progress
    await create_activity(db_session)
    await create_activity(db_session,at=AT-timedelta(days=1),distance_m=20000)
    await db_session.commit()
    monkeypatch.setattr(sport_progress,"ACTIVITY_LIMIT",1)
    result = await overview(db_session)
    assert result["state"] == "partial" and result["quality"]["activity_limit_reached"]
    assert result["long_run_progression"][0]["value"] is None
    assert result["long_run_progression"][0]["unavailable_reason"] == "incomplete_history"
    assert result["consistency"]["value"] is None


async def test_profile_focus_configuration_drives_saved_day_order_without_new_sessions(client,db_session):
    from datetime import time
    from app.services.athlete_day import your_day
    await authenticate(client)
    context = {"focus_mode":"balanced","supporting_focus":["cycling"],"weekly_time_budget_min":300,
        "weekly_allocation_min":{"running":180,"cycling":120}}
    response = await client.put("/athlete/profile",headers={"X-CSRF-Token":client.cookies.get("csrf_token")},json={"expected_revision":0,"training_focus":["running","cycling"],"context":context})
    assert response.status_code == 200,response.text
    plan = TrainingPlan(user_id=1,status="active",created_by="manual",week_start=DAY,activated_on=DAY)
    db_session.add(plan)
    await db_session.flush()
    running = await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    cycling = await db_session.scalar(select(Discipline.id).where(Discipline.name == "road_cycling"))
    db_session.add_all([PlannedSession(training_plan_id=plan.id,date=DAY,discipline_id=running,start_time=time(9)),
        PlannedSession(training_plan_id=plan.id,date=DAY,discipline_id=cycling,start_time=time(8))])
    await db_session.commit()
    day = await your_day(db_session,await db_session.get(User,1),DAY)
    assert day["focus_configuration"]["focus_mode"] == "balanced"
    assert [p["discipline"] for p in day["sessions"]] == ["road_cycling","running"]
    assert len(day["sessions"]) == 2
    context["focus_mode"] = "prioritized"
    changed = await client.put("/athlete/profile",headers={"X-CSRF-Token":client.cookies.get("csrf_token")},json={"expected_revision":response.json()["revision"],"training_focus":["running","cycling"],"context":context})
    assert changed.status_code == 200,changed.text
    db_session.expire_all()
    day = await your_day(db_session,await db_session.get(User,1),DAY)
    assert [p["discipline"] for p in day["sessions"]] == ["running","road_cycling"]
    assert len(day["sessions"]) == 2


async def test_accepted_ftp_changes_record_owned_history_retry_and_export_sources(client,db_session):
    await authenticate(client)
    base = {"training_focus":["cycling"],"context":{"ftp":{"watts":250,"measured_on":"2026-10-01","confirmed":True}},"expected_revision":0}
    response = await client.put("/athlete/profile",headers={"X-CSRF-Token":client.cookies.get("csrf_token")},json=base)
    assert response.status_code == 200,response.text
    base["expected_revision"] = response.json()["revision"]
    retry = await client.put("/athlete/profile",headers={"X-CSRF-Token":client.cookies.get("csrf_token")},json=base)
    assert retry.status_code == 200 and retry.json()["revision"] == base["expected_revision"]
    base["context"]["ftp"] = {"watts":260,"measured_on":"2026-10-12","confirmed":True}
    assert (await client.put("/athlete/profile",headers={"X-CSRF-Token":client.cookies.get("csrf_token")},json=base)).status_code == 200
    result = await sport_overview(db_session,Row(id=1,timezone="UTC"),"cycling",date(2026,10,1),DAY,now=AT)
    history = next(m for m in result["advanced_metrics"] if m["key"] == "ftp_trend")
    assert [point["watts"] for point in history["value"]] == [250,260]
    assert all(point["source"] == "user_confirmed" for point in history["value"])
    assert all(point["method"] == "explicit_dated_profile_assertion" for point in history["value"])
    entries = (await db_session.scalars(select(AthleteEntry).where(AthleteEntry.user_id == 1,AthleteEntry.kind == "ftp_assertion"))).all()
    assert len(entries) == 2
