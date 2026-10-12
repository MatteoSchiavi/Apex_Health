"""Authenticated read-only provider synchronization health endpoint."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
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


class AccountHealth(BaseModel):
    provider: str
    state: Literal[
        "syncing", "successful", "partial", "awaiting_new_data", "delayed",
        "auth_required", "failed", "connected", "unknown",
    ]
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    latest_measurement_at: datetime | None
    has_successful_sync: bool
    data_freshness: Literal["fresh", "stale", "not_measured"]
    stale_after_hours: int
    error_class: Literal[
        "authentication", "permission", "transport", "normalization", "timeout",
        "unknown", "sync_failed", "fetch_failed", "normalization_pending",
    ] | None
    failed_attempts: int
    credentials_state: Literal[
        "unknown", "configured", "reconnect_required", "not_required",
    ]
    streams_failed: int = Field(ge=0)
    unprocessed: int = Field(ge=0)


class SyncHealthResponse(BaseModel):
    feeds: list[FeedHealth]
    accounts: list[AccountHealth]


@router.get("/sync-health", response_model=SyncHealthResponse)
async def get_sync_health(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await sync_health(session, user.id)
