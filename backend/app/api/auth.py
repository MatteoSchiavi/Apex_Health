"""Auth endpoints (MASTER_SPEC §18): /auth/login, /auth/logout.

§17: these routes are reachable without a session; state-changing requests
still require the CSRF header (§22.3).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CREDENTIALS_EXCEPTION, get_current_session
from app.auth.service import (
    AuthError,
    authenticate,
    cookie_max_age_seconds,
    create_session,
    destroy_session,
    get_auth_credential,
    session_cookie_name,
)
from app.core.config import get_settings
from app.core.db import get_session
from app.core.redis import get_redis
from app.models.user import AuthCredential, User, UserSession
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> LoginResponse:
    email = payload.email.lower()
    cred: AuthCredential | None = await get_auth_credential(session, email)
    if cred is None:
        # Uniform 401 for unknown emails: no account-existence oracle.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    try:
        cred = await authenticate(session, redis, email, payload.password)
    except AuthError as exc:
        if exc.kind == "locked":
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many failed attempts; account temporarily locked",
            ) from exc
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid email or password"
        ) from exc

    user = await session.get(User, cred.user_id)
    assert user is not None  # FK guarantees existence
    token, _ = await create_session(session, user.id)

    settings = get_settings()
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=cookie_max_age_seconds(),
        secure=True,  # §22.2 — unconditional; clients reach the API over TLS or localhost tooling
        httponly=True,
        samesite="lax",
        path="/",
    )
    return LoginResponse(
        user_id=user.id,
        email=cred.email,
        role=cred.role,
        ai_access_tier=cred.ai_access_tier,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session),
) -> None:
    token = getattr(request.state, "session_token", None)
    if token is None:
        raise CREDENTIALS_EXCEPTION
    await destroy_session(session, token)
    response.delete_cookie(key=session_cookie_name(), path="/")
