"""Fitbit food diary OAuth/account flow with a mocked provider response."""

import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.conftest import login, sync_csrf_header
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_fitbit_reports_unconfigured_without_starting_oauth(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "fitbit_client_id", "")
    monkeypatch.setattr(settings, "fitbit_client_secret", "")
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    status = await client.get("/nutrition/fitbit/status")
    assert status.status_code == 200
    assert status.json()["configured"] is False
    authorize = await client.post(
        "/nutrition/fitbit/authorize", headers=sync_csrf_header(client)
    )
    assert authorize.status_code == 409


@pytest.mark.asyncio
async def test_fitbit_food_diary_uses_nutrition_scope_and_can_disconnect(
    client, monkeypatch
):
    from app.api import nutrition_integrations as api

    settings = get_settings()
    monkeypatch.setattr(settings, "fitbit_client_id", "test-fitbit-id")
    monkeypatch.setattr(settings, "fitbit_client_secret", "test-fitbit-secret")
    monkeypatch.setattr(
        settings,
        "fitbit_redirect_uri",
        "https://testserver/integrations/fitbit/callback",
    )
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    status = await client.get("/nutrition/fitbit/status")
    assert status.json() == {"configured": True, "connected": False, "provider": "fitbit"}

    start = await client.post(
        "/nutrition/fitbit/authorize", headers=sync_csrf_header(client)
    )
    assert start.status_code == 200
    query = parse_qs(urlparse(start.json()["authorize_url"]).query)
    assert query["scope"] == ["nutrition"]
    assert query["redirect_uri"] == [settings.fitbit_redirect_uri]

    async def fake_exchange(data):
        assert data["grant_type"] == "authorization_code"
        return {
            "access_token": "provider-access-token",
            "refresh_token": "provider-refresh-token",
            "scope": "nutrition",
            "expires_in": 3600,
        }

    monkeypatch.setattr(api, "_token_request", fake_exchange)
    callback = await client.get(
        "/integrations/fitbit/callback",
        params={"state": query["state"][0], "code": "provider-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/app/lab?tab=nutrition"
    replay = await client.get(
        "/integrations/fitbit/callback",
        params={"state": query["state"][0], "code": "provider-code"},
    )
    assert replay.status_code == 400
    assert (await client.get("/nutrition/fitbit/status")).json()["connected"] is True

    real_client = httpx.AsyncClient

    def fake_http_client(*args, **kwargs):
        def respond(request):
            assert request.url.path == "/1/user/-/foods/log/date/2026-10-05.json"
            assert request.headers["Authorization"] == "Bearer provider-access-token"
            return httpx.Response(
                200,
                json={
                    "summary": {"calories": 1200, "protein": 65, "water": 1000},
                    "foods": [
                        {
                            "loggedFood": {"name": "Oats", "amount": 1, "unit": {"name": "cup"}},
                            "nutritionalValues": {"calories": 300},
                        },
                        {"loggedFood": "invalid", "nutritionalValues": ["invalid"]},
                        {"loggedFood": {"name": "Tea", "unit": 12}, "nutritionalValues": None},
                    ],
                },
            )

        return real_client(*args, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(api.httpx, "AsyncClient", fake_http_client)
    diary = await client.get("/nutrition/fitbit/day/2026-10-05")
    assert diary.status_code == 200
    assert diary.json()["summary"]["calories"] == 1200
    assert diary.json()["foods"][0]["name"] == "Oats"
    assert diary.json()["foods"][1]["calories"] is None
    assert diary.json()["foods"][2]["unit"] is None

    disconnected = await client.delete(
        "/nutrition/fitbit", headers=sync_csrf_header(client)
    )
    assert disconnected.status_code == 204
    assert (await client.get("/nutrition/fitbit/status")).json()["connected"] is False
    assert (await client.get("/nutrition/fitbit/day/2026-10-05")).status_code == 409


@pytest.mark.asyncio
async def test_disconnect_invalidates_pending_fitbit_callback(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "fitbit_client_id", "test-fitbit-id")
    monkeypatch.setattr(settings, "fitbit_client_secret", "test-fitbit-secret")
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    start = await client.post(
        "/nutrition/fitbit/authorize", headers=sync_csrf_header(client)
    )
    state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
    assert (await client.delete(
        "/nutrition/fitbit", headers=sync_csrf_header(client)
    )).status_code == 204
    callback = await client.get(
        "/integrations/fitbit/callback", params={"state": state, "code": "late-code"}
    )
    assert callback.status_code == 400
    assert (await client.get("/nutrition/fitbit/status")).json()["connected"] is False


@pytest.mark.asyncio
async def test_refresh_requires_continued_nutrition_scope(client, monkeypatch):
    from app.api import nutrition_integrations as api

    settings = get_settings()
    monkeypatch.setattr(settings, "fitbit_client_id", "test-fitbit-id")
    monkeypatch.setattr(settings, "fitbit_client_secret", "test-fitbit-secret")
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    start = await client.post(
        "/nutrition/fitbit/authorize", headers=sync_csrf_header(client)
    )
    state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]

    async def fake_exchange(data):
        if data["grant_type"] == "authorization_code":
            return {"access_token": "initial", "refresh_token": "refresh", "scope": "nutrition", "expires_in": 0}
        return {"access_token": "revoked-scope", "refresh_token": "new-refresh", "scope": "activity", "expires_in": 3600}

    monkeypatch.setattr(api, "_token_request", fake_exchange)
    assert (await client.get(
        "/integrations/fitbit/callback", params={"state": state, "code": "code"}, follow_redirects=False
    )).status_code == 303
    diary = await client.get("/nutrition/fitbit/day/2026-10-05")
    assert diary.status_code == 403


@pytest.mark.asyncio
async def test_lab_file_download_uses_original_name_and_stays_private(client):
    assert (await client.get("/lab/documents")).status_code == 401
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    content = b"Ferritin 47 ng/mL\n"
    upload = await client.post(
        "/lab/documents",
        files={"file": ("blood results.md", content, "text/markdown")},
        headers=sync_csrf_header(client),
    )
    assert upload.status_code == 201, upload.text
    ident = upload.json()["id"]
    download = await client.get(f"/lab/documents/{ident}/original")
    assert download.status_code == 200
    assert download.content == content
    assert "blood%20results.md" in download.headers["content-disposition"]
    assert download.headers["cache-control"] == "no-store"
    assert (await client.delete(
        f"/lab/documents/{ident}", headers=sync_csrf_header(client)
    )).status_code == 204
    assert (await client.get(f"/lab/documents/{ident}/original")).status_code == 404
