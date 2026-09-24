"""Auth endpoints (MASTER_SPEC §18): /auth/login, /auth/logout.

§17: these routes are reachable without a session; state-changing requests
still require the CSRF header (§22.3).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CREDENTIALS_EXCEPTION, get_current_session
from app.auth.invites import InviteError, redeem_invite
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
from app.core.middleware import mint_csrf_token, set_csrf_cookie
from app.core.redis import get_redis
from app.models.user import AuthCredential, User, UserSession
from app.schemas.auth import LoginRequest, LoginResponse, RedeemInviteRequest

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
        secure=settings.cookie_secure,  # §22.2 — TLS paths default; LAN-HTTP opts out via COOKIE_SECURE=false
        httponly=True,
        samesite="lax",
        path="/",
    )
    # F-04 audit: mint a CSRF double-submit token and set it as a non-HttpOnly
    # cookie. The SPA reads this cookie and mirrors the value in the
    # X-CSRF-Token header on every unsafe method; the middleware verifies
    # the two match with hmac.compare_digest.
    csrf_token = mint_csrf_token()
    set_csrf_cookie(response, csrf_token, secure=settings.cookie_secure)
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


@router.post("/invite/redeem", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def redeem(
    payload: RedeemInviteRequest,
    response: Response,
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
        max_age=cookie_max_age_seconds(),
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    # F-04 audit: CSRF double-submit token (same path as login).
    csrf_token = mint_csrf_token()
    set_csrf_cookie(response, csrf_token, secure=settings.cookie_secure)
    return LoginResponse(
        user_id=user.id,
        email=cred.email,
        role=cred.role,
        ai_access_tier=cred.ai_access_tier,
    )
