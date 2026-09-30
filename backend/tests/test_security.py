"""Security hardening tests (MASTER_SPEC §22.1 login rate limiting, §22.3 CSRF)."""

import os

from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import reset_owner_auth_state

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


async def test_state_change_without_csrf_header_rejected(client: AsyncClient):
    """§22.3 + F-04 audit: state-changing requests require a matching
    X-CSRF-Token header + csrf_token cookie (double-submit).

    Login/redeem are exempt (they MINT the cookie). All OTHER state-changing
    endpoints — e.g. /settings/integrations/garmin/connect — require the
    header+cookie pair. This test targets a non-exempt endpoint without the
    header and asserts the 403.
    """
    # /settings/integrations/garmin/connect requires a session + CSRF.
    # Without the CSRF header (and without a session), the CSRF middleware
    # fires first and returns 403.
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "x@y.z", "password": "anything"},
        # No X-CSRF-Token header → middleware 403s before the route runs.
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"] or "csrf" in resp.json()["detail"].lower()


async def test_csrf_mismatch_rejected(client: AsyncClient):
    """F-04 audit: a header value that doesn't match the cookie is rejected."""
    # The conftest pre-sets csrf_token=test. Send a DIFFERENT header value.
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "x@y.z", "password": "anything"},
        headers={"X-CSRF-Token": "wrong-value"},
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"] or "csrf" in resp.json()["detail"].lower()


async def test_csrf_match_accepted_past_middleware(client: AsyncClient):
    """F-04 audit: when header == cookie, the request passes the middleware
    (it may still 401 from missing session, but NOT 403 from CSRF)."""
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "x@y.z", "password": "anything"},
        headers={"X-CSRF-Token": "test"},  # matches the conftest cookie
    )
    # 401 (no session) or 400 (bad creds) — NOT 403 (CSRF passed).
    assert resp.status_code != 403


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
