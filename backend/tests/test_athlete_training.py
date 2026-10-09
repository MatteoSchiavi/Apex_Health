from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from app.core.config import get_settings
from app.models.activity import Activity, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import PlanDocumentDraft
from app.models.training import TrainingPlan, PlannedSession
from app.models.user import User
from app.schemas.changes import ProposeIn
from app.services.changes import propose, apply, undo
from app.services.evidence import EvidenceError
from app.services.athlete_day import your_day
from app.services.analytics import constraints
from tests.conftest import login, csrf_headers
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def isolate_profile(db_session):
    await db_session.execute(text("TRUNCATE athlete_profiles RESTART IDENTITY CASCADE"))
    await db_session.execute(text("UPDATE auth_credentials SET failed_login_count=0, locked_until=NULL WHERE user_id=1"))
    await db_session.commit()


async def authenticate(client):
    s = get_settings()
    assert (await login(client, s.owner_email, s.owner_password)).status_code == 200


async def reviewed_document(client):
    upload = await client.post("/lab/documents", headers=csrf_headers(client), files={"file": ("plan.md", b"A reviewed plan, dates and duration may be unclear.", "text/plain")})
    assert upload.status_code == 201
    doc = upload.json()
    review = await client.post(f"/lab/documents/{doc['id']}/confirm", headers=csrf_headers(client), json={"content_hash": doc["content_hash"], "reviewed_text": doc["excerpt"]})
    return review.json()


def structure(day, sports=("strength", "running"), protected=False, ambiguities=None):
    return {"title": "Mixed sport plan", "starts_on": str(day), "ends_on": str(day+timedelta(days=6)),
        "sessions": [{"date": str(day), "discipline": sport, "duration_min": 30,
            "session_type": "easy", "protected": protected} for sport in sports], "ambiguities": ambiguities or []}


async def test_document_review_draft_confirmation_retry_and_ambiguity(client, db_session):
    await authenticate(client)
    upload = await client.post("/lab/documents", headers=csrf_headers(client), files={"file": ("raw.txt", b"plan", "text/plain")})
    day = datetime.now(ZoneInfo("Europe/Rome")).date()
    invalid = await client.post(f"/lab/documents/{upload.json()['id']}/plan-drafts", headers=csrf_headers(client), json={"expected_document_revision": 1, "structure": structure(day)})
    assert invalid.status_code == 409
    doc = await reviewed_document(client)
    payload = {"expected_document_revision": doc["revision"], "structure": structure(day, ambiguities=["Intensity unspecified"])}
    response = await client.post(f"/lab/documents/{doc['id']}/plan-drafts", headers=csrf_headers(client), json=payload)
    assert response.status_code == 201, response.text
    draft = response.json()
    stored = await db_session.get(PlanDocumentDraft, draft["id"])
    assert b"Mixed sport plan" not in stored.structure_ciphertext
    assert not await db_session.scalar(select(TrainingPlan.id))
    retry = await client.post(f"/lab/documents/{doc['id']}/plan-drafts", headers=csrf_headers(client), json=payload)
    assert retry.json()["id"] == draft["id"]
    assert (await client.post(f"/lab/plan-drafts/{draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"]})).status_code == 422
    confirm = {"payload_hash": draft["payload_hash"], "ambiguities_reviewed": True}
    activation = await client.post(f"/lab/plan-drafts/{draft['id']}/confirm", headers=csrf_headers(client), json=confirm)
    assert activation.status_code == 200, activation.text
    duplicate = await client.post(f"/lab/plan-drafts/{draft['id']}/confirm", headers=csrf_headers(client), json=confirm)
    assert duplicate.json()["plan_id"] == activation.json()["plan_id"]
    day_response = (await client.get(f"/athlete/day?date={day}")).json()
    assert len(day_response["sessions"]) == 2
    assert {s["discipline"] for s in day_response["sessions"]} == {"strength", "running"}


async def test_missing_dates_unknown_duration_preserved_and_stale_extraction_rejected(client, db_session):
    await authenticate(client)
    doc = await reviewed_document(client)
    result = await client.post(f"/lab/documents/{doc['id']}/plan-drafts", headers=csrf_headers(client), json={"expected_document_revision": doc["revision"], "structure": {"sessions": [{"discipline": "running"}], "ambiguities": ["Dates unknown"]}})
    draft = result.json()
    assert draft["structure"]["starts_on"] is None and draft["structure"]["sessions"][0]["duration_min"] is None
    response = await client.post(f"/lab/plan-drafts/{draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"], "ambiguities_reviewed": True})
    assert response.status_code == 422
    day = datetime.now(ZoneInfo("Europe/Rome")).date()
    updated = await client.post(f"/lab/documents/{doc['id']}/plan-drafts", headers=csrf_headers(client), json={"expected_document_revision": doc["revision"], "structure": structure(day)})
    assert updated.json()["version"] == 2
    stale = await client.post(f"/lab/plan-drafts/{draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"], "ambiguities_reviewed": True})
    assert stale.status_code == 409


