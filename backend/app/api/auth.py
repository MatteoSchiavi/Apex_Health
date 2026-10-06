"""Auth endpoints (MASTER_SPEC §18): /auth/login, /auth/logout.

§17: these routes are reachable without a session; state-changing requests
still require the CSRF header (§22.3).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CREDENTIALS_EXCEPTION, get_current_session
from app.auth.invites import InviteError, redeem_invite
from app.auth.service import (
    AuthError,
    authenticate,
    create_session,
    destroy_session,
    remembered_session_max_age_seconds,
    session_cookie_name,
)
from app.core.config import get_settings
from app.core.db import get_session
from app.core.middleware import mint_csrf_token, set_csrf_cookie
from app.core.redis import get_redis_dependency
from app.models.user import User, UserSession
from app.schemas.auth import LoginRequest, LoginResponse, RedeemInviteRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> LoginResponse:
    email = payload.email.lower()
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
    except RedisError:
        raise HTTPException(503, "Authentication temporarily unavailable; try again shortly.") from None

    user = await session.get(User, cred.user_id)
    assert user is not None  # FK guarantees existence
    token, _ = await create_session(session, user.id, remember_me=payload.remember_me)

    settings = get_settings()
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        **(
            {"max_age": remembered_session_max_age_seconds()}
            if payload.remember_me
            else {}
        ),
        secure=settings.cookie_secure,  # §22.2 — TLS paths default; LAN-HTTP opts out via COOKIE_SECURE=false
        httponly=True,
        samesite="lax",
        path="/",
    )
    set_csrf_cookie(
        response,
        mint_csrf_token(token),
        secure=settings.cookie_secure,
        max_age=(remembered_session_max_age_seconds() if payload.remember_me else None),
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
    response.delete_cookie(key="csrf_token", path="/")


@router.post("/invite/redeem", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def redeem(
    payload: RedeemInviteRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """§18 /auth/invite/redeem — one POST turns a live invite code into a
    friend account AND a session (no separate login step: the person just
    chose the password, asking them to type it again is friction without
    security value). Bootstrap/auth route per §17, CSRF header still
    required (state-changing, §22.3)."""
    try:
        user, cred, _invite = await redeem_invite(
            session,
            code=payload.code.strip(),
            name=payload.name,
            email=payload.email,
            password=payload.password,
            locale=payload.locale,
            theme=payload.theme,
        )
    except InviteError as exc:
        if exc.kind == "email_taken":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That email is already registered — log in instead",
            ) from exc
        # Uniform rejection for invalid / used / expired: one message, no
        # oracle for which codes exist.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invite code is not valid (unknown, already used, or expired)",
        ) from exc

    token, _ = await create_session(session, user.id)
    settings = get_settings()
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    set_csrf_cookie(
        response,
        mint_csrf_token(token),
        secure=settings.cookie_secure,
        max_age=None,
    )
    return LoginResponse(
        user_id=user.id,
        email=cred.email,
        role=cred.role,
        ai_access_tier=cred.ai_access_tier,
    )
