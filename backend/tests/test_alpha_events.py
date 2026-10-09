"""Alpha utility telemetry: real API gates and outcomes, never live providers.

These integration tests use the suite's disposable PostgreSQL/Redis services.
They do not invoke a schema reset independently of the existing guarded suite.
"""

from tests.helpers.ai import authorized_ai_account  # noqa: F401

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.agent.entrypoint import AgentTurnResult
from app.agent.loop import AgentLoopResult
from app.models.alpha import AlphaEvent
from app.models.chat import AiChatMessage
from app.models.integration import Integration
from app.models.lab import ChangeDraft, DecisionRecord
from app.models.user import AuthCredential, User
from app.services.alpha_events import record_event
from tests.conftest import csrf_headers
from tests.test_admin_operations import friend
from tests.test_invites import _owner_login
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def clean_alpha_events(db_session):
    await db_session.execute(delete(AlphaEvent))
    await db_session.commit()
    yield


async def owner_id(session):
    return await session.scalar(select(AuthCredential.user_id).where(AuthCredential.role == "owner"))


async def events(session, user_id=None):
    query = select(AlphaEvent).order_by(AlphaEvent.id)
    if user_id is not None:
        query = query.where(AlphaEvent.user_id == user_id)
    return (await session.scalars(query)).all()


async def test_alpha_aggregates_require_owner_and_authentication(client, db_session):
    assert (await client.get("/api/admin/alpha")).status_code == 401
    owner, cookies, uid, _ = await friend(client, db_session)
    denied = await client.get("/api/admin/alpha", cookies=cookies)
    assert denied.status_code == 403
    client.cookies.clear()
    response = await client.get("/api/admin/alpha", cookies=owner)
    assert response.status_code == 200
    assert response.json()["decision_feedback_responses"] == 0
    assert response.json()["decision_influence_rate"] is None
    assert response.json()["acceptance_rate"] is None


async def test_event_metadata_whitelist_excludes_prompts_payloads_and_secrets(db_session):
    uid = await owner_id(db_session)
    row = record_event(db_session, uid, "agent_question_asked", {
        "session_id": 12, "draft_id": True, "experiment_id": -1,
        "provider": "garmin", "error_class": "token=SECRET",
        "prompt": "private health question SECRET", "text": "SECRET",
        "answer": "SECRET", "email": "secret@example.com", "credentials": "SECRET",
        "metric": "made_up_secret_metric", "url": "https://private/?token=SECRET",
    })
    await db_session.commit()
    assert row.metadata_json == {"session_id": 12, "provider": "garmin"}
    assert "SECRET" not in json.dumps(row.metadata_json)
    with pytest.raises(ValueError):
        record_event(db_session, uid, "arbitrary_event")


async def test_capture_deduplicates_repeated_views_and_refuses_sensitive_fields(client, db_session):
    owner = await _owner_login(client, db_session)
    for _ in range(3):
        response = await client.post("/alpha/events", json={"event": "overview_viewed"},
            cookies=owner, headers=csrf_headers(client, owner))
        assert response.status_code == 204
        client.cookies.clear()
    response = await client.post("/alpha/events", json={"event": "overview_viewed", "prompt": "SECRET"},
        cookies=owner, headers=csrf_headers(client, owner))
    assert response.status_code == 422
    assert [row.event for row in await events(db_session)] == ["overview_viewed"]
    assert (await events(db_session))[0].metadata_json == {}


def draft(uid, status, now):
    return ChangeDraft(user_id=uid, status=status, kind="context_patch", payload={},
        before={}, after={}, payload_hash="a" * 64, snapshot_revision="fixture",
        evidence_ids=[], reason="Synthetic review", risk="local_reversible",
        created_at=now, expires_at=now + timedelta(days=1))


async def test_proposal_ratios_use_unique_drafts_and_missing_feedback_is_excluded(client, db_session):
    owner = await _owner_login(client, db_session)
    uid, now = await owner_id(db_session), datetime.now(UTC)
    drafts = [draft(uid, status, now) for status in ("draft", "applied_locally", "rejected", "undone")]
    old = draft(uid, "draft", now - timedelta(days=40))
    db_session.add_all([*drafts, old])
    await db_session.flush()
    for _ in range(3):
        record_event(db_session, uid, "change_edited", {"draft_id": drafts[0].id})
    record_event(db_session, uid, "change_edited", {"draft_id": old.id})
    record_event(db_session, uid, "change_edited", {"draft_id": 99999999})
    for i, outcome in enumerate(({"influenced_plan": "yes"}, {"influenced_plan": "partly"},
                                  {"influenced_plan": "no"}, None, {}, {"influenced_plan": "unanswered"})):
        db_session.add(DecisionRecord(user_id=uid, date=now.date() - timedelta(days=i),
            snapshot_revision=f"alpha:{i}", output={}, outcome=outcome, created_at=now))
    record_event(db_session, uid, "integration_sync_failure", {"provider": "garmin", "error_class": "timeout"})
    record_event(db_session, uid, "integration_sync_failure", {"provider": "garmin", "error_class": "authentication"})
    await db_session.commit()
    response = await client.get("/api/admin/alpha", cookies=owner)
    assert response.status_code == 200
    body = response.json()
    assert body["proposals"] == 4
    assert body["acceptance_rate"] == 0.5
    assert body["rejection_rate"] == 0.25
    assert body["edit_rate"] == 0.25
    assert body["decision_feedback_responses"] == 3
    assert body["decision_influence_rate"] == pytest.approx(2 / 3)
    assert body["provider_failure_counts"] == {"garmin": 2}
    assert "reported influence" in body["formula"]


