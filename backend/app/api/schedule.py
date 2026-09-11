"""Gym schedule CRUD (Phase 10 v2): the recurring weekly routine every
watch/plan surface falls back to.

Session-protected, each user manages THEIR OWN slots only (a foreign slot id
answers 404, the API-wide cross-user convention). POST/PATCH/DELETE are
state-changing so they require the CSRF header (§22.3) exactly like every
other mutating route.
"""

from datetime import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.gym import GymScheduleSlot
from app.models.user import User
from app.queries import create_slot, delete_slot, list_slots, update_slot

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _slot_out(slot: GymScheduleSlot) -> dict:
    return {
        "id": slot.id,
        "weekday": slot.weekday,
        "start_time": slot.start_time.strftime("%H:%M"),
        "title": slot.title,
        "description": slot.description,
        "active": slot.active,
    }


class SlotIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0=Mon .. 6=Sun")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["18:00"])
    title: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=2000)


class SlotPatch(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    title: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    try:
        parsed = time(int(hour), int(minute))
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid start_time")
    return parsed


@router.get("")
async def get_schedule(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return [_slot_out(s) for s in await list_slots(session, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_slot(
    payload: SlotIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    slot = await create_slot(
        session,
        user.id,
        weekday=payload.weekday,
        start_time=_parse_time(payload.start_time),
        title=payload.title,
        description=payload.description,
    )
    await session.commit()
    await session.refresh(slot)
    return _slot_out(slot)


@router.patch("/{slot_id}")
async def patch_slot(
    slot_id: int,
    payload: SlotPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "start_time" in fields:
        fields["start_time"] = _parse_time(fields["start_time"])
    slot = await update_slot(session, user.id, slot_id, **fields)
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found")
    await session.commit()
    return _slot_out(slot)


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_slot(
    slot_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    if not await delete_slot(session, user.id, slot_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found")
    await session.commit()
