"""CSRF middleware (MASTER_SPEC §22.3) + reverse-proxy header handling (§15).

CSRF: state-changing requests require a custom header (`X-CSRF-Token`) that
cross-origin requests cannot attach without triggering a CORS preflight.
Only /health is exempt, matching §17's reachable-without-session rule
(GET /health is safe anyway — the exemption is belt-and-braces).

ProxyHeadersMiddleware: for the Tailscale Funnel / Caddy deployment (§15,
infra/tailscale-funnel-setup.md) the TLS terminator forwards the request to
the app over plain HTTP and records the real scheme/client in
X-Forwarded-*. When TRUST_PROXY_HEADERS=true the app adopts those values —
but only from loopback connections (the funnel/serve proxy runs on the same
host), so a random client cannot lie to us about its own address.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

CSRF_HEADER = "X-CSRF-Token"
_EXEMPT_PATHS = {"/health"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in _EXEMPT_PATHS:
            if not request.headers.get(CSRF_HEADER):
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Missing required header: {CSRF_HEADER}"},
                )
        return await call_next(request)


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