@pytest.mark.parametrize("provider,flow_name", [("technogym", "complete_authorization"),
    ("whoop", "whoop_complete"), ("strava", "strava_complete"), ("oura", "oura_complete")])
async def test_successful_oauth_records_connected_for_state_owned_account(client, db_session, monkeypatch, provider, flow_name):
    from app.api import integrations
    owner, cookies, uid, _ = await friend(client, db_session)
    row = Integration(user_id=uid, provider=provider, status="active")
    db_session.add(row)
    await db_session.commit()
    result = ({"integration_id": row.id, "provider": provider} if provider == "oura"
              else {"status": "connected", "provider": provider, "user_id": uid,
                    "expires_at": datetime.now(UTC).isoformat()})
    monkeypatch.setattr(integrations, flow_name, AsyncMock(return_value=result))
    # Browser cookie belongs to the owner; the OAuth flow's state-owned
    # integration belongs to the friend and determines the event account.
    response = await client.get(f"/integrations/{provider}/callback?code=SECRET_CODE&state=SECRET_STATE", cookies=owner)
    assert response.status_code == 200
    assert response.json() == result
    captured = await events(db_session)
    assert len(captured) == 1 and captured[0].user_id == uid
    assert captured[0].event == "integration_connected"
    assert captured[0].metadata_json == {"provider": provider}
    assert "SECRET" not in json.dumps(captured[0].metadata_json)


async def test_failed_oauth_does_not_record_connected(client, db_session, monkeypatch):
    from app.api import integrations
    monkeypatch.setattr(integrations, "oura_complete", AsyncMock(side_effect=integrations.OuraFlowError("Authorization failed")))
    response = await client.get("/integrations/oura/callback?code=invalid&state=invalid")
    assert response.status_code == 400
    assert not await events(db_session)


@pytest.mark.parametrize("grounding,expected", [("structured", "agent_answer_completed"),
    ("invalid", "agent_answer_failed"), ("incomplete", "agent_answer_failed")])
async def test_agent_events_follow_grounding_outcome_without_prompt_duplication(client, db_session, monkeypatch, grounding, expected):
    from app.api import chats
    owner = await _owner_login(client, db_session)
    monkeypatch.setattr(chats, "get_settings", lambda: SimpleNamespace(daily_token_budget_usd=0))
    monkeypatch.setattr(chats, "build_llm_client", lambda: SimpleNamespace(aclose=AsyncMock()))

    async def fake_turn(maker, llm, *, user_id, session_id, **kwargs):
        async with maker() as session:
            reply = AiChatMessage(session_id=session_id, role="assistant", content="Fixture answer", model_tier="cheap")
            session.add(reply)
            await session.commit()
            return AgentTurnResult(reply.content, session_id, reply.id,
                loop=AgentLoopResult(reply.content, "cheap", "fixture", converged=True,
                                     grounding={"status": grounding, "verified_claims": []}))

    monkeypatch.setattr(chats, "run_agent_turn", fake_turn)
    response = await client.post("/coach/chats", json={"text": "PRIVATE_PROMPT_SECRET", "tier": "cheap"},
        cookies=owner, headers=csrf_headers(client, owner))
    assert response.status_code == 201
    captured = await events(db_session)
    assert [r.event for r in captured] == ["agent_question_asked", expected]
    assert "PRIVATE_PROMPT_SECRET" not in json.dumps([r.metadata_json for r in captured])
    assert captured[-1].metadata_json == {"session_id": response.json()["id"]}


@pytest.mark.parametrize("failure,code,error_class", [("unavailable", 503, "unknown"), ("timeout", 504, "timeout")])
async def test_agent_provider_failure_records_one_question_one_failure(client, db_session, monkeypatch, failure, code, error_class):
    from app.api import chats
    from app.core.llm import LLMUnavailableError
    owner = await _owner_login(client, db_session)
    monkeypatch.setattr(chats, "get_settings", lambda: SimpleNamespace(daily_token_budget_usd=0))
    if failure == "unavailable":
        def unavailable():
            raise LLMUnavailableError("SECRET_CONFIG")
        monkeypatch.setattr(chats, "build_llm_client", unavailable)
    else:
        monkeypatch.setattr(chats, "build_llm_client", lambda: SimpleNamespace(aclose=AsyncMock()))
        monkeypatch.setattr(chats, "run_agent_turn", AsyncMock(side_effect=TimeoutError("SECRET_PROMPT")))
    response = await client.post("/coach/chats", json={"text": "PRIVATE_SECRET"},
        cookies=owner, headers=csrf_headers(client, owner))
    assert response.status_code == code
    captured = await events(db_session)
    assert [r.event for r in captured] == ["agent_question_asked", "agent_answer_failed"]
    assert captured[-1].metadata_json["error_class"] == error_class
    assert "SECRET" not in json.dumps([r.metadata_json for r in captured])


