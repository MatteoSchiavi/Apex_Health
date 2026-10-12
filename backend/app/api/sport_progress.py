"""Deterministic running/cycling history; independent of AI access and consent."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.services.sport_progress import sport_overview

router = APIRouter(prefix="/athlete/sports", tags=["sport-progress"])


@router.get("/{sport}/overview")
async def overview(sport: Literal["running", "cycling"], start: date | None = None,
        end: date | None = None, user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session)):
    try:
        return await sport_overview(session, user, sport, start, end)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
