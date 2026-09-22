"""Challenges & rankings API (owner feature batch): friendly multi-user
leaderboards — records for the 5k, activity counts, steps, intensity
minutes, sleep, training load."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.challenge import Challenge, ChallengeMember
from app.models.user import User
from app.queries.rankings import METRICS, global_records, leaderboard

router = APIRouter(tags=["challenges"])


class ChallengeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    metric: str
    period: str = "all_time"
    starts_at: datetime | None = None
    ends_at: datetime | None = None


def _challenge_dict(challenge: Challenge, member_count: int, user: User) -> dict:
    return {
        "id": challenge.id,
        "name": challenge.name,
        "metric": challenge.metric,
        "period": challenge.period,
        "starts_at": challenge.starts_at,
        "ends_at": challenge.ends_at,
        "created_by": challenge.created_by,
        "created_by_name": user.name,
        "is_active": challenge.is_active,
        "member_count": member_count,
    }


@router.get("/rankings")
async def get_rankings(
    metric: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Global all-time records for one metric (all accounts)."""
    if metric not in METRICS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"metric must be one of {', '.join(sorted(METRICS))}",
        )
    return await global_records(session, metric)


@router.get("/challenges")
async def list_challenges(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.execute(
            select(Challenge, User, func.count(ChallengeMember.user_id))
            .join(User, User.id == Challenge.created_by)
            .join(ChallengeMember, ChallengeMember.challenge_id == Challenge.id, isouter=True)
            .where(Challenge.is_active.is_(True))
            .group_by(Challenge.id, User.id)
            .order_by(Challenge.id.desc())
        )
    ).all()
    return [
        _challenge_dict(challenge, count or 0, creator)
        for challenge, creator, count in rows
    ]


@router.post("/challenges", status_code=status.HTTP_201_CREATED)
async def create_challenge(
    payload: ChallengeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    if payload.metric not in METRICS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"metric must be one of {', '.join(sorted(METRICS))}",
        )
    if payload.period not in ("all_time", "weekly", "monthly", "custom"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period must be all_time | weekly | monthly | custom",
        )
    challenge = Challenge(
        name=payload.name,
        metric=payload.metric,
        period=payload.period,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_by=user.id,
    )
    session.add(challenge)
    await session.flush()
    session.add(ChallengeMember(challenge_id=challenge.id, user_id=user.id))
    await session.commit()
    return _challenge_dict(challenge, 1, user)


@router.post("/challenges/{challenge_id}/join", status_code=status.HTTP_200_OK)
async def join_challenge(
    challenge_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None or not challenge.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="challenge not found")
    existing = await session.scalar(
        select(ChallengeMember).where(
            ChallengeMember.challenge_id == challenge_id,
            ChallengeMember.user_id == user.id,
        )
    )
    if existing is None:
        session.add(ChallengeMember(challenge_id=challenge_id, user_id=user.id))
        await session.commit()
    return {"challenge_id": challenge_id, "joined": True}


@router.post("/challenges/{challenge_id}/leave", status_code=status.HTTP_200_OK)
async def leave_challenge(
    challenge_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    membership = await session.scalar(
        select(ChallengeMember).where(
            ChallengeMember.challenge_id == challenge_id,
            ChallengeMember.user_id == user.id,
        )
    )
    if membership is not None:
        await session.delete(membership)
        await session.commit()
    return {"challenge_id": challenge_id, "joined": False}


@router.get("/challenges/{challenge_id}")
async def challenge_detail(
    challenge_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="challenge not found")
    return await leaderboard(session, challenge, datetime.now(UTC))