async def make_plan(db_session, day, sports=("running",), protected=False):
    plan = TrainingPlan(user_id=1, created_by="manual", week_start=day, status="confirmed", protected=protected)
    db_session.add(plan)
    await db_session.flush()
    items = []
    for sport in sports:
        discipline = await db_session.scalar(select(Discipline.id).where(Discipline.name == sport))
        item = PlannedSession(training_plan_id=plan.id, date=day, discipline_id=discipline, session_type="easy", target_duration_min=30)
        db_session.add(item)
        items.append(item)
    await db_session.commit()
    return plan, items


@pytest.mark.parametrize("sports", [("strength", "running"), ("running", "road_cycling"), ("running", "running"), ("sailing", "skiing", "enduro")])
async def test_multiple_sessions_other_sports_and_recorded_links(client, db_session, sports):
    await authenticate(client)
    day = datetime(2026, 10, 9).date()
    _, items = await make_plan(db_session, day, sports)
    discipline = await db_session.scalar(select(Discipline.id).where(Discipline.name == sports[0]))
    activity = Activity(user_id=1, discipline_id=discipline, start_time=datetime(2026, 10, 9, 8, tzinfo=UTC), local_date=day,
        start_tz_offset_minutes=120, duration_s=1800, training_load=999, source_metrics={"whoop": {"strain": 12}})
    db_session.add(activity)
    await db_session.commit()
    first = (await client.get(f"/athlete/day?date={day}")).json()
    assert len(first["sessions"]) == len(sports)
    assert first["activities"][0]["association"] == "needs_confirmation"
    assert all(s["status"] == "planned" for s in first["sessions"])
    assert "training_load" not in first["totals"]
    response = await client.put(f"/athlete/activities/{activity.id}/association", headers=csrf_headers(client), json={"planned_session_id": items[0].id})
    assert response.status_code == 200
    checkin = await client.put("/athlete/checkins", headers=csrf_headers(client), json={"activity_id": activity.id, "status": "partial", "rpe": 6, "pain": False, "felt_unwell": False})
    assert checkin.status_code == 200, checkin.text
    second = (await client.get(f"/athlete/day?date={day}")).json()
    assert second["sessions"][0]["status"] == "partial"
    assert second["activities"][0]["comparison"]["duration_delta_min"] == 0
    assert second["totals"]["session_rpe_load"]["value"] == 180
    assert (await client.put("/athlete/checkins", headers=csrf_headers(client), json={"activity_id": activity.id, "status": "partial", "rpe": 6, "pain": False, "felt_unwell": False})).json()["id"] == checkin.json()["id"]


async def test_protected_session_engine_and_exact_adaptation_approval_undo(db_session):
    day = datetime(2026, 10, 9).date()
    plan, items = await make_plan(db_session, day, protected=True)
    spec = ProposeIn.model_validate({"change": {"kind": "session_patch", "target_id": items[0].id, "target_duration_min": 20}, "reason": "Shorter schedule"})
    with pytest.raises(EvidenceError, match="Protected"):
        await propose(db_session, 1, spec)
    plan.protected = False
    await db_session.commit()
    draft = await propose(db_session, 1, spec)
    assert draft["adaptation"]["original_session"]["target_duration_min"] == 30
    assert draft["adaptation"]["proposed_session"]["target_duration_min"] == 20
    assert draft["adaptation"]["objective_status"] == "uncertain"
    await apply(db_session, 1, draft["id"], draft["payload_hash"])
    await db_session.commit()
    await undo(db_session, 1, draft["id"])
    assert items[0].target_duration_min == 30


async def test_profile_time_budget_rest_day_and_life_illness_constraints(client, db_session):
    await authenticate(client)
    day = datetime(2026, 10, 9).date()
    _, items = await make_plan(db_session, day)
    db_session.add(AthleteProfile(user_id=1, training_focus=["running", "gym"], context={"weekly_time_budget_min": 10}))
    await db_session.commit()
    spec = ProposeIn.model_validate({"change": {"kind": "session_patch", "target_id": items[0].id, "target_duration_min": 20}, "reason": "Review volume"})
    with pytest.raises(EvidenceError, match="weekly time"):
        await propose(db_session, 1, spec)
    await db_session.rollback()
    response = await client.post("/athlete/life-events", headers=csrf_headers(client), json={"kind": "illness", "starts_on": str(day), "ends_on": str(day), "note": "Self reported"})
    assert response.status_code == 201
    user = await db_session.get(User, 1)
    result = await constraints(db_session, user, day)
    assert result["athlete"]["training_focus"] == ["running", "gym"]
    assert result["subjective"][-1]["felt_unwell"] is True


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
async def test_account_local_day_dst_and_historical_state(db_session, day, hours):
    from datetime import date, time
    local = date.fromisoformat(day)
    user = await db_session.get(User, 1)
    user.timezone = "Europe/Rome"
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(local, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(local+timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    assert (end-start).total_seconds() / 3600 == hours
    for stamp in (start-timedelta(seconds=1), start, end-timedelta(seconds=1), end):
        db_session.add(Activity(user_id=1, start_time=stamp, local_date=stamp.date(), start_tz_offset_minutes=0, duration_s=60))
    await db_session.commit()
    timeline = await your_day(db_session, user, local)
    assert len(timeline["activities"]) == 2 and timeline["date"] == day
    assert timeline["sessions"] == []
