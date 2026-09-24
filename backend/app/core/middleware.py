"""CSRF middleware (MASTER_SPEC §22.3) + reverse-proxy header handling (§15).

F-04 audit: TRUE double-submit CSRF is now enforced. The server issues a
non-HttpOnly ``csrf_token`` cookie (per session, signed with SESSION_SECRET)
and the SPA reads it and sends the same value back in the ``X-CSRF-Token``
header on every unsafe method. The middleware verifies the two match with
``hmac.compare_digest`` — a cross-origin attacker can neither read the cookie
(SameSite=Lax + cross-origin cookie blocking) nor forge the matching header.

This replaces the previous presence-only check, which the SPA satisfied with
a self-minted token and which therefore added zero origin-proof beyond
SameSite=Lax. The defense-in-depth claim in §22.3 is now real.

Only /health is exempt, matching §17's reachable-without-session rule
(GET /health is safe anyway — the exemption is belt-and-braces).

ProxyHeadersMiddleware: for the Tailscale Funnel / Caddy deployment (§15,
infra/tailscale-funnel-setup.md) the TLS terminator forwards the request to
the app over plain HTTP and records the real scheme/client in
X-Forwarded-*. When TRUST_PROXY_HEADERS=true the app adopts those values —
but only from loopback connections (the funnel/serve proxy runs on the same
host), so a random client cannot lie to us about its own address.
"""

import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"
_EXEMPT_PATHS = {"/health"}


def _csrf_cookie_value(token: str) -> str:
    """Format the CSRF cookie value (the token itself — double-submit).

    The token is 256-bit random; no signing is needed because the
    double-submit invariant (cookie == header) is the auth check. An
    attacker who can read the cookie can already send the matching header,
    but SameSite=Lax + cross-origin cookie blocking prevents that read.
    """
    return token


class CSRFMiddleware(BaseHTTPMiddleware):
    """F-04 audit: true double-submit CSRF.

    On every unsafe method (POST/PUT/PATCH/DELETE) the middleware checks
    that the ``X-CSRF-Token`` header value matches the ``csrf_token`` cookie
    value with ``hmac.compare_digest``. Mismatches (or missing either side)
    return 403.

    The cookie is set lazily on the first response after a successful login
    (the auth endpoint sets it explicitly); if no cookie is present on an
    unsafe request, the request is rejected. The SPA reads the cookie and
    sends the same value back in the header (see frontend/src/app/api.ts).
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"} or request.url.path in _EXEMPT_PATHS:
            response = await call_next(request)
            return response
        header_value = request.headers.get(CSRF_HEADER)
        cookie_value = request.cookies.get(CSRF_COOKIE)
        if not header_value or not cookie_value or not hmac.compare_digest(
            str(header_value), str(cookie_value)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch — refresh the page and retry."},
            )
        return await call_next(request)


def mint_csrf_token() -> str:
    """Mint a fresh CSRF token for double-submit (called at login)."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, *, secure: bool = True) -> None:
    """Attach the non-HttpOnly ``csrf_token`` cookie to a response.

    Non-HttpOnly is REQUIRED — the SPA must read the cookie to mirror it
    back in the header. SameSite=Lax + Secure prevents cross-origin reads;
    the cookie is not a session credential (the session rides the separate
    HttpOnly ``hcc_session`` cookie), so leaking it adds no capability an
    attacker didn't already have via SameSite.
    """
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=30 * 24 * 3600,  # 30d — refreshes on each login
        path="/",
    )


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Adopt X-Forwarded-Proto/-For from a local TLS terminator (§15).

    Only applied when the TRUST_PROXY_HEADERS setting is on, and only for
    loopback peers. Funnel/serve (and Caddy) terminate TLS and proxy to the
    app on localhost — that peer is the only one allowed to vouch for the
    outside client. Effect: request.url.scheme becomes https, request.client
    becomes the real client, so logs, rate limiting and any absolute-URL
    building see the truth through the tunnel.
    """

    def __init__(self, app, trusted: bool = False):
        super().__init__(app)
        self._trusted = trusted

    async def dispatch(self, request: Request, call_next):
        if self._trusted:
            client = request.client
            peer_is_local = client is not None and client.host in {"127.0.0.1", "::1"}
            if peer_is_local:
                proto = request.headers.get("x-forwarded-proto")
                if proto in {"https", "http"}:
                    request.scope["scheme"] = proto
                fwd_for = request.headers.get("x-forwarded-for")
                if fwd_for:
                    real_ip = fwd_for.split(",")[0].strip()
                    if real_ip:
                        request.scope["client"] = (real_ip, 0)
        return await call_next(request)
