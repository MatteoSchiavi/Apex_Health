"""CSRF middleware (MASTER_SPEC §22.3).

State-changing requests require a custom header (`X-CSRF-Token`) that
cross-origin requests cannot attach without triggering a CORS preflight.
Only /health is exempt, matching §17's reachable-without-session rule
(GET /health is safe anyway — the exemption is belt-and-braces).
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
