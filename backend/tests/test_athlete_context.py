"""Real database/API checks of optional context, consent and atomic reservations."""
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import get_settings
from app.core.llm import LLMResponse
from app.models.athlete import AiConsent, AiBudgetReservation
from app.models.user import AuthCredential
from app.services.ai_access import POLICY_VERSION, PURPOSE, guarded_complete, provider_identity, effective_access, reserve
from app.services.evidence import EvidenceError
from tests.conftest import login, csrf_headers


@pytest_asyncio.fixture(autouse=True)
async def isolated(db_session):
    await db_session.execute(text("TRUNCATE athlete_profiles, ai_consents, ai_budget_reservations, token_usage RESTART IDENTITY CASCADE"))
    await db_session.execute(text("UPDATE auth_credentials SET disabled=false, ai_access_tier='full', failed_login_count=0, locked_until=NULL WHERE user_id=1"))
    await db_session.commit()
    yield


async def authenticate(client):
    settings = get_settings()
    assert (await login(client, settings.owner_email, settings.owner_password)).status_code == 200


async def accept(db_session, user_id=1):
    db_session.add(AiConsent(user_id=user_id, active=True, policy_version=POLICY_VERSION,
        purpose=PURPOSE, provider_identity=provider_identity(), accepted_at=datetime.now(UTC)))
    await db_session.commit()


@pytest.mark.parametrize("priorities", [[], ["running"], ["running", "gym"], ["cycling", "gym", "running"]])
async def test_profile_optional_order_persistent_and_me(client, priorities):
    await authenticate(client)
    result = await client.put("/athlete/profile", headers=csrf_headers(client), json={
        "expected_revision": 0, "training_focus": priorities, "context": {"athlete_notes": "My variable schedule"}})
    assert result.status_code == 200, result.text
    profile = result.json()
    assert profile["training_focus"] == priorities and profile["revision"] == 1
    me = (await client.get("/me")).json()
    assert me["training_focus"] == priorities and me["athlete_context"]["athlete_notes"] == "My variable schedule"
    stale = await client.put("/athlete/profile", headers=csrf_headers(client), json={"expected_revision": 0})
    assert stale.status_code == 409
    exported = (await client.get("/lab/export/account.json")).json()
    assert "My variable schedule" in str(exported)
    assert (await client.delete("/athlete/profile", headers=csrf_headers(client))).status_code == 204
    assert (await client.get("/athlete/profile")).json() == {"training_focus": [], "context": {}, "revision": 2}


@pytest.mark.parametrize("invalid", [
    {"training_focus": ["running", "running"]}, {"training_focus": ["sailing"]},
    {"context": {"focuses": {"cycling": {}}}}, {"context": {"weekly_time_budget_min": -1}},
    {"context": {"availability": [{"day": 1, "start": "12:00", "end": "11:00"}]}},
    {"ai_access_tier": "full"}, {"user_id": 2},
])
async def test_profile_rejects_invalid_values_and_client_authority(client, invalid):
    await authenticate(client)
    response = await client.put("/athlete/profile", headers=csrf_headers(client), json={"expected_revision": 0, **invalid})
    assert response.status_code == 422


async def test_consent_voluntary_provider_bound_revocable_and_redacted_audit(client, db_session):
    await authenticate(client)
    initial = (await client.get("/athlete/ai")).json()
    assert initial["effective_access"] == "disabled" and initial["consent"] is None
    payload = {"active": True, "policy_version": initial["policy_version"], "provider_identity": initial["provider_identity"]}
    wrong = await client.put("/athlete/ai/consent", headers=csrf_headers(client), json={**payload, "provider_identity": "manipulated"})
    assert wrong.status_code == 409
    accepted = await client.put("/athlete/ai/consent", headers=csrf_headers(client), json=payload)
    assert accepted.status_code == 200 and accepted.json()["effective_access"] == "full"
    assert accepted.json()["consent"]["accepted_at"]
    withdrawn = await client.put("/athlete/ai/consent", headers=csrf_headers(client), json={**payload, "active": False})
    assert withdrawn.json()["effective_access"] == "disabled" and withdrawn.json()["consent"]["withdrawn_at"]
    chat = await client.post("/coach/chats", headers=csrf_headers(client), json={"text": "Help", "tier": "powerful"})
    assert chat.status_code == 403


class FixtureProvider:
    def __init__(self):
        self.calls = 0
    async def complete(self, **kwargs):
        self.calls += 1
        return LLMResponse(content="context", model="fixture", tokens_in=100, tokens_out=50)


async def test_provider_never_called_without_consent_revoked_or_basic_strategic(db_session):
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    provider = FixtureProvider()
    with pytest.raises(EvidenceError, match="consent"):
        await guarded_complete(maker, provider, 1, "standard_chat", messages=[], tier="cheap")
    await accept(db_session)
    credential = await db_session.get(AuthCredential, 1)
    credential.ai_access_tier = "cheap_only"
    await db_session.commit()
    with pytest.raises(EvidenceError):
        await guarded_complete(maker, provider, 1, "strategic_coaching", messages=[], tier="powerful")
    assert provider.calls == 0
    await guarded_complete(maker, provider, 1, "standard_chat", messages=[], tier="cheap")
    row = await db_session.get(AiConsent, 1, populate_existing=True)
    row.active = False
    await db_session.commit()
    with pytest.raises(EvidenceError):
        await guarded_complete(maker, provider, 1, "standard_chat", messages=[], tier="cheap")
    assert provider.calls == 1


async def test_budget_atomic_concurrent_reservations_and_reconciliation(db_session, monkeypatch):
    await accept(db_session)
    settings = get_settings().model_copy(update={"daily_token_budget_usd": 0.03})
    monkeypatch.setattr("app.services.ai_access.get_settings", lambda: settings)
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async def claim():
        async with maker() as session:
            ident = await reserve(session, 1, "standard_chat", "cheap", 100)
            await session.commit()
            return ident
    results = await asyncio.gather(claim(), claim(), return_exceptions=True)
    assert sum(isinstance(r, int) for r in results) == 1
    assert sum(isinstance(r, EvidenceError) for r in results) == 1
    provider = FixtureProvider()
    with pytest.raises(EvidenceError):
        await guarded_complete(maker, provider, 1, "standard_chat", messages=[], tier="cheap")
    assert provider.calls == 0
    await db_session.execute(text("DELETE FROM ai_budget_reservations"))
    await db_session.commit()
    await guarded_complete(maker, provider, 1, "standard_chat", messages=[], tier="cheap")
    row = await db_session.scalar(select(AiBudgetReservation))
    assert row.state == "reconciled" and row.actual_tokens == 150 and row.actual_usd < row.reserved_usd


async def test_server_policy_unknown_tier_provider_change_fail_closed(db_session, monkeypatch):
    await accept(db_session)
    settings = get_settings().model_copy(update={"ai_processing_enabled": False})
    monkeypatch.setattr("app.services.ai_access.get_settings", lambda: settings)
    assert await effective_access(db_session, 1) == "disabled"
    settings.ai_processing_enabled = True
    settings.llm_api_base_cheap, settings.llm_api_key_cheap, settings.llm_provider_cheap = "https://changed.invalid", "fixture", "fixture"
    assert await effective_access(db_session, 1) == "disabled"
