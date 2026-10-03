"""Request-level regressions for session revocation and signed CSRF."""

import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select

from app.auth.rate_limit import LoginRateLimiter
from app.auth.service import resolve_session
from app.core.config import get_settings
from app.core.security import hash_password, hash_session_token
from app.main import app
from app.models.user import AuthCredential, UserSession
from tests.conftest import csrf_headers, reset_owner_auth_state


async def sign_in(client, session):
    await reset_owner_auth_state(session)
    response = await client.post("/auth/login", json={
        "email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"],
    })
    assert response.status_code == 200
    return response


async def test_password_change_revokes_other_sessions_only(client, db_session):
    first = await sign_in(client, db_session)
    first_cookies = dict(first.cookies)
    await sign_in(client, db_session)
    new_password = "Replacement-password-42!"
    try:
        changed = await client.put("/me/password", headers=csrf_headers(client), json={
            "current_password": os.environ["OWNER_PASSWORD"], "new_password": new_password,
        })
        assert changed.status_code == 204
        assert (await client.get("/me")).status_code == 200
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver", cookies=first_cookies) as other:
            assert (await other.get("/me")).status_code == 401
        assert (await client.post("/auth/login", json={
            "email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"],
        })).status_code == 401
        assert (await client.post("/auth/login", json={
            "email": os.environ["OWNER_EMAIL"], "password": new_password,
        })).status_code == 200
    finally:
        credential = await db_session.scalar(select(AuthCredential).where(AuthCredential.role == "owner"))
        credential.password_hash = hash_password(os.environ["OWNER_PASSWORD"])
        await db_session.commit()


async def test_login_rotates_and_csrf_is_bound_to_session(client, db_session):
    first = await sign_in(client, db_session)
    old_token = first.cookies["csrf_token"]
    second = await sign_in(client, db_session)
    assert second.cookies["csrf_token"] != old_token
    client.cookies.set("csrf_token", old_token, domain="testserver.local", path="/")
    rejected = await client.put("/me", json={"theme": "dark"}, headers={"X-CSRF-Token": old_token})
    assert rejected.status_code == 403
    # A safe read upgrades/repairs a legacy or stale CSRF cookie.
    assert (await client.get("/me")).status_code == 200
    assert (await client.put("/me", json={"theme": "dark"}, headers=csrf_headers(client))).status_code == 200


@pytest.mark.parametrize("headers", [
    {"Origin": "https://attacker.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"},
])
async def test_cross_origin_bootstrap_rejected(client, headers):
    assert (await client.post("/auth/login", headers=headers, json={
        "email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"],
    })).status_code == 403
    assert (await client.post("/auth/invite/redeem", headers=headers, json={})).status_code == 403


async def test_unknown_accounts_have_lockout_and_expiring_keys(client):
    email = "nonexistent-release-check@apexhealth.dev"
    settings = get_settings()
    for _ in range(settings.login_max_attempts):
        assert (await client.post("/auth/login", json={"email": email, "password": "incorrect"})).status_code == 401
    assert (await client.post("/auth/login", json={"email": email, "password": "incorrect"})).status_code == 429
    async with Redis.from_url(os.environ["REDIS_URL"]) as redis:
        key = LoginRateLimiter(redis, settings)._key(email)
        assert email not in key
        assert 0 < await redis.ttl(key) <= settings.login_window_minutes * 60


async def test_failures_in_same_clock_tick_are_counted(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234567890.0)
    async with Redis.from_url(os.environ["REDIS_URL"]) as redis:
        limiter = LoginRateLimiter(redis, get_settings())
        assert [await limiter.record_failure("same-tick@example.com") for _ in range(3)] == [1, 2, 3]


async def test_sliding_session_refresh_uses_remaining_ttl(client, db_session):
    login = await sign_in(client, db_session)
    settings = get_settings()
    token = login.cookies["hcc_session"]
    row = await db_session.scalar(select(UserSession).where(
        UserSession.token_hash == hash_session_token(token, settings.session_secret),
    ))
    row.created_at = datetime.now(UTC) - timedelta(days=2)
    row.expires_at = datetime.now(UTC) + timedelta(minutes=1)
    await db_session.commit()
    resolved = await resolve_session(db_session, token)
    refreshed_expiry = resolved[1].expires_at
    assert refreshed_expiry > datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes - 1)
    assert (await resolve_session(db_session, token))[1].expires_at == refreshed_expiry
    response = await client.get("/me")
    assert "Max-Age=" in response.headers["set-cookie"]


async def test_unicode_csrf_and_logout_csrf_rejected(client, db_session):
    await sign_in(client, db_session)
    assert (await client.post("/auth/logout")).status_code == 403
    response = await client.put("/me", json={"theme": "dark"}, headers={"X-CSRF-Token": "é".encode()})
    assert response.status_code == 403
    response = await client.post("/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 204
    assert not client.cookies.get("csrf_token")
