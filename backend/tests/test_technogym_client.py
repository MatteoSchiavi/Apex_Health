"""Technogym OAuth + API client tests (MASTER_SPEC §11 Stage 11a).

All HTTP runs through httpx.MockTransport against the recorded fixtures —
no test can reach the live API (§0/§16.7/§20). Settings are faked the same
way the budget tests fake them (monkeypatched get_settings).
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.connectors.technogym.client import (
    LiveTechnogymClient,
    OAuthTokens,
    TechnogymAuthError,
    TechnogymOAuth,
    build_authorize_url,
    build_live_client,
    credentials_expired,
)

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


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.technogym.client.get_settings", lambda: SETTINGS
    )


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _token_transport(tokens_by_call: list[dict], calls: list[httpx.Request]) -> httpx.MockTransport:
    """Token endpoint serves the queued payloads; every request is recorded."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        payload = tokens_by_call.pop(0)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------- authorize URL


def test_authorize_url_carries_client_state_and_redirect():
    url = build_authorize_url("state-abc-123")
    assert url.startswith(SETTINGS.technogym_oauth_authorize_url)
    assert "response_type=code" in url
    assert "client_id=cid-fixture" in url
    assert (
        "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fintegrations%2Ftechnogym%2Fcallback"
        in url
    )
    assert "state=state-abc-123" in url
    assert "scope=exercises.read" in url


def test_authorize_url_omits_empty_scope(monkeypatch):
    stripped = SimpleNamespace(**{**SETTINGS.__dict__, "technogym_scope": ""})
    monkeypatch.setattr(
        "app.connectors.technogym.client.get_settings", lambda: stripped
    )
    assert "scope=" not in build_authorize_url("s")


# ---------------------------------------------------------------- token exchange


async def test_exchange_code_parses_fixture_token_response():
    calls: list[httpx.Request] = []
    oauth = TechnogymOAuth(
        http=httpx.AsyncClient(
            transport=_token_transport([_load("token_success.json")], calls), base_url=""
        )
    )
    before = datetime.now(UTC)
    tokens = await oauth.exchange_code("auth-code-1")

    assert tokens.access_token == "tg_access_token_fixture"
    assert tokens.refresh_token == "tg_refresh_token_fixture"
    assert tokens.expires_at is not None and tokens.expires_at > before
    assert tokens.raw["user_urn"] == "urn:mywellness:user:31416"

    body = (await calls[0].aread()).decode()
    assert calls[0].method == "POST"
    assert "grant_type=authorization_code" in body
    assert "code=auth-code-1" in body
    assert "client_id=cid-fixture" in body


async def test_exchange_code_requires_configured_client(monkeypatch):
    empty = SimpleNamespace(
        **{**SETTINGS.__dict__, "technogym_client_id": "", "technogym_client_secret": ""}
    )
    monkeypatch.setattr(
        "app.connectors.technogym.client.get_settings", lambda: empty
    )
    oauth = TechnogymOAuth(
        http=httpx.AsyncClient(
            transport=_token_transport([_load("token_success.json")], []), base_url=""
        )
    )
    with pytest.raises(TechnogymAuthError, match="not configured"):
        await oauth.exchange_code("code")