async def test_budget_rejected_question_is_not_counted_as_agent_usage(client, db_session, monkeypatch):
    from app.api import chats
    owner = await _owner_login(client, db_session)
    monkeypatch.setattr(chats, "get_settings", lambda: SimpleNamespace(daily_token_budget_usd=1))
    monkeypatch.setattr(chats, "user_day_spend", AsyncMock(return_value=Decimal(1)))
    response = await client.post("/coach/chats", json={"text": "SECRET"},
        cookies=owner, headers=csrf_headers(client, owner))
    assert response.status_code == 429 and not await events(db_session)


class LockConnection:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def scalar(self, *args): return True
    async def execute(self, *args): return None


@pytest.mark.parametrize("status,event,error_class", [("ok", "integration_sync_success", None),
    ("partial", "integration_sync_failure", "normalization"), ("skipped", None, None)])
async def test_sync_events_record_actual_completed_attempt_status(db_session, monkeypatch, status, event, error_class):
    from app.tasks import provider_sync
    uid = await owner_id(db_session)
    monkeypatch.setattr(provider_sync, "engine", SimpleNamespace(connect=LockConnection))
    monkeypatch.setattr(provider_sync, "_sync_account", AsyncMock(return_value={"status": status}))
    assert await provider_sync.sync_account("garmin", uid) == {"status": status}
    captured = await events(db_session)
    if event is None:
        assert not captured
    else:
        assert len(captured) == 1 and captured[0].event == event
        assert captured[0].metadata_json == ({"provider": "garmin", "error_class": error_class}
                                             if error_class else {"provider": "garmin"})


async def test_sync_retries_record_each_failed_attempt_with_sanitized_class(db_session, monkeypatch):
    from app.tasks import provider_sync
    uid = await owner_id(db_session)
    monkeypatch.setattr(provider_sync, "engine", SimpleNamespace(connect=LockConnection))
    monkeypatch.setattr(provider_sync, "_sync_account", AsyncMock(side_effect=TimeoutError("token=SECRET health=PRIVATE")))
    for _ in range(2):
        with pytest.raises(TimeoutError):
            await provider_sync.sync_account("garmin", uid)
    captured = await events(db_session)
    assert len(captured) == 2
    assert all(r.event == "integration_sync_failure" and r.metadata_json == {"provider": "garmin", "error_class": "timeout"} for r in captured)
    assert "SECRET" not in json.dumps([r.metadata_json for r in captured])


async def test_direct_and_durable_analyses_record_one_start_and_real_completion(db_session):
    from app.services.analytics import run_recipe
    from app.services.jobs import request_analysis
    user = await db_session.get(User, await owner_id(db_session))
    await run_recipe(db_session, user, "personal_baseline", metric="resting_hr", origin="garmin", for_ai=True)
    await db_session.commit()
    assert [r.event for r in await events(db_session)] == ["analysis_started", "analysis_completed"]
    await db_session.execute(delete(AlphaEvent))
    params = {"recipe": "personal_baseline", "metric": "resting_hr", "origin": "garmin"}
    job = await request_analysis(db_session, user, params)
    duplicate = await request_analysis(db_session, user, params)
    assert duplicate["id"] == job["id"]
    await db_session.commit()
    assert [r.event for r in await events(db_session)] == ["analysis_started"]
    await run_recipe(db_session, user, "personal_baseline", metric="resting_hr", origin="garmin", for_ai=True, job_id=job["id"])
    await db_session.commit()
    captured = await events(db_session)
    assert [r.event for r in captured] == ["analysis_started", "analysis_completed"]
    assert all(r.metadata_json == {"job_id": job["id"]} for r in captured)


async def test_invalid_recipe_does_not_report_completed_analysis(db_session):
    from app.services.analytics import run_recipe
    from app.services.evidence import EvidenceError
    user = await db_session.get(User, await owner_id(db_session))
    with pytest.raises(EvidenceError):
        await run_recipe(db_session, user, "unregistered-recipe")
    await db_session.commit()
    assert not await events(db_session)


async def test_committed_oauth_connection_survives_event_storage_failure(client, db_session, monkeypatch):
    from app.api import integrations
    uid = await owner_id(db_session)
    row = Integration(user_id=uid, provider="oura", status="active")
    db_session.add(row)
    await db_session.commit()
    monkeypatch.setattr(integrations, "oura_complete", AsyncMock(return_value={"integration_id": row.id, "provider": "oura"}))
    def fail_telemetry(*args, **kwargs):
        raise RuntimeError("SECRET_INTERNAL_ERROR")
    monkeypatch.setattr(integrations, "record_event", fail_telemetry)
    response = await client.get("/integrations/oura/callback?code=invalid&state=invalid")
    assert response.status_code == 200
    assert not await events(db_session)
