"""Authenticated read-only provider synchronization health endpoint."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.services.sync_health import sync_health

router = APIRouter(prefix="/lab", tags=["performance-lab"])


class FeedHealth(BaseModel):
    provider: str
    feed: str
    state: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    latest_measurement_at: datetime | None
    stale_after_hours: int
    error_class: str | None
    retry_state: Literal[
        "unknown", "scheduled", "reconnect_required", "idle"
    ]
    has_checkpoint: bool
    failed_attempts: int
    credentials_state: Literal[
        "unknown", "configured", "reconnect_required", "not_required"
    ]


class SyncHealthResponse(BaseModel):
    feeds: list[FeedHealth]


@router.get("/sync-health", response_model=SyncHealthResponse)
async def get_sync_health(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await sync_health(session, user.id)
