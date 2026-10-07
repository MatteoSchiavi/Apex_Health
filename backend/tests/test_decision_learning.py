"""Daily interpretation and optional feedback use the existing decision boundary."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, text

from app.api.performance_lab import decision_outcome
from app.models.activity import Activity
from app.models.alpha import AlphaEvent
from app.models.lab import AthleteEntry, ChangeDraft, DecisionRecord
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User
from app.schemas.lab import OutcomeIn
from app.services import decisions
from fastapi import HTTPException
from tests.conftest import csrf_headers

NOW = datetime(2026, 10, 4, 7, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def clean_learning_records(db_session):
    await db_session.execute(text("TRUNCATE decision_records, change_drafts, alpha_events RESTART IDENTITY CASCADE"))
    await db_session.commit()
    yield
    await db_session.rollback()
    plan_ids = db_session.info.get("decision_learning_plans", [])
    activity_ids = db_session.info.get("decision_learning_activities", [])
    entry_ids = db_session.info.get("decision_learning_entries", [])
    if entry_ids:
        await db_session.execute(delete(AthleteEntry).where(AthleteEntry.id.in_(entry_ids)))
    if activity_ids:
        await db_session.execute(delete(Activity).where(Activity.id.in_(activity_ids)))
    if plan_ids:
        await db_session.execute(delete(PlannedSession).where(PlannedSession.training_plan_id.in_(plan_ids)))
        await db_session.execute(delete(TrainingPlan).where(TrainingPlan.id.in_(plan_ids)))
    await db_session.commit()


async def interpretation(monkeypatch, db_session, *, locale="en", missing=False, sleep=7.5, pain=False):
    user = User(id=1, name="Athlete", timezone="UTC", locale=locale)
    values = {"hrv_overnight_rmssd": 60, "resting_hr": 52, "sleep_duration": sleep}
    async def coverage(*args, **kwargs):
        return {"metrics": [{"metric": metric, "availability": "stale" if missing else "available", "sample_days_7d": 0 if missing else 7,
            "latest": {"id": f"observation:{i}:1", "metric": metric, "value": value, "origin": "garmin", "local_date": str(NOW.date() - timedelta(days=7) if missing else NOW.date())}}
            for i, (metric, value) in enumerate(values.items(), 1)]}
    async def baseline(*args, **kwargs):
        return {"state": "available", "median": 62 if args[2] == "hrv_overnight_rmssd" else 50, "sample_count": 24}
    async def constraints(*args, **kwargs):
        return {"events": [], "availability": [], "subjective": [{"pain": pain}], "sessions": [{"id": 55, "date": str(NOW.date())}]}
    async def revision(*args, **kwargs):
        return "test-interpretation"
    monkeypatch.setattr(decisions, "coverage", coverage)
    monkeypatch.setattr(decisions, "baseline", baseline)
    monkeypatch.setattr(decisions, "constraints", constraints)
    monkeypatch.setattr(decisions, "snapshot_revision", revision)
    return await decisions.daily_decision(db_session, user, now=NOW)


async def test_interpretation_keeps_rules_and_source_comparison(monkeypatch, db_session):
    result = await interpretation(monkeypatch, db_session)
    assert result["action"] == "train_normally" and result["state"] == "stable"
    assert result["headline"] == "Keep your planned training"
    assert result["contributors"] == result["reasons"]
    assert result["data_coverage"] == result["data_completeness"]
    assert result["recommended_action"]["planned_session_id"] == 55
    assert result["key_changes"][0] == {"metric": "hrv_overnight_rmssd", "current": 60, "baseline": 62, "delta": -2, "origin": "garmin"}
    # Sleep has no comparable baseline in the existing rule: absence stays null.
    assert result["key_changes"][2]["baseline"] is None
    assert result["key_changes"][2]["delta"] is None
    assert result["evidence"][0]["origin"] == "garmin"


async def test_stale_evidence_remains_insufficient_and_has_no_current_delta(monkeypatch, db_session):
    result = await interpretation(monkeypatch, db_session, missing=True)
    assert result["state"] == "insufficient_data"
    assert result["action"] == "collect_more_data"
    assert result["confidence"] == "limited"
    assert all(change["current"] is None and change["delta"] is None for change in result["key_changes"])
    assert result["data_coverage"]["coverage_pct"] == 0
    assert result["evidence"]  # The historical source evidence is still inspectable.


async def test_italian_adjustment_and_symptom_override_are_deterministic(monkeypatch, db_session):
    reduced = await interpretation(monkeypatch, db_session, locale="it", sleep=5)
    assert reduced["headline"] == "Mantieni l’obiettivo, riduci il volume"
    assert reduced["recommended_action"]["duration_factor"] == 0.7
    assert reduced["contributors"][0].startswith("Il sonno registrato")
    recovery = await interpretation(monkeypatch, db_session, locale="it", missing=True, pain=True)
    assert recovery["state"] == "recovery_suggested"
    assert recovery["action"] == "recover"
    assert recovery["headline"] == "Dedica oggi al recupero"


async def learning_records(session, user_id=1, *, day=NOW.date()):
    plan = TrainingPlan(user_id=user_id, created_by="manual", week_start=day, status="active")
    session.add(plan)
    await session.flush()
    planned = PlannedSession(training_plan_id=plan.id, date=day, session_type="easy", target_duration_min=40)
    session.add(planned)
    await session.flush()
    draft = ChangeDraft(user_id=user_id, kind="session_patch", status="draft", payload={"kind": "session_patch", "target_id": planned.id},
        before={"target_id": planned.id, "date": str(day), "target_duration_min": 40},
        after={"target_id": planned.id, "date": str(day), "target_duration_min": 28},
        payload_hash="a" * 64, snapshot_revision="test", evidence_ids=[], reason="Less volume", expires_at=NOW + timedelta(days=1), created_at=NOW)
    activity = Activity(user_id=user_id, start_time=NOW, start_tz_offset_minutes=0, local_date=day, duration_s=1800)
    session.add_all([draft, activity])
    await session.flush()
    session.info.setdefault("decision_learning_plans", []).append(plan.id)
    session.info.setdefault("decision_learning_activities", []).append(activity.id)
    return planned, draft, activity


async def decision_record(session, user_id=1):
    row = DecisionRecord(user_id=user_id, date=NOW.date(), snapshot_revision=str(uuid4()), output={"action": "reduce_volume"})
    session.add(row)
    await session.flush()
    return row


async def test_http_partial_feedback_preserves_outcome_and_never_applies_draft(client, db_session):
    row = await decision_record(db_session)
    planned, draft, activity = await learning_records(db_session)
    await db_session.commit()
    response = await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]})
    assert response.status_code == 200
    path = f"/lab/decision/{row.id}/outcome"
    response = await client.post(path, headers=csrf_headers(client), json={"state": "modified", "influenced_plan": "partly", "useful": True, "notes": "Shortened to fit the day", "draft_id": draft.id})
    assert response.status_code == 200, response.text
    assert response.json()["outcome"]["planned_session_id"] == planned.id
    response = await client.post(path, headers=csrf_headers(client), json={"state": "accepted", "completion": "partial", "rpe": 4.5, "soreness": 2, "pain": False, "felt_unwell": False, "activity_id": activity.id})
    assert response.status_code == 200, response.text
    outcome = response.json()["outcome"]
    assert outcome["notes"] == "Shortened to fit the day"
    assert outcome["useful"] is True and outcome["influenced_plan"] == "partly"
    assert outcome["draft_id"] == draft.id and outcome["planned_session_id"] == planned.id
    assert outcome["rpe"] == 4.5 and outcome["completion"] == "partial"
    response = await client.post(path, headers=csrf_headers(client), json={"state": "snoozed"})
    assert response.status_code == 200 and response.json()["outcome"]["activity_id"] == activity.id
    await db_session.refresh(draft)
    await db_session.refresh(planned)
    assert draft.status == "draft" and planned.target_duration_min == 40
    events = (await db_session.scalars(select(AlphaEvent).where(AlphaEvent.event == "decision_feedback_submitted"))).all()
    assert len(events) == 3 and all(event.metadata_json == {"decision_id": row.id} for event in events)


async def test_experiment_created_event_uses_real_entry_and_not_checkin_completion(client, db_session):
    response = await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]})
    assert response.status_code == 200
    response = await client.post("/lab/entries", headers=csrf_headers(client), json={"entry": {
        "kind": "experiment", "date": str(NOW.date()), "end_date": str(NOW.date() + timedelta(days=2)),
        "title": "Earlier bedtime", "intervention": "Avoid late caffeine", "outcome_metric": "sleep_duration", "notes": "Private participant note",
    }})
    assert response.status_code == 201, response.text
    ident = response.json()["id"]
    db_session.info.setdefault("decision_learning_entries", []).append(ident)
    response = await client.post("/lab/entries", headers=csrf_headers(client), json={"entry": {
        "kind": "experiment_checkin", "date": str(NOW.date() + timedelta(days=1)), "experiment_id": ident, "exposed": True,
    }})
    assert response.status_code == 201, response.text
    db_session.info["decision_learning_entries"].append(response.json()["id"])
    events = (await db_session.scalars(select(AlphaEvent))).all()
    assert [(event.event, event.metadata_json) for event in events] == [("experiment_created", {"experiment_id": ident})]


@pytest.mark.parametrize("link", ["activity_id", "planned_session_id", "draft_id"])
async def test_feedback_rejects_foreign_links_without_recording_event(db_session, link):
    user = await db_session.get(User, 1)
    row = await decision_record(db_session)
    foreign = User(name="Feedback peer", timezone="UTC")
    db_session.add(foreign)
    await db_session.flush()
    planned, draft, activity = await learning_records(db_session, foreign.id)
    ident = {"activity_id": activity.id, "planned_session_id": planned.id, "draft_id": draft.id}[link]
    with pytest.raises(HTTPException) as error:
        await decision_outcome(row.id, OutcomeIn(state="accepted", **{link: ident}), db_session, user)
    assert error.value.status_code == 404
    assert row.outcome is None
    assert not (await db_session.scalars(select(AlphaEvent))).all()


@pytest.mark.parametrize("link", ["activity_id", "planned_session_id", "draft_id"])
async def test_feedback_requires_coherent_link_dates(db_session, link):
    user = await db_session.get(User, 1)
    row = await decision_record(db_session)
    planned, draft, activity = await learning_records(db_session, day=NOW.date() + timedelta(days=1))
    ident = {"activity_id": activity.id, "planned_session_id": planned.id, "draft_id": draft.id}[link]
    with pytest.raises(HTTPException) as error:
        await decision_outcome(row.id, OutcomeIn(state="accepted", **{link: ident}), db_session, user)
    assert error.value.status_code == 422 and row.outcome is None


async def test_feedback_rejects_mismatched_session_and_proposal(db_session):
    user = await db_session.get(User, 1)
    row = await decision_record(db_session)
    _, draft, _ = await learning_records(db_session)
    other_planned, _, _ = await learning_records(db_session)
    with pytest.raises(HTTPException) as error:
        await decision_outcome(row.id, OutcomeIn(state="modified", draft_id=draft.id, planned_session_id=other_planned.id), db_session, user)
    assert error.value.status_code == 422 and row.outcome is None


@pytest.mark.parametrize("field,value", [("rpe", 11), ("rpe", -1), ("soreness", 11), ("soreness", 1.5), ("completion", "unknown"), ("influenced_plan", "sometimes")])
def test_feedback_validates_bounded_optional_fields(field, value):
    with pytest.raises(ValidationError):
        OutcomeIn.model_validate({"state": "accepted", field: value})
    assert OutcomeIn(state="accepted").model_dump(exclude_unset=True) == {"state": "accepted"}
