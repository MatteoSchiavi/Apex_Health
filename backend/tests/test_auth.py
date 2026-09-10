"""Acceptance tests for owner auth (Phase 0 criterion: "owner login works")."""

import os

from httpx import AsyncClient

from tests.conftest import reset_owner_auth_state

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


async def login(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/auth/login", json={"email": email, "password": password}, headers=CSRF
    )


async def test_owner_login_success_sets_hardened_cookie(
    client: AsyncClient, db_session
):
    await reset_owner_auth_state(db_session)
    resp = await login(client, OWNER_EMAIL, OWNER_PASSWORD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "owner"
    assert body["ai_access_tier"] == "full"

    set_cookie = resp.headers["set-cookie"]
    assert "hcc_session=" in set_cookie
    assert "HttpOnly" in set_cookie  # §22.2
    assert "Secure" in set_cookie    # §22.2
    assert "samesite=lax" in set_cookie.lower()  # §22.2


async def test_owner_session_row_is_server_side(client: AsyncClient, db_session):
    """§2: server-side sessions — the cookie token is NOT stored verbatim."""
    await reset_owner_auth_state(db_session)
    resp = await login(client, OWNER_EMAIL, OWNER_PASSWORD)
    token = resp.cookies["hcc_session"]

    from sqlalchemy import text

    rows = await db_session.execute(text("SELECT token_hash FROM sessions"))
    hashes = [r[0] for r in rows.fetchall()]
    assert len(hashes) >= 1
    assert token not in hashes  # only the peppered SHA-256 hash is stored


async def test_logout_destroys_session(client: AsyncClient, db_session):
    await reset_owner_auth_state(db_session)
    resp = await login(client, OWNER_EMAIL, OWNER_PASSWORD)
    cookie = resp.cookies

    out = await client.post("/auth/logout", headers=CSRF, cookies=cookie)
    assert out.status_code == 204

    replay = await client.post("/auth/logout", headers=CSRF, cookies=cookie)
    assert replay.status_code == 401
