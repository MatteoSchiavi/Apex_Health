"""Gear endpoints (MASTER_SPEC §18): GET /gear, POST /gear/{id}/service.

Session-protected; POST is state-changing so it requires the CSRF header
(§22.3). Logging a service goes through the §13 service function so the
counters reset and any open gear_service_due alert resolves in one place.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.gear.service import log_gear_service
from app.models.gear import Gear, GearServiceLog
from app.models.user import User
from app.queries import gear_overview

router = APIRouter(prefix="/gear", tags=["gear"])


class GearServiceIn(BaseModel):
    service_type: str = Field(min_length=1)
    performed_at: datetime | None = None  # defaults to now (UTC)
    notes: str | None = None


@router.get("")
async def list_gear(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return await gear_overview(session, user.id)


@router.post("/{gear_id}/service", status_code=status.HTTP_200_OK)
async def record_service(
    gear_id: int,
    payload: GearServiceIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    gear = await session.get(Gear, gear_id)
    if gear is None or gear.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gear not found")
    log = await log_gear_service(
        session,
        gear=gear,
        service_type=payload.service_type,
        performed_at=payload.performed_at or datetime.now(UTC),
        notes=payload.notes,
    )
    await session.commit()
    return {
        "gear_id": gear.id,
        "service_log_id": log.id,
        "hours_since_service": float(gear.hours_since_service),
        "km_since_service": float(gear.km_since_service),
    }
