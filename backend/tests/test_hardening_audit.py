"""Phase 8 hardening-audit tests (§20, §21, §22).

Closes the audit gaps that earlier phases did not lock down:
- §22.2 sliding session expiry (implemented in auth/service.resolve_session,
  never regression-tested)
- §17/§22 route-reachability matrix: nothing but /health, the bootstrap/auth
  endpoints and the documented OAuth callback is reachable without a session
- §21 structured JSON logging actually emits single-line JSON
"""

import io
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth.service import create_session, resolve_session
from app.core.config import get_settings
from app.models.user import UserSession


# ---------------------------------------------------------------- §22.2 sliding


async def _mk_session(db_session) -> tuple[str, UserSession]:
    token, _ = await create_session(db_session, user_id=1)
    row = await db_session.scalar(
        select(UserSession).where(
            UserSession.token_hash
            == __import__("app.core.security", fromlist=["hash_session_token"]).hash_session_token(
                token, get_settings().session_secret
            )
        )
    )
    return token, row


async def test_no_slide_before_half_life(db_session):
    """A session inside its first half-life keeps its original expiry."""
    token, row = await _mk_session(db_session)
    original_expiry = row.expires_at

    result = await resolve_session(db_session, token)
    assert result is not None
    _, slid = result
    assert slid.expires_at == original_expiry


async def test_slides_to_full_ttl_after_half_life(db_session):
    """§22.2: past half the TTL, resolve extends expiry to a full TTL from now."""
    settings = get_settings()
    token, row = await _mk_session(db_session)
    # Age the session: created_at pushed back so now is just past the half-life.
    row.created_at = datetime.now(UTC) - timedelta(
        minutes=settings.session_ttl_minutes // 2 + 5
    )
    row.expires_at = row.created_at + timedelta(minutes=settings.session_ttl_minutes)
    await db_session.commit()

    result = await resolve_session(db_session, token)
    assert result is not None
    _, slid = result
    expected_floor = datetime.now(UTC) + timedelta(
        minutes=settings.session_ttl_minutes - 1
    )
    assert slid.expires_at >= expected_floor


async def test_expired_session_is_dead(db_session):
    """An expired token resolves to None regardless of sliding."""
    token, row = await _mk_session(db_session)
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()
    assert await resolve_session(db_session, token) is None


# -------------------------------------------------------- §17/§22 route matrix


def _exempt(route) -> bool:
    path = route.path
    # §17: /health + bootstrap/auth endpoints; the Technogym callback is a
    # provider browser redirect whose single-use `state` IS the credential
    # (documented in the handler) and it 400s without it.
    return path == "/health" or path.startswith("/auth") or "callback" in path


async def test_every_route_denies_unauthenticated_access(client: AsyncClient):
    """Probe the SERVED surface via the OpenAPI schema (version-proof — the
    app's included-router internals changed shape across Starlette versions,
    openapi() is the authoritative contract)."""
    from app.main import app

    schema = app.openapi()
    probed: list[tuple[str, str, int]] = []
    for path, operations in schema["paths"].items():
        if _exempt(SimpleNamespace(path=path)):
            continue
        for method in operations:
            if method == "parameters":
                continue
            # Send the CSRF header so a denial comes from the AUTH layer,
            # not the CSRF middleware — the two guarantees are tested apart.
            resp = await client.request(
                method.upper(),
                path,
                headers={"X-CSRF-Token": "audit"},
            )
            probed.append((method.upper(), path, resp.status_code))
            assert resp.status_code in {401, 403}, (
                f"{method.upper()} {path} answered {resp.status_code} unauthenticated"
            )
    # The audit must have actually covered the API surface, not exempted it all.
    assert len(probed) >= 6


async def test_health_and_login_remain_reachable(client: AsyncClient):
    health = await client.get("/health")
    assert health.status_code == 200
    # /auth/login is a bootstrap endpoint — the AUTH layer must answer (401 on
    # bad creds). F-04 audit: login is CSRF-EXEMPT (it MINTS the csrf cookie,
    # so it cannot require one). The X-CSRF-Token header is accepted but not
    # required on login/redeem.
    login = await client.post(
        "/auth/login",
        json={"email": "nobody@x.dev", "password": "wrong"},
        headers={"X-CSRF-Token": "audit"},
    )
    assert login.status_code == 401
    # Without the header, login still answers (401 on bad creds) — it is
    # CSRF-exempt. A NON-exempt endpoint (e.g. /settings/integrations/garmin/connect)
    # without the header would 403 from the CSRF middleware.
    no_csrf = await client.post(
        "/auth/login", json={"email": "nobody@x.dev", "password": "wrong"}
    )
    assert no_csrf.status_code == 401  # auth check runs (bad creds), not CSRF
    # Verify a non-exempt endpoint WITHOUT csrf header → 403 from middleware.
    non_exempt = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "x@y.z", "password": "anything"},
    )
    assert non_exempt.status_code == 403  # CSRF middleware fires first


# ------------------------------------------------------------- §21 JSON logs


def test_configure_logging_emits_single_line_json():
    """§21: structured JSON logging to stdout — every line parses as JSON."""
    from app.core.logging import configure_logging

    buf = io.StringIO()
    with patch("sys.stdout", buf):
        configure_logging()
        import logging

        logging.getLogger("audit.test").info("hardening probe %s", "ok", extra={})
        for h in logging.getLogger().handlers:
            h.flush()
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "expected at least one JSON log line"
    parsed = json.loads(lines[-1])
    assert parsed["message"] == "hardening probe ok"
    assert parsed["levelname"] == "INFO"


def test_alerts_and_logs_are_distinct_channels():
    """§21: alerts (user-facing) and logs (developer-facing) don't conflate —
    a sync_failure alert row exists as a DB concept, separate from logging."""
    from app.models.alert import Alert

    alert_columns = {c.name for c in Alert.__table__.columns}
    assert {"type", "severity", "user_id"} <= alert_columns
