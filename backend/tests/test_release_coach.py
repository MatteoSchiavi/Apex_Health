"""Provider errors stay explicit and draft transitions stay serialized."""

from tests.helpers.ai import authorized_ai_account  # noqa: F401

import os
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.llm import LLMError, LLMUnavailableError
from app.core.llm import LLMResponse
from app.models.medical import SupplementProtocol
from app.models.user import User
from app.queries.plans import confirm_supplement_draft
from tests.conftest import csrf_headers, reset_owner_auth_state
from tests.helpers.ai import FixtureAgentLLMClient


@pytest.mark.parametrize("error,status", [
    (LLMError("private-provider-secret"), 502),
    (LLMUnavailableError("provider unconfigured"), 503),
])
async def test_chat_provider_failure_is_explicit_and_releases_lock(client, db_session, monkeypatch, error, status):
    await reset_owner_auth_state(db_session)
    await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]})
    class FailingLLM:
        closed = False
        async def complete(self, **kwargs): raise error
        async def aclose(self): self.closed = True
    llm = FailingLLM()
    monkeypatch.setattr("app.api.chats.build_llm_client", lambda: llm)
    for _ in range(2):
        response = await client.post("/coach/chats", json={"text": "How is my recovery?"}, headers=csrf_headers(client))
        assert response.status_code == status  # second attempt is not locked
        assert "private-provider-secret" not in response.text
    assert llm.closed


async def test_chat_http_starts_and_resumes_same_conversation(client, db_session, monkeypatch):
    await reset_owner_auth_state(db_session)
    await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]})
    llm = FixtureAgentLLMClient([
        LLMResponse(content="First recorded reply", model="fixture"),
        LLMResponse(content="Second recorded reply", model="fixture"),
        LLMResponse(content="New conversation reply", model="fixture"),
    ])
    monkeypatch.setattr("app.api.chats.build_llm_client", lambda: llm)
    first = await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "First question", "tier": "cheap"})
    assert first.status_code == 201
    body = first.json()
    assert body["messages"][-1]["content"] == "First recorded reply"
    second = await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "Follow-up", "tier": "cheap", "session_id": body["id"]})
    assert second.status_code == 201
    assert second.json()["id"] == body["id"]
    assert len(second.json()["messages"]) == 4
    assert second.json()["messages"][-1]["content"] == "Second recorded reply"
    new = await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "New topic", "tier": "cheap"})
    assert new.status_code == 201
    assert new.json()["id"] != body["id"]
    assert len(new.json()["messages"]) == 2
    assert (await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "Invalid", "session_id": -1})).status_code == 422


async def test_friend_cannot_override_ai_access_cap(client, db_session, monkeypatch):
    from app.core.security import hash_password
    from app.models.user import AuthCredential
    user = User(name="capped-coach")
    db_session.add(user)
    await db_session.flush()
    email = f"capped-coach-{user.id}@example.com"
    password = "Friend-password-42!"
    db_session.add(AuthCredential(user_id=user.id, email=email, password_hash=hash_password(password), ai_access_tier="cheap_only"))
    await db_session.commit()
    from tests.helpers.ai import authorize_ai
    await authorize_ai(db_session, user.id)
    assert (await client.post("/auth/login", json={"email": email, "password": password})).status_code == 200
    llm = FixtureAgentLLMClient([LLMResponse(content="Allowed reply", model="fixture")])
    monkeypatch.setattr("app.api.chats.build_llm_client", lambda: llm)
    response = await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "Help me train", "tier": "powerful"})
    assert response.status_code == 201
    assert {call["tier"] for call in llm.calls} == {"cheap"}


async def test_supplement_replacement_ends_previous_protocol_day_before_start(db_session):
    user = User(name="protocol-replacement")
    db_session.add(user)
    await db_session.flush()
    old = SupplementProtocol(user_id=user.id, supplement_name="fixture-protocol", active=True, start_date=date(2026, 1, 1))
    new = SupplementProtocol(user_id=user.id, supplement_name="fixture-protocol", active=False, start_date=date(2026, 10, 3))
    db_session.add_all([old, new])
    await db_session.commit()
    assert await confirm_supplement_draft(db_session, user.id, new.id) == "confirmed"
    await db_session.commit()
    assert old.active is False
    assert old.end_date == new.start_date - timedelta(days=1)
    assert await confirm_supplement_draft(db_session, user.id, new.id) == "not_draft"
