"""Personal API connection security and account isolation, without Garmin I/O."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text

from app.connectors.garmin.client import GarminAuthError
from app.connectors.garmin.personal import GarminPersonalClient, GarminPersonalError
from app.core.encryption import decrypt_json, encrypt_json
from app.models.integration import Integration, RawIngest
from app.models.user import AuthCredential, User
from tests.conftest import csrf_headers, login, reset_owner_auth_state

ENDPOINT = "/settings/integrations/garmin/personal/connect"
API_KEY = "garmin-personal-key-test-DO-NOT-RETURN"
ACCESS_TOKEN = "garmin-personal-token-test-DO-NOT-RETURN"


async def owner_login(client, session):
    await reset_owner_auth_state(session)
    response = await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])
    assert response.status_code == 200


async def post_key(client, **kwargs):
    return await client.post(ENDPOINT, headers=csrf_headers(client), json={"api_key": API_KEY}, **kwargs)


@pytest.fixture
def personal_client(monkeypatch):
    state = SimpleNamespace(clients=[], queued=[], failure=None, on_authenticate=None)

    class FakeClient:
        def __init__(self, credentials):
            self.credentials = dict(credentials)
            self.authenticated = False
            self.closed = False
            state.clients.append(self)

        async def authenticate(self):
            if state.on_authenticate:
                await state.on_authenticate()
            if state.failure:
                raise state.failure
            self.authenticated = True

        def dump_tokens(self):
            assert self.authenticated, "Credentials may only persist after Garmin verification"
            return {**self.credentials, "access_token": ACCESS_TOKEN, "expires_at": 1900000000}

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr("app.api.integrations.GarminPersonalClient", FakeClient)
    monkeypatch.setattr("app.tasks.garmin_sync.sync_user_garmin.delay", state.queued.append)
    return state


@pytest.fixture
async def accounts(db_session):
    owner_credential = await db_session.scalar(select(AuthCredential).where(AuthCredential.role == "owner"))
    owner = await db_session.get(User, owner_credential.user_id)
    friend = User(name="Personal API isolation fixture")
    db_session.add(friend)
    await db_session.flush()
    email = f"garmin-personal-{uuid4().hex}@example.com"
    db_session.add(AuthCredential(
        user_id=friend.id, email=email, role="friend",
        password_hash=owner_credential.password_hash,
    ))
    mine = await db_session.scalar(select(Integration).where(
        Integration.user_id == owner.id, Integration.provider == "garmin",
    ))
    if mine is None:
        mine = Integration(user_id=owner.id, provider="garmin")
        db_session.add(mine)
    original_credentials = {"di_token": "old-session", "di_refresh_token": "old-refresh"}
    mine.credentials_encrypted = encrypt_json(original_credentials)
    mine.status = "active"
    mine.consecutive_failures = 2
    mine.last_synced_at = datetime(2026, 10, 1, 10, tzinfo=UTC)
    theirs = Integration(
        user_id=friend.id, provider="garmin", status="active",
        credentials_encrypted=encrypt_json({"auth_type": "personal_api_key", "api_key": "other-account-key"}),
    )
    historical = RawIngest(
        user_id=owner.id, source="garmin", payload_type="activity",
        raw_json={"activityId": f"preserve-{uuid4().hex}"},
    )
    db_session.add_all([theirs, historical])
    await db_session.flush()
    owner.main_integration_id = mine.id
    await db_session.commit()
    return SimpleNamespace(
        owner=owner, friend=friend, friend_email=email, mine=mine, theirs=theirs,
        historical=historical, original_credentials=original_credentials,
        original_encrypted=mine.credentials_encrypted, last_synced_at=mine.last_synced_at,
    )


async def test_personal_connect_requires_session_and_csrf(client, db_session, personal_client):
    unauthenticated = await post_key(client)
    assert unauthenticated.status_code == 401
    await owner_login(client, db_session)
    missing_csrf = await client.post(ENDPOINT, json={"api_key": API_KEY})
    assert missing_csrf.status_code == 403
    assert personal_client.clients == []
    assert API_KEY not in unauthenticated.text + missing_csrf.text


async def test_personal_connect_is_owner_only(client, accounts, personal_client, db_session):
    assert (await login(client, accounts.friend_email, os.environ["OWNER_PASSWORD"])).status_code == 200
    rejected = await post_key(client)
    assert rejected.status_code == 403
    assert personal_client.clients == []
    await db_session.refresh(accounts.theirs)
    assert decrypt_json(accounts.theirs.credentials_encrypted)["api_key"] == "other-account-key"


@pytest.mark.parametrize("body", [
    {}, {"api_key": ""}, {"api_key": "  "}, {"api_key": API_KEY * 200},
    {"api_key": [API_KEY]}, {"api_key": {"secret": API_KEY}},
    {"api_key": API_KEY, "unexpected": API_KEY},
    {"api_key": API_KEY, "user_id": 99999},
    {"api_key": API_KEY, "expires_on": "2030-01-01"},
])
async def test_invalid_personal_request_never_echoes_secrets(
    client, db_session, personal_client, body, caplog
):
    await owner_login(client, db_session)
    rejected = await client.post(ENDPOINT, headers=csrf_headers(client), json=body)
    assert rejected.status_code == 422
    assert API_KEY not in rejected.text
    assert API_KEY not in caplog.text
    assert personal_client.clients == []
    assert personal_client.queued == []


async def test_malformed_json_never_echoes_secret(client, db_session, personal_client):
    await owner_login(client, db_session)
    response = await client.post(
        ENDPOINT, headers={**csrf_headers(client), "Content-Type": "application/json"},
        content='{"api_key": "' + API_KEY,
    )
    assert response.status_code == 422
    assert API_KEY not in response.text
    assert personal_client.clients == []


async def test_verified_key_replaces_only_owner_credentials_and_preserves_history(
    client, db_session, accounts, personal_client, caplog
):
    await owner_login(client, db_session)
    response = await post_key(client)
    assert response.status_code == 200
    assert response.json() == {
        "connected": True, "provider": "garmin", "auth_method": "personal_api_key",
        "backfill_enqueued": True,
    }
    await db_session.refresh(accounts.mine)
    await db_session.refresh(accounts.theirs)
    await db_session.refresh(accounts.owner)
    stored = decrypt_json(accounts.mine.credentials_encrypted)
    assert stored == {
        "auth_type": "personal_api_key", "api_key": API_KEY,
        "access_token": ACCESS_TOKEN, "expires_at": 1900000000,
    }
    assert API_KEY.encode() not in accounts.mine.credentials_encrypted
    assert accounts.mine.status == "active"
    assert accounts.mine.consecutive_failures == 0
    assert accounts.mine.last_synced_at == accounts.last_synced_at
    assert accounts.owner.main_integration_id == accounts.mine.id
    assert await db_session.get(RawIngest, accounts.historical.id) is not None
    assert decrypt_json(accounts.theirs.credentials_encrypted)["api_key"] == "other-account-key"
    assert personal_client.queued == [accounts.owner.id]
    assert personal_client.clients[0].closed
    for endpoint in ("/settings/integrations", "/settings/devices"):
        listing = await client.get(endpoint)
        assert listing.status_code == 200
        garmin = next(row for row in listing.json() if row["provider"] == "garmin")
        assert garmin["auth_method"] == "personal_api_key"
        assert "other-account-key" not in listing.text
        assert API_KEY not in listing.text
        assert ACCESS_TOKEN not in listing.text
    assert API_KEY not in response.text + caplog.text
    assert ACCESS_TOKEN not in response.text + caplog.text


@pytest.mark.parametrize("failure, expected_status", [
    (GarminAuthError(API_KEY), 400),
    (GarminPersonalError(API_KEY, error_class="transport"), 503),
    (GarminPersonalError(API_KEY, error_class="timeout"), 503),
    (GarminPersonalError(API_KEY, error_class="permission", status_code=403), 400),
    (GarminPersonalError(API_KEY, status_code=429), 429),
])
async def test_failed_verification_keeps_working_credentials_and_sanitizes_errors(
    client, db_session, accounts, personal_client, failure, expected_status, caplog
):
    personal_client.failure = failure
    await owner_login(client, db_session)
    response = await post_key(client)
    assert response.status_code == expected_status
    assert API_KEY not in response.text + caplog.text
    await db_session.refresh(accounts.mine)
    assert accounts.mine.credentials_encrypted == accounts.original_encrypted
    assert accounts.mine.last_synced_at == accounts.last_synced_at
    assert accounts.mine.status == "active"
    assert personal_client.queued == []
    assert personal_client.clients[0].closed


async def test_rate_limit_is_shared_with_legacy_and_scoped_to_user(
    client, db_session, accounts, personal_client
):
    personal_client.failure = GarminAuthError("fixture invalid key")
    await owner_login(client, db_session)
    for _ in range(3):
        assert (await post_key(client)).status_code == 400
    response = await post_key(client)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    legacy = await client.post(
        "/settings/integrations/garmin/connect", headers=csrf_headers(client),
        json={"email": "fixture@example.test", "password": API_KEY},
    )
    assert legacy.status_code == 429
    assert len(personal_client.clients) == 3
    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        assert 0 < await redis.ttl(f"garmin_connect:rl:user:{accounts.owner.id}") <= 3600
        assert await redis.get(f"garmin_connect:rl:user:{accounts.friend.id}") is None
    finally:
        await redis.aclose()


async def test_queue_outage_reports_saved_connection_without_false_enqueue(
    client, db_session, accounts, personal_client, monkeypatch
):
    def queue_failure(user_id):
        raise RuntimeError("broker offline")

    monkeypatch.setattr("app.tasks.garmin_sync.sync_user_garmin.delay", queue_failure)
    await owner_login(client, db_session)
    response = await post_key(client)
    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["backfill_enqueued"] is False
    await db_session.refresh(accounts.mine)
    assert decrypt_json(accounts.mine.credentials_encrypted)["api_key"] == API_KEY


async def test_constructor_auth_failure_is_sanitized_and_preserves_existing_connection(
    client, db_session, accounts, personal_client, monkeypatch
):
    def rejected_constructor(credentials):
        raise GarminAuthError(API_KEY)

    monkeypatch.setattr("app.api.integrations.GarminPersonalClient", rejected_constructor)
    await owner_login(client, db_session)
    response = await post_key(client)
    assert response.status_code == 400
    assert API_KEY not in response.text
    await db_session.refresh(accounts.mine)
    assert accounts.mine.credentials_encrypted == accounts.original_encrypted
    assert personal_client.queued == []


async def test_key_with_internal_whitespace_is_rejected_without_network_or_secret_echo(
    client, db_session, accounts, personal_client, monkeypatch
):
    monkeypatch.setattr("app.api.integrations.GarminPersonalClient", GarminPersonalClient)
    await owner_login(client, db_session)
    response = await client.post(
        ENDPOINT, headers=csrf_headers(client), json={"api_key": API_KEY + " invalid"},
    )
    assert response.status_code == 400
    assert API_KEY not in response.text
    await db_session.refresh(accounts.mine)
    assert accounts.mine.credentials_encrypted == accounts.original_encrypted
    assert personal_client.queued == []


async def test_active_sync_blocks_personal_and_legacy_connection(
    client, db_session, accounts, personal_client
):
    lock_id = int.from_bytes(
        hashlib.sha256(f"sync:garmin:{accounts.owner.id}".encode()).digest()[:8], "big", signed=True,
    )
    await owner_login(client, db_session)
    # owner_login commits this fixture's session while resetting lockout, so
    # acquire the external worker lock after it.
    await db_session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    try:
        response = await post_key(client)
        assert response.status_code == 409
        legacy = await client.post(
            "/settings/integrations/garmin/connect", headers=csrf_headers(client),
            json={"email": "fixture@example.test", "password": API_KEY},
        )
        assert legacy.status_code == 409
        assert personal_client.clients == []
    finally:
        await db_session.rollback()


async def test_inflight_key_exchange_blocks_disconnect(
    client, db_session, accounts, personal_client
):
    started, release = asyncio.Event(), asyncio.Event()

    async def exchange():
        started.set()
        await release.wait()

    personal_client.on_authenticate = exchange
    await owner_login(client, db_session)
    connecting = asyncio.create_task(post_key(client))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        busy = await client.delete("/settings/integrations/garmin", headers=csrf_headers(client))
        assert busy.status_code == 409
    finally:
        release.set()
        connected = await asyncio.wait_for(connecting, timeout=5)
    assert connected.status_code == 200
    disconnected = await client.delete("/settings/integrations/garmin", headers=csrf_headers(client))
    assert disconnected.status_code == 200
    await db_session.refresh(accounts.mine)
    assert accounts.mine.status == "revoked"
    assert accounts.mine.credentials_encrypted is None


async def test_friend_settings_never_decrypt_credentials(
    client, db_session, accounts, monkeypatch
):
    attempted = []

    def forbidden_decrypt(ciphertext):
        attempted.append(True)
        raise AssertionError("Friend settings must not decrypt credential blobs")

    monkeypatch.setattr("app.connectors.garmin.metadata.decrypt_json", forbidden_decrypt)
    assert (await login(client, accounts.friend_email, os.environ["OWNER_PASSWORD"])).status_code == 200
    for endpoint in ("/settings/integrations", "/settings/devices"):
        response = await client.get(endpoint)
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["provider"] == "garmin"
        assert rows[0]["auth_method"] is None
        assert "other-account-key" not in response.text
    assert attempted == []


async def test_owner_legacy_connection_has_explicit_auth_method(client, db_session, accounts):
    await owner_login(client, db_session)
    for endpoint in ("/settings/integrations", "/settings/devices"):
        response = await client.get(endpoint)
        assert response.status_code == 200
        row = next(item for item in response.json() if item["provider"] == "garmin")
        assert row["auth_method"] == "garmin_connect"
        assert "old-session" not in response.text
