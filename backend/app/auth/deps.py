"""FastAPI auth dependencies (session cookie -> authenticated principal)."""

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import resolve_session, session_cookie_name
from app.core.db import get_session
from app.models.user import User, UserSession

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


async def get_current_session(
    request: Request,
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
    return resolved


async def get_current_user(
    resolved: tuple[User, UserSession] = Depends(get_current_session),
) -> User:
    """The authenticated principal for handlers that don't touch the session row."""
    return resolved[0]
