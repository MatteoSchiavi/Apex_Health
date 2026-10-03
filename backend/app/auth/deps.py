"""FastAPI auth dependencies (session cookie -> authenticated principal)."""

from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import resolve_session, session_cookie_name
from app.core.config import get_settings
from app.core.middleware import mint_csrf_token, set_csrf_cookie, valid_csrf_token
from app.core.db import get_session
from app.models.user import AuthCredential, User, UserSession

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


async def get_current_session(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    hcc_session: str | None = Cookie(default=None, alias=session_cookie_name()),
) -> tuple[User, UserSession]:
    if not hcc_session:
        raise CREDENTIALS_EXCEPTION
    resolved = await resolve_session(session, hcc_session)
    if resolved is None:
        raise CREDENTIALS_EXCEPTION
    # Bind the raw token for handlers that need to destroy the session.
    request.state.session_token = hcc_session
    settings = get_settings()
    # Renew the browser cookie alongside the server's sliding expiry, without
    # ever extending it beyond the row's absolute lifetime.
    response.set_cookie(
        session_cookie_name(), hcc_session,
        max_age=max(0, int((resolved[1].expires_at - datetime.now(UTC)).total_seconds())),
        secure=settings.cookie_secure, httponly=True, samesite="lax", path="/",
    )
    # A safe authenticated read repairs cookies from older deployments.
    if not valid_csrf_token(request.cookies.get("csrf_token", ""), hcc_session):
        set_csrf_cookie(response, mint_csrf_token(hcc_session), secure=settings.cookie_secure)
    return resolved


async def get_current_user(
    resolved: tuple[User, UserSession] = Depends(get_current_session),
) -> User:
    """The authenticated principal for handlers that don't touch the session row."""
    return resolved[0]


async def get_current_credential(
    resolved: tuple[User, UserSession] = Depends(get_current_session),
    session: AsyncSession = Depends(get_session),
) -> AuthCredential:
    """The auth_credential row for the authenticated principal (role lives here)."""
    user = resolved[0]
    cred = await session.get(AuthCredential, user.id)
    if cred is None:
        raise CREDENTIALS_EXCEPTION
    return cred


async def require_owner(
    cred: AuthCredential = Depends(get_current_credential),
) -> AuthCredential:
    """Owner-only gate (§18 Settings): friends get 403, not 404 — the route
    exists and their account is authenticated; the privilege just isn't theirs."""
    if cred.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return cred
