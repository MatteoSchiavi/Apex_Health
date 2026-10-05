"""Account-scoped integration disconnect behavior."""

import os
import asyncio
from types import SimpleNamespace

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.encryption import decrypt_json, encrypt_json
from app.models.integration import Integration, RawIngest
from app.models.user import AuthCredential, User
from tests.conftest import csrf_headers, login


async def test_disconnect_clears_only_own_credentials_and_preserves_history(
    client: AsyncClient, db_session
):
    owner_id = await db_session.scalar(
        select(AuthCredential.user_id).where(AuthCredential.role == "owner")
    )
    owner = await db_session.get(User, owner_id)
    other = User(name="Disconnect isolation account")
    db_session.add(other)
    await db_session.flush()

    mine = Integration(
        user_id=owner_id,
        provider="whoop",
        status="active",
        credentials_encrypted=encrypt_json({"access_token": "mine"}),
    )
    theirs = Integration(
        user_id=other.id,
        provider="whoop",
        status="active",
        credentials_encrypted=encrypt_json({"access_token": "theirs"}),
    )
    db_session.add_all([mine, theirs])
    await db_session.flush()
    owner.main_integration_id = mine.id
    historical = RawIngest(
        user_id=owner_id,
        source="whoop",
        payload_type="sleep",
        raw_json={"external_id": "kept-after-disconnect"},
    )
    db_session.add(historical)
    await db_session.commit()

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await redis.set("whoop:oauth:state:mine", str(owner_id), ex=600)
    await redis.set("whoop:oauth:state:theirs", str(other.id), ex=600)
    await redis.aclose()

    await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])
    response = await client.delete(
        "/settings/integrations/whoop", headers=csrf_headers(client)
    )
    assert response.status_code == 200
    assert response.json() == {
        "provider": "whoop",
        "disconnected": True,
        "provider_revocation": "unsupported",
    }

    await db_session.refresh(mine)
    await db_session.refresh(theirs)
    await db_session.refresh(owner)
    assert mine.status == "revoked"
    assert mine.credentials_encrypted is None
    assert theirs.status == "active"
    assert decrypt_json(theirs.credentials_encrypted) == {"access_token": "theirs"}
    assert owner.main_integration_id is None
    assert await db_session.get(RawIngest, historical.id) is not None

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    assert await redis.get("whoop:oauth:state:mine") is None
    assert await redis.get("whoop:oauth:state:theirs") == str(other.id)
    await redis.aclose()


async def test_disconnect_requires_session(client: AsyncClient):
    response = await client.delete(
        "/settings/integrations/garmin", headers=csrf_headers(client)
    )
    assert response.status_code == 401


async def test_oauth_completion_and_disconnect_cannot_restore_cancelled_credentials(
    client, db_session, monkeypatch
):
    from app.connectors.whoop import flow

    owner_id = await db_session.scalar(select(AuthCredential.user_id).where(AuthCredential.role == "owner"))
    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await redis.set("whoop:oauth:state:in-flight", str(owner_id), ex=600)
    await redis.set("whoop:oauth:state:cancelled", str(owner_id), ex=600)
    await redis.aclose()
    started, release = asyncio.Event(), asyncio.Event()

    async def exchange(code):
        started.set()
        await release.wait()
        return SimpleNamespace(expires_at=None, as_credentials=lambda: {"access_token": "test-token"})

    monkeypatch.setattr(flow, "WhoopOAuth", lambda: SimpleNamespace(exchange_code=exchange))
    await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])
    callback = asyncio.create_task(client.get("/integrations/whoop/callback?state=in-flight&code=test-code"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        # Completion holds the same account/provider lock as disconnect. The
        # caller can retry once it finishes, rather than seeing false success.
        busy = await client.delete("/settings/integrations/whoop", headers=csrf_headers(client))
        assert busy.status_code == 409
    finally:
        release.set()
        connected = await asyncio.wait_for(callback, timeout=5)
    assert connected.status_code == 200
    disconnected = await client.delete("/settings/integrations/whoop", headers=csrf_headers(client))
    assert disconnected.status_code == 200
    late = await client.get("/integrations/whoop/callback?state=cancelled&code=late-code")
    assert late.status_code == 400
    row = await db_session.scalar(select(Integration).where(Integration.user_id == owner_id, Integration.provider == "whoop"))
    assert row.status == "revoked"
    assert row.credentials_encrypted is None