async def test_exchange_code_surfaces_provider_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    oauth = TechnogymOAuth(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(TechnogymAuthError, match="400"):
        await oauth.exchange_code("bad-code")


async def test_refresh_grant_posts_refresh_token():
    calls: list[httpx.Request] = []
    oauth = TechnogymOAuth(
        http=httpx.AsyncClient(
            transport=_token_transport([_load("token_refresh.json")], calls), base_url=""
        )
    )
    tokens = await oauth.refresh("rt-old")
    assert tokens.access_token == "tg_access_token_rotated"
    body = (await calls[0].aread()).decode()
    assert "grant_type=refresh_token" in body
    assert "refresh_token=rt-old" in body


# ---------------------------------------------------------------- token model


def test_credentials_roundtrip_preserves_expiry():
    tokens = OAuthTokens.from_response(_load("token_success.json"))
    restored = OAuthTokens.from_credentials(tokens.as_credentials())
    assert restored.access_token == tokens.access_token
    assert restored.refresh_token == tokens.refresh_token
    assert restored.expires_at == tokens.expires_at


def test_from_credentials_rejects_missing_access_token():
    with pytest.raises(TechnogymAuthError):
        OAuthTokens.from_credentials({"refresh_token": "orphan"})
    with pytest.raises(TechnogymAuthError):
        build_live_client(None)


def test_credentials_expiry_detection():
    fresh = OAuthTokens.from_response(
        {**_load("token_success.json"), "expires_in": 3600}
    )
    stale = OAuthTokens(
        access_token="a", refresh_token="r", expires_at=datetime.now(UTC) - timedelta(minutes=5)
    )
    assert credentials_expired(fresh.as_credentials()) is False
    assert credentials_expired(stale.as_credentials()) is True
    assert credentials_expired(None) is True


# ---------------------------------------------------------------- API client


def _api_transport(calls: list[httpx.Request], token_hits: list[int] = [0]) -> httpx.MockTransport:
    """Serve the recorded workout pages / detail / upload; 401s if a token
    endpoint call was expected but skipped (used by the freshness tests)."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/oauth2/token"):
            token_hits[0] += 1
            return httpx.Response(200, json=_load("token_refresh.json"))
        if path.endswith("/exercises") and request.method == "GET":
            offset = int(request.url.params.get("offset", "0"))
            name = "workouts_page1.json" if offset == 0 else "workouts_page2.json"
            return httpx.Response(200, json=_load(name))
        if path.endswith("/exercises/tg-wkt-003"):
            return httpx.Response(200, json=_load("workout_detail.json"))
        if path.endswith("/exercises/upload") and request.method == "POST":
            return httpx.Response(202, json={"status": "queued"})
        if path.endswith("/denied"):
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_get_workouts_paginates_and_carries_bearer():
    calls: list[httpx.Request] = []
    tokens = OAuthTokens.from_response(_load("token_success.json"))
    client = LiveTechnogymClient(
        tokens, http=httpx.AsyncClient(transport=_api_transport(calls))
    )

    page1 = await client.get_workouts(0, 2)
    page2 = await client.get_workouts(2, 2)

    assert [w["id"] for w in page1] == ["tg-wkt-003", "tg-wkt-002"]
    assert [w["id"] for w in page2] == ["tg-wkt-001"]
    auth_headers = {c.headers.get("Authorization") for c in calls if c.url.path.endswith("/exercises")}
    assert auth_headers == {"Bearer tg_access_token_fixture"}


async def test_get_workout_detail_returns_machine_data():
    client = LiveTechnogymClient(
        OAuthTokens.from_response(_load("token_success.json")),
        http=httpx.AsyncClient(transport=_api_transport([])),
    )
    detail = await client.get_workout_detail("tg-wkt-003")
    assert detail["equipmentName"] == "Run 7000 Treadmill"
    assert detail["inclineMaxPercent"] == 6.0


async def test_ensure_fresh_rotates_tokens_when_expired():
    calls: list[httpx.Request] = []
    stale = OAuthTokens(
        access_token="expired",
        refresh_token="rt-old",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    client = LiveTechnogymClient(
        stale, http=httpx.AsyncClient(transport=_api_transport(calls))
    )
    workouts = await client.get_workouts(0, 2)

    # request went out with the ROTATED token, and the caller can persist it
    assert client.tokens.access_token == "tg_access_token_rotated"
    assert client.tokens_out is not None
    assert client.tokens_out.refresh_token == "tg_refresh_token_rotated"
    auth = {c.headers.get("Authorization") for c in calls if c.url.path.endswith("/exercises")}
    assert auth == {"Bearer tg_access_token_rotated"}
    assert len(workouts) == 2


async def test_fresh_token_skips_refresh():
    calls: list[httpx.Request] = []
    token_hits = [0]
    tokens = OAuthTokens.from_response(_load("token_success.json"))  # expires in 1h
    client = LiveTechnogymClient(
        tokens, http=httpx.AsyncClient(transport=_api_transport(calls, token_hits))
    )
    await client.get_workouts(0, 2)
    assert token_hits[0] == 0  # token endpoint never touched


async def test_upload_fit_posts_multipart():
    calls: list[httpx.Request] = []
    client = LiveTechnogymClient(
        OAuthTokens.from_response(_load("token_success.json")),
        http=httpx.AsyncClient(transport=_api_transport(calls)),
    )
    result = await client.upload_fit("activity.fit", b"FIT-bytes-here")
    assert result == {"status": "queued"}
    posted = [c for c in calls if c.url.path.endswith("/exercises/upload")]
    assert len(posted) == 1 and posted[0].method == "POST"


async def test_unauthorized_raises_auth_error():
    client = LiveTechnogymClient(
        OAuthTokens.from_response(_load("token_success.json")),
        http=httpx.AsyncClient(transport=_api_transport([])),
    )
    with pytest.raises(TechnogymAuthError, match="unauthorized"):
        await client._get_json("/denied")


# ---------------------------------------------------------------- type map


async def test_resolve_equipment_maps_seed_disciplines(db_session):
    from app.connectors.technogym.type_map import load_discipline_index, resolve_equipment

    index = await load_discipline_index(db_session)
    rid, src = resolve_equipment("treadmill", index)
    assert src == "mapped"
    assert rid == index["running"]
    cid, _ = resolve_equipment("indoor_cycle", index)
    assert cid == index["road_cycling"]
    sid, _ = resolve_equipment("kinesis", index)
    assert sid == index["strength"]


async def test_resolve_equipment_falls_back_to_gym_general(db_session):
    from app.connectors.technogym.type_map import load_discipline_index, resolve_equipment

    index = await load_discipline_index(db_session)
    gid, src = resolve_equipment("holodeck", index)
    assert src == "fallback"
    assert gid == index["gym_general"]
    gid2, src2 = resolve_equipment(None, index)
    assert src2 == "fallback" and gid2 == gid
