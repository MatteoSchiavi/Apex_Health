"""Session-bound signed double-submit CSRF and trusted proxy handling.

Login and invite redemption mint a new CSRF cookie. Bootstrap requests and
all other writes reject browser cross-origin requests. Authenticated writes
also require a matching signed token bound to the current session cookie.
"""
import hashlib
import hmac
import secrets
import base64
from pathlib import Path
import os
import re
from urllib.parse import urlsplit

from app.core.config import get_settings

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"
_EXEMPT_PATHS = {"/auth/login", "/auth/invite/redeem"}


def _signature(nonce: str, session_token: str) -> str:
    message = f"{session_token}:{nonce}".encode()
    return hmac.new(get_settings().session_secret.encode(), message, hashlib.sha256).hexdigest()


def mint_csrf_token(session_token: str = "") -> str:
    nonce = secrets.token_urlsafe(32)
    return f"{nonce}.{_signature(nonce, session_token)}"


def valid_csrf_token(token: str, session_token: str) -> bool:
    try:
        nonce, signature = token.split(".")
        return len(nonce) == 43 and hmac.compare_digest(
            signature.encode(), _signature(nonce, session_token).encode()
        )
    except (ValueError, UnicodeError):
        return False


def _same_origin(request: Request) -> bool:
    # Non-browser API clients may omit Origin; browsers' explicit cross-site
    # metadata must never bypass the check, including bootstrap endpoints.
    if request.headers.get("sec-fetch-site") == "cross-site":
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
        expected = request.url
        return (
            parsed.scheme in {"http", "https"}
            and parsed.scheme == expected.scheme
            and parsed.hostname == expected.hostname
            and (parsed.port or (443 if parsed.scheme == "https" else 80))
            == (expected.port or (443 if expected.scheme == "https" else 80))
            and not parsed.username and not parsed.password
            and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
        )
    except ValueError:
        return False


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        if not _same_origin(request):
            return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected."})
        # Native routes authenticate a separate scoped capability. Browser sessions
        # cannot use this exemption, and no other write route accepts bearer auth.
        if request.url.path in {"/healthkit/exchange", "/healthkit/deltas"}:
            if request.cookies.get("hcc_session"):
                return JSONResponse(status_code=403, content={"detail": "Native device authentication required."})
            limit = 2 * 1024 * 1024
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > limit:
                    return JSONResponse(status_code=413, content={"detail": "HealthKit batch too large."})
            request._body = bytes(body)
            return await call_next(request)
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        header = request.headers.get(CSRF_HEADER, "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        session_token = request.cookies.get("hcc_session", "")
        if not header or not cookie or not hmac.compare_digest(
            header.encode(), cookie.encode()
        ) or not valid_csrf_token(cookie, session_token):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch — refresh the page and retry."},
            )
        return await call_next(request)


def set_csrf_cookie(
    response: Response,
    token: str,
    *,
    secure: bool = True,
    max_age: int | None = 30 * 24 * 3600,
) -> None:
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
        max_age=max_age,
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

    def __init__(self, app, trusted: bool = False, trusted_ips: str = "127.0.0.1,::1"):
        super().__init__(app)
        self._trusted = trusted
        self._trusted_ips = {ip.strip() for ip in trusted_ips.split(",") if ip.strip()}

    async def dispatch(self, request: Request, call_next):
        if self._trusted:
            client = request.client
            peer_is_local = client is not None and client.host in self._trusted_ips
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


class SecurityHeadersMiddleware:
    """Security headers for the single API/SPA server, including errors.

    Hash the shipped first-paint script instead of allowing arbitrary inline
    scripts. HSTS is emitted only on HTTPS (after trusted proxy resolution).
    """

    def __init__(self, app):
        self.app = app
        repo = Path(__file__).resolve().parents[3]
        dist = Path(os.environ.get("SPA_DIST_DIR") or repo / "frontend" / "dist")
        hashes = set()
        for path in (dist / "index.html", repo / "frontend" / "index.html"):
            if path.is_file():
                for attrs, script in re.findall(r"<script\b([^>]*)>(.*?)</script>", path.read_text(), re.S):
                    if not re.search(r"\bsrc\s*=", attrs) and script.strip():
                        hashes.add("'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'")
        self.csp = (
            "default-src 'self'; script-src 'self' " + " ".join(sorted(hashes)) + "; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "font-src 'self' data:; connect-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def with_headers(message):
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders
                headers = MutableHeaders(scope=message)
                headers["X-Frame-Options"] = "DENY"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Content-Security-Policy"] = self.csp
                headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=(self)"
                if scope.get("scheme") == "https":
                    headers["Strict-Transport-Security"] = "max-age=31536000"
                if (
                    "application/json" in headers.get("content-type", "")
                    or scope.get("path", "").startswith((
                        "/api/", "/app", "/admin", "/me", "/auth", "/coach",
                        "/lab", "/dashboard", "/activities", "/metrics", "/sleep",
                        "/settings", "/imports", "/integrations", "/gym", "/events",
                        "/schedule", "/gear", "/watch", "/challenges", "/leaderboard",
                    ))
                ):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, with_headers)
