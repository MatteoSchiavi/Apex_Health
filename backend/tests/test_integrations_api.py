import os
"""Phase 6 AC1 tests — Technogym OAuth connection (§11 Stage 11a, §18,
§23 Phase 6: "OAuth completes (manual connection)").

The API endpoints + shared flow prove the connection path end-to-end with a
MockTransport token endpoint — the owner's real browser step is simulated
exactly once here, with fixture payloads (§0/§16.7/§20). State is single-use
and TTL-bound; tokens land app-layer-encrypted (§17).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.encryption import decrypt_json
from app.models.integration import Integration

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "technogym"

SETTINGS = SimpleNamespace(
    technogym_client_id="cid-fixture",
    technogym_client_secret="secret-fixture",
    technogym_redirect_uri="http://localhost:8000/integrations/technogym/callback",
    technogym_oauth_authorize_url="https://oauth.mywellness.com/Authorize/Authorize",
    technogym_oauth_token_url="https://token.mywellness.com/oauth2/token",
    technogym_api_base="https://api.mywellness.com/v4",
    technogym_scope="exercises.read",
)


def _token_endpoint_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=json.loads((FIXTURES / "token_success.json").read_text()))

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def fake_flow_settings(monkeypatch):
    """The flow touches settings in two modules (client + flow)."""
    monkeypatch.setattr(
        "app.connectors.technogym.client.get_settings", lambda: SETTINGS
    )
    monkeypatch.setattr("app.connectors.technogym.flow.get_settings", lambda: SETTINGS)


async def _login(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=CSRF
    )
    assert login.status_code == 200


async def test_integrations_list_requires_session(client: AsyncClient):
    assert (await client.get("/settings/integrations")).status_code == 401


async def test_integrations_list_after_login(client: AsyncClient, db_session):
    await _login(client)
    listed = (await client.get("/settings/integrations")).json()
    assert isinstance(listed, list)  # owner may have zero or more connectors


async def test_authorize_endpoint_requires_configured_client(
    client: AsyncClient, monkeypatch
):
    await _login(client)
    stripped = SimpleNamespace(
        **{**SETTINGS.__dict__, "technogym_client_id": "", "technogym_client_secret": ""}
    )
    monkeypatch.setattr(
        "app.connectors.technogym.flow.get_settings", lambda: stripped
    )
    resp = await client.post("/settings/integrations/technogym/authorize", headers=CSRF)
    assert resp.status_code == 400
    assert "developer.technogym.com" in resp.json()["detail"]  # §24 pointer


async def test_authorize_mints_single_use_state_and_url(client: AsyncClient):
    await _login(client)
    resp = await client.post("/settings/integrations/technogym/authorize", headers=CSRF)
    assert resp.status_code == 200
    body = resp.json()

    assert body["authorize_url"].startswith(SETTINGS.technogym_oauth_authorize_url)
    assert "response_type=code" in body["authorize_url"]
    assert f"state={body['state']}" in body["authorize_url"]
    assert body["expires_in_seconds"] == 600


async def test_manual_connection_flow_completes_and_stores_encrypted_tokens(
    client: AsyncClient, db_session, monkeypatch
):
    """AC1: OAuth completes (manual connection simulated with fixtures):
    authorize -> provider callback -> tokens stored app-layer-encrypted."""
    await _login(client)
    minted = (
        await client.post("/settings/integrations/technogym/authorize", headers=CSRF)
    ).json()

    captured: list[httpx.Request] = []
    monkeypatch.setattr(
        "app.connectors.technogym.flow.TechnogymOAuth",
        lambda: __import__(
            "app.connectors.technogym.client", fromlist=["TechnogymOAuth"]
        ).TechnogymOAuth(
            http=httpx.AsyncClient(transport=_token_endpoint_transport(captured))
        ),
    )

    callback = await client.get(
        "/integrations/technogym/callback",
        params={"code": "auth-code-from-provider", "state": minted["state"]},
    )
    assert callback.status_code == 200
    body = callback.json()
    assert body["status"] == "connected"
    assert body["provider"] == "technogym"

    # token endpoint was hit with the authorization-code grant
    assert len(captured) == 1
    req_body = (await captured[0].aread()).decode()
    assert "grant_type=authorization_code" in req_body
    assert "code=auth-code-from-provider" in req_body

    # integration row exists with ENCRYPTED credentials (§17)
    integration = (
        await db_session.scalars(
            select(Integration).where(Integration.provider == "technogym")
        )
    ).one()
    assert integration.status == "active"
    assert integration.credentials_encrypted is not None
    stored = decrypt_json(integration.credentials_encrypted)
    assert stored["access_token"] == "tg_access_token_fixture"
    assert stored["refresh_token"] == "tg_refresh_token_fixture"

    # the integrations list now reports the connector
    listed = (await client.get("/settings/integrations")).json()
    tg = next(i for i in listed if i["provider"] == "technogym")
    assert tg["credentials_stored"] is True and tg["status"] == "active"


async def test_callback_rejects_replayed_or_unknown_state(client: AsyncClient):
    # never-minted state
    bad = await client.get(
        "/integrations/technogym/callback",
        params={"code": "x", "state": "never-minted"},
    )
    assert bad.status_code == 400
    assert "unknown or expired state" in bad.json()["detail"]


async def test_callback_surfaces_provider_error(client: AsyncClient):
    resp = await client.get(
        "/integrations/technogym/callback", params={"error": "access_denied"}
    )
    assert resp.status_code == 400
    assert "access_denied" in resp.json()["detail"]


async def test_callback_requires_code_and_state(client: AsyncClient):
    resp = await client.get("/integrations/technogym/callback")
    assert resp.status_code == 400
    assert "code" in resp.json()["detail"]


async def test_state_is_single_use(client: AsyncClient, db_session, monkeypatch):
    await _login(client)
    minted = (
        await client.post("/settings/integrations/technogym/authorize", headers=CSRF)
    ).json()

    captured: list[httpx.Request] = []
    monkeypatch.setattr(
        "app.connectors.technogym.flow.TechnogymOAuth",
        lambda: __import__(
            "app.connectors.technogym.client", fromlist=["TechnogymOAuth"]
        ).TechnogymOAuth(
            http=httpx.AsyncClient(transport=_token_endpoint_transport(captured))
        ),
    )
    first = await client.get(
        "/integrations/technogym/callback",
        params={"code": "code-1", "state": minted["state"]},
    )
    assert first.status_code == 200

    replay = await client.get(
        "/integrations/technogym/callback",
        params={"code": "code-1", "state": minted["state"]},
    )
    # the state was consumed on first use — the replay is rejected either as
    # "already used" (race window) or "unknown/expired" (already deleted)
    assert replay.status_code == 400
    assert "state" in replay.json()["detail"]
