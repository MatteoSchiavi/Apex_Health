"""Watch endpoints (MASTER_SPEC §23 Phase 10).

Token management (session-authed, each user mints their own):
  POST   /watch/tokens        -> the plaintext token is returned ONCE
  GET    /watch/tokens        -> own tokens with mint/last-used/revoked state
  DELETE /watch/tokens/{id}   -> soft-revoke one of MY tokens

Data endpoints (Bearer-token authed — cookie auth is impossible on a Connect
IQ device; makeWebRequest carries the token in the Authorization header):
  GET    /watch/today         -> {readiness, recovery, strain, as_of date,
                                  data completeness} for the TOKEN OWNER.
  GET    /watch/day  (v2)     -> the Apex-only day: gym sessions (recurring
                                  schedule, overridden by date-specific
                                  planned sessions), active supplements, open
                                  alerts, journal streak. This is the payload
                                  the rethought app actually shows — the old
                                  scores stay available but are NOT what the
                                  glance duplicates (Garmin already shows
                                  Training Readiness / Recovery / Body Battery
                                  natively).
  GET    /watch/week (v2)     -> 7 resolved days for the week view.

Isolation is structural: the token resolves to exactly one user, and the
daily_features row is fetched by that user's id and that user's LOCAL date
(§17 day-boundary rule) — a friend's watch can only ever see the friend's
numbers, there is no parameter to do otherwise.
"""

from datetime import UTC, datetime, timedelta
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
from app.queries import (
    active_supplements,
    journal_streak,
    open_alert_summaries,
    resolve_day,
    resolve_range,
)
from app.queries.gym_detail import plan_for_date, session_view
from app.services.safety_interlock import safety_block

router = APIRouter(prefix="/watch", tags=["watch"])


# ---------------------------------------------------------------- token auth


async def get_watch_principal(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, DeviceToken]:
    """Bearer-token principal for watch requests (§22 security posture:
    peppered hash lookup, revocation respected, last_used stamped).

    F-19 audit: throttles ``last_used`` writes to one per hour per token
    (write amplification was hitting the DB on every 30-min watch poll), and
    rejects tokens past their ``absolute_expires_at`` regardless of activity."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()
    hashed = hash_session_token(raw, get_settings().session_secret)

    token = await session.scalar(
        select(DeviceToken).where(DeviceToken.token_hash == hashed)
    )
    now = datetime.now(UTC)
    # F-19: revocation OR absolute expiry → reject.
    if token is None or token.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token")
    if token.absolute_expires_at is not None and token.absolute_expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")

    user = await session.get(User, token.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token")

    # F-19: throttle last_used writes — only stamp when the previous stamp is
    # older than an hour. A 30-min watch poll cadence no longer writes a row
    # every tick; the index on (user_id, revoked_at) keeps the lookup cheap.
    if token.last_used_at is None or (now - token.last_used_at).total_seconds() >= 3600:
        await session.execute(
            update(DeviceToken)
            .where(DeviceToken.id == token.id)
            .values(last_used_at=now)
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
    # F-19 audit: 365-day absolute expiry baked in at mint time. The watch
    # auth path rejects tokens past this column regardless of activity.
    now = datetime.now(UTC)
    token = DeviceToken(
        user_id=principal[0].id,
        name=body.name,
        token_hash=hash_session_token(raw, get_settings().session_secret),
        absolute_expires_at=now + timedelta(days=365),
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


# ------------------------------------------------------- v2: Apex-only payload


def _compact_session(entry: dict) -> dict:
    """Radio-friendly session dict for the wrist (short keys, no nulls)."""
    out = {
        "title": entry["title"],
        "source": entry["source"],  # schedule | plan
        "start": entry["start_time"],  # null for plan sessions (date-anchored)
        "duration": entry["target_duration_min"],
    }
    description = entry.get("description")
    if description:
        out["notes"] = description[:800]  # exercises block; truncation is honest
    return out


class WatchDay(BaseModel):
    date: str
    weekday: int  # 0=Mon .. 6=Sun (watch renders its own names)
    sessions: list[dict]
    supplements: list[dict]
    alerts: dict
    journal_streak: int
    # Concrete gym day plan (owner feature batch): exercises with sets/reps
    # + rest so the watch window doubles as the in-gym tracker.
    gym_plan: dict | None = None
    # W-02 audit: machine-readable safety interlock — verdict ∈ {go, modify,
    # rest} + intensity_ceiling + reasons. The watch renders a banner when
    # the verdict is modify/rest so the athlete sees the veto BEFORE the
    # workout starts.
    safety: dict | None = None


class WatchWeek(BaseModel):
    week_start: str
    days: list[dict]


@router.get("/day", response_model=WatchDay)
async def watch_day(
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, DeviceToken] = Depends(get_watch_principal),
) -> WatchDay:
    user, _token = principal
    local_today = datetime.now(ZoneInfo(user.timezone)).date()
    # Concrete gym plan (advisor-generated or manual) wins over the raw
    # template rows; its exercises carry sets/reps/rest for the tracker.
    gym_plan = None
    plan = await plan_for_date(session, user.id, local_today)
    if plan is not None:
        try:
            gym_plan = await session_view(session, user.id, plan.id)
        except Exception:  # pragma: no cover - view built from same rows
            gym_plan = None
    # W-02 audit: pull the latest DailyFeature and compute the safety verdict
    # so the watch can render a modify/rest banner BEFORE the workout starts.
    latest_feature = await session.scalar(
        select(DailyFeature)
        .where(DailyFeature.user_id == user.id)
        .order_by(DailyFeature.date.desc())
        .limit(1)
    )
    safety = safety_block(latest_feature)
    return WatchDay(
        date=local_today.isoformat(),
        weekday=local_today.weekday(),
        sessions=[
            _compact_session(e)
            for e in await resolve_day(session, user.id, local_today)
        ],
        supplements=await active_supplements(session, user.id, local_today),
        alerts=await open_alert_summaries(session, user.id),
        journal_streak=await journal_streak(session, user.id, local_today),
        gym_plan=gym_plan,
        safety=safety,
    )


@router.get("/week", response_model=WatchWeek)
async def watch_week(
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, DeviceToken] = Depends(get_watch_principal),
) -> WatchWeek:
    """The 7 days starting Monday of the token owner's LOCAL current week —
    the gym schedule is a weekly template, so the week view anchors on the
    user-local Monday (§17 day-boundary rule)."""
    user, _token = principal
    local_today = datetime.now(ZoneInfo(user.timezone)).date()
    monday = local_today - timedelta(days=local_today.weekday())
    resolved = await resolve_range(session, user.id, monday, days=7)
    for day in resolved:
        day["sessions"] = [_compact_session(e) for e in day["sessions"]]
    return WatchWeek(week_start=monday.isoformat(), days=resolved)
