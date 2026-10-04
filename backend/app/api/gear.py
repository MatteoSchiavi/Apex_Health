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
from app.models.gear import Gear
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


class GearIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gear_type: str = Field(min_length=1, max_length=40)
    service_interval_hours: float | None = Field(default=None, gt=0, le=100000)
    service_interval_km: float | None = Field(default=None, gt=0, le=1000000)


@router.post("", status_code=201)
async def create_gear(
    payload: GearIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if payload.gear_type not in {
        "bike",
        "shoes",
        "skis",
        "ski",
        "board",
        "racket",
        "other",
    }:
        raise HTTPException(422, "Unknown equipment type")
    row = Gear(user_id=user.id, **payload.model_dump())
    session.add(row)
    await session.commit()
    return {"gear_id": row.id, "name": row.name}


class GearPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None
    service_interval_hours: float | None = Field(default=None, gt=0, le=100000)
    service_interval_km: float | None = Field(default=None, gt=0, le=1000000)


@router.patch("/{gear_id}")
async def update_gear(
    gear_id: int,
    payload: GearPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.get(Gear, gear_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Equipment not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key in ("name", "active"):
            raise HTTPException(422, "Name and active cannot be null")
        setattr(row, key, value)
    await session.commit()
    return {"gear_id": row.id, "name": row.name, "active": row.active}
