"""Watch endpoints (MASTER_SPEC §23 Phase 10).

Token management (session-authed, each user mints their own):
  POST   /watch/tokens        -> the plaintext token is returned ONCE
  GET    /watch/tokens        -> own tokens with mint/last-used/revoked state
  DELETE /watch/tokens/{id}   -> soft-revoke one of MY tokens

Data endpoint (Bearer-token authed — cookie auth is impossible on a Connect
IQ device; makeWebRequest carries the token in the Authorization header):
  GET    /watch/today         -> {readiness, recovery, strain, as_of date,
                                  data completeness} for the TOKEN OWNER.

Isolation is structural: the token resolves to exactly one user, and the
daily_features row is fetched by that user's id and that user's LOCAL date
(§17 day-boundary rule) — a friend's watch can only ever see the friend's
numbers, there is no parameter to do otherwise.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_session
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import hash_session_token, new_session_token
from app.models.features import DailyFeature
from app.models.user import User, UserSession
from app.models.watch import DeviceToken

router = APIRouter(prefix="/watch", tags=["watch"])


# ---------------------------------------------------------------- token auth


async def get_watch_principal(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, DeviceToken]:
    """Bearer-token principal for watch requests (§22 security posture:
    peppered hash lookup, revocation respected, last_used stamped)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()
    hashed = hash_session_token(raw, get_settings().session_secret)

    token = await session.scalar(
        select(DeviceToken).where(DeviceToken.token_hash == hashed)
    )
    if token is None or token.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token")

    user = await session.get(User, token.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token")

    await session.execute(
        update(DeviceToken)
        .where(DeviceToken.id == token.id)
        .values(last_used_at=datetime.now(UTC))
    )
    await session.commit()
    return user, token


# ------------------------------------------------------------ token mgmt API


class TokenCreateRequest(BaseModel):
    name: str = Field(default="watch", min_length=1, max_length=60)


class TokenCreated(BaseModel):
    id: int
    name: str
    token: str  # plaintext — shown exactly once, like the invite code
    created_at: datetime


class TokenOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


@router.post("/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def mint_token(
    payload: TokenCreateRequest | None = None,
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session),
) -> TokenCreated:
    body = payload or TokenCreateRequest()
    raw = new_session_token()  # same 256-bit entropy, same peppered hashing
    token = DeviceToken(
        user_id=principal[0].id,
        name=body.name,
        token_hash=hash_session_token(raw, get_settings().session_secret),
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return TokenCreated(
        id=token.id, name=token.name, token=raw, created_at=token.created_at
    )


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session),
) -> list[TokenOut]:
    rows = (
        await session.scalars(
            select(DeviceToken)
            .where(DeviceToken.user_id == principal[0].id)
            .order_by(DeviceToken.created_at.desc(), DeviceToken.id.desc())
        )
    ).all()
    return [
        TokenOut(
            id=t.id, name=t.name, created_at=t.created_at,
            last_used_at=t.last_used_at, revoked_at=t.revoked_at,
        )
        for t in rows
    ]


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: int,
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session),
) -> None:
    token = await session.get(DeviceToken, token_id)
    if token is None or token.user_id != principal[0].id:
        # 404 denies existence across users (same convention as every
        # user-scoped row in this API).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await session.commit()


# ----------------------------------------------------------------- data API


class WatchToday(BaseModel):
    user_id: int
    as_of_date: str  # the LOCAL date the scores belong to (§17)
    readiness: float | None
    recovery: float | None
    strain: float | None
    data_completeness: str | None
    stale: bool  # true when as_of_date is not today (honest UI on the wrist)


@router.get("/today", response_model=WatchToday)
async def today(
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, DeviceToken] = Depends(get_watch_principal),
) -> WatchToday:
    user, _token = principal
    local_today = datetime.now(ZoneInfo(user.timezone)).date()

    row = await session.get(DailyFeature, {"user_id": user.id, "date": local_today})
    stale = False
    if row is None:
        # Today hasn't been scored yet (nightly engine runs 03:00 user-local,
        # §19) — serve the most recent scored day and say so via stale=true.
        row = await session.scalar(
            select(DailyFeature)
            .where(DailyFeature.user_id == user.id)
            .order_by(DailyFeature.date.desc())
            .limit(1)
        )
        stale = True
    if row is None:
        # No scored day exists at all — the glance renders dashes, not zeros.
        return WatchToday(
            user_id=user.id, as_of_date=local_today.isoformat(),
            readiness=None, recovery=None, strain=None,
            data_completeness=None, stale=True,
        )

    return WatchToday(
        user_id=user.id,
        as_of_date=row.date.isoformat(),
        readiness=float(row.readiness_score) if row.readiness_score is not None else None,
        recovery=float(row.recovery_score) if row.recovery_score is not None else None,
        strain=float(row.strain_score) if row.strain_score is not None else None,
        data_completeness=row.data_completeness,
        stale=stale,
    )
