"""Security hardening tests (MASTER_SPEC §22.1 login rate limiting, §22.3 CSRF)."""

import os

from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import reset_owner_auth_state

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


async def test_state_change_without_csrf_header_rejected(client: AsyncClient):
    """§22.3: state-changing requests require a custom header."""
    resp = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert resp.status_code == 403
    assert "X-CSRF-Token" in resp.json()["detail"]


async def test_unknown_email_is_uniform_401(client: AsyncClient):
    """No account-existence oracle: unknown email == wrong password == 401."""
    resp = await client.post(
        "/auth/login",
        json={"email": "nobody@apexhealth.dev", "password": "whatever"},
        headers=CSRF,
    )
    assert resp.status_code == 401


async def test_lockout_after_five_failures(client: AsyncClient, db_session):
    """§22.1: 5 failed attempts per email per 15 min -> temporary lockout;
    even the CORRECT password is rejected while locked (429)."""
    await reset_owner_auth_state(db_session)

    for i in range(1, 6):
        resp = await client.post(
            "/auth/login",
            json={"email": OWNER_EMAIL, "password": f"wrong-{i}"},
            headers=CSRF,
        )
        assert resp.status_code == 401, f"attempt {i}"

    row = await db_session.execute(
        text(
            "SELECT failed_login_count, locked_until FROM auth_credentials "
            "WHERE email = :email"
        ),
        {"email": OWNER_EMAIL},
    )
    failed_count, locked_until = row.fetchone()
    assert failed_count == 5
    assert locked_until is not None

    locked = await client.post(
        "/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        headers=CSRF,
    )
    assert locked.status_code == 429


async def test_successful_login_resets_counters(client: AsyncClient, db_session):
    await reset_owner_auth_state(db_session)
    await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": "wrong"}, headers=CSRF
    )
    ok = await client.post(
        "/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        headers=CSRF,
    )
    assert ok.status_code == 200

    row = await db_session.execute(
        text(
            "SELECT failed_login_count, locked_until FROM auth_credentials "
            "WHERE email = :email"
        ),
        {"email": OWNER_EMAIL},
    )
    failed_count, locked_until = row.fetchone()
    assert failed_count == 0
    assert locked_until is None
