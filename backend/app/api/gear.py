"""Gear endpoints (MASTER_SPEC §18): GET /gear, POST /gear/{id}/service.

Session-protected; POST is state-changing so it requires the CSRF header
(§22.3). Logging a service goes through the §13 service function so the
counters reset and any open gear_service_due alert resolves in one place.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.gear.service import log_gear_service, accumulate_gear_usage
from app.models.gear import Gear, ActivityGearLink, GearServiceLog, DisciplineGearDefault
from app.models.activity import Activity, Discipline
from app.models.lab import ChangeAudit
from app.models.user import User
from app.queries import gear_overview
from app.schemas.changes import Strict
from app.services.evidence import scope_lock

router = APIRouter(prefix="/gear", tags=["gear"])


class GearServiceIn(Strict):
    service_type: str = Field(min_length=1, max_length=80)
    performed_at: datetime | None = None  # defaults to now (UTC)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def real_service_time(self):
        if self.performed_at is not None and (self.performed_at.tzinfo is None or self.performed_at > datetime.now(UTC)):
            raise ValueError('Use a real service time with a timezone, no later than now')
        return self


@router.get("")
async def list_gear(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return await gear_overview(session, user.id)


@router.get("/{gear_id}")
async def get_gear(
    gear_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    rows = await gear_overview(session, user.id, gear_id=gear_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found")
    return rows[0]


@router.post("/{gear_id}/service", status_code=status.HTTP_200_OK)
async def record_service(
    gear_id: int,
    payload: GearServiceIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await scope_lock(session, user.id, 'changes')
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
    await session.flush()
    await accumulate_gear_usage(session, gear)
    session.add(ChangeAudit(user_id=user.id, action='gear_service_recorded', payload={'gear_id':gear.id,'service_log_id':log.id}))
    await session.commit()
    return {
        "gear_id": gear.id,
        "service_log_id": log.id,
        "hours_since_service": float(gear.hours_since_service),
        "km_since_service": float(gear.km_since_service),
    }


class GearIn(Strict):
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
    await scope_lock(session, user.id, 'changes')
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


class GearPatch(Strict):
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
    await scope_lock(session, user.id, 'changes')
    row = await session.get(Gear, gear_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Equipment not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key in ("name", "active"):
            raise HTTPException(422, "Name and active cannot be null")
        setattr(row, key, value)
    await accumulate_gear_usage(session, row)
    await session.commit()
    return {"gear_id": row.id, "name": row.name, "active": row.active}


async def owned_gear(session,user_id,ident):
    row = await session.scalar(select(Gear).where(Gear.id==ident,Gear.user_id==user_id).with_for_update())
    if row is None:
        raise HTTPException(404,'Equipment not found')
    return row


@router.get('/{gear_id}/history')
async def gear_history(gear_id:int,limit:int=Query(default=100,ge=1,le=200),offset:int=Query(default=0,ge=0,le=1000000),
        session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    gear = await owned_gear(session,user.id,gear_id)
    conditions=(ActivityGearLink.gear_id==gear.id,Activity.user_id==user.id)
    totals = (await session.execute(select(func.count(Activity.id),func.sum(Activity.duration_s),func.sum(Activity.distance_m),
        func.count(Activity.id).filter(Activity.distance_m.is_(None))).select_from(ActivityGearLink)
        .join(Activity,Activity.id==ActivityGearLink.activity_id).where(*conditions))).one()
    rows = (await session.execute(select(Activity,Discipline.name).select_from(ActivityGearLink)
        .join(Activity,Activity.id==ActivityGearLink.activity_id).outerjoin(Discipline,Discipline.id==Activity.discipline_id)
        .where(*conditions).order_by(Activity.start_time.desc(),Activity.id.desc()).offset(offset).limit(limit))).all()
    logs = (await session.scalars(select(GearServiceLog).where(GearServiceLog.gear_id==gear.id)
        .order_by(GearServiceLog.performed_at.desc(),GearServiceLog.id.desc()).limit(100))).all()
    defaults = list((await session.scalars(select(DisciplineGearDefault.discipline_id).where(
        DisciplineGearDefault.user_id==user.id,DisciplineGearDefault.gear_id==gear.id))).all())
    return {'gear':(await gear_overview(session,user.id,gear_id=gear.id))[0],
        'lifetime':{'activity_count':totals[0],'hours':float(totals[1])/3600 if totals[1] is not None else None,
            'km':float(totals[2])/1000 if totals[2] is not None else None,'missing_distance_count':totals[3],
            'method':'sum owned canonical linked activities; unknown distance remains missing'},
        'activities':[{'id':row.id,'date':row.start_time.astimezone(ZoneInfo(user.timezone)).date().isoformat(),
            'discipline':name,'duration_s':row.duration_s,'distance_m':float(row.distance_m) if row.distance_m is not None else None} for row,name in rows],
        'pagination':{'limit':limit,'offset':offset,'total':totals[0]},
        'services':[{'id':row.id,'service_type':row.service_type,'performed_at':row.performed_at,'notes':row.notes} for row in logs],
        'discipline_choices':[{'id':row.id,'name':row.name} for row in (await session.scalars(select(Discipline).order_by(Discipline.name))).all()],
        'default_discipline_ids':defaults,'reminder_policy':'user_configured_intervals_only'}


@router.get('/{gear_id}/comparison')
async def compare_gear(gear_id:int, other_gear_id:int=Query(gt=0),
        session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    from app.services.gear_comparison import ACTIVITY_LIMIT, comparison
    gears = list((await session.scalars(select(Gear).where(
        Gear.id.in_((gear_id,other_gear_id)),Gear.user_id==user.id))).all())
    if len(gears) != 2:
        if gear_id == other_gear_id and gears:
            raise HTTPException(422,'Choose two different equipment items')
        raise HTTPException(404,'Equipment not found')
    items = {row.id:row for row in gears}
    if items[gear_id].gear_type != items[other_gear_id].gear_type:
        raise HTTPException(422,'Compare equipment of the same type')
    rows = []
    totals = []
    for ident in (gear_id,other_gear_id):
        conditions = (ActivityGearLink.gear_id==ident,Activity.user_id==user.id)
        totals.append(await session.scalar(select(func.count(Activity.id)).select_from(ActivityGearLink)
            .join(Activity,Activity.id==ActivityGearLink.activity_id).where(*conditions)))
        rows.append(list((await session.scalars(select(Activity).select_from(ActivityGearLink)
            .join(Activity,Activity.id==ActivityGearLink.activity_id).where(*conditions)
            .order_by(Activity.start_time.desc(),Activity.id.desc()).limit(ACTIVITY_LIMIT))).all()))
    result = comparison(rows[0],rows[1],user.timezone)
    result.update({'selected_gear':{'id':gear_id,'name':items[gear_id].name},
        'other_gear':{'id':other_gear_id,'name':items[other_gear_id].name},
        'history_scope':{'activity_limit_per_gear':ACTIVITY_LIMIT,'selected_total':totals[0],
            'other_total':totals[1],'truncated':any(count > ACTIVITY_LIMIT for count in totals)}})
    return result


@router.put('/{gear_id}/activities/{activity_id}')
async def link_activity(gear_id:int,activity_id:int,session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    await scope_lock(session,user.id,'changes')
    gear = await owned_gear(session,user.id,gear_id)
    activity = await session.scalar(select(Activity).where(Activity.id==activity_id,Activity.user_id==user.id))
    if activity is None:
        raise HTTPException(404,'Activity not found')
    link = await session.get(ActivityGearLink,(activity.id,gear.id))
    if link is None:
        session.add(ActivityGearLink(activity_id=activity.id,gear_id=gear.id))
        session.add(ChangeAudit(user_id=user.id,action='activity_gear_linked',payload={'gear_id':gear.id,'activity_id':activity.id}))
        await session.flush()
    await accumulate_gear_usage(session,gear)
    await session.commit()
    return {'gear_id':gear.id,'activity_id':activity.id,'linked':True}


@router.delete('/{gear_id}/activities/{activity_id}',status_code=204)
async def unlink_activity(gear_id:int,activity_id:int,session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    await scope_lock(session,user.id,'changes')
    gear = await owned_gear(session,user.id,gear_id)
    activity = await session.scalar(select(Activity.id).where(Activity.id==activity_id,Activity.user_id==user.id))
    if activity is None:
        raise HTTPException(404,'Activity not found')
    link = await session.get(ActivityGearLink,(activity_id,gear.id))
    if link:
        await session.delete(link)
        session.add(ChangeAudit(user_id=user.id,action='activity_gear_unlinked',payload={'gear_id':gear.id,'activity_id':activity_id}))
        await session.flush()
    await accumulate_gear_usage(session,gear)
    await session.commit()


@router.put('/{gear_id}/defaults/{discipline_id}')
async def set_default(gear_id:int,discipline_id:int,session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    await scope_lock(session,user.id,'changes')
    gear = await owned_gear(session,user.id,gear_id)
    if not gear.active:
        raise HTTPException(409,'Activate this equipment before using it as a default')
    if not await session.get(Discipline,discipline_id):
        raise HTTPException(404,'Discipline not found')
    row = await session.get(DisciplineGearDefault,(user.id,discipline_id))
    if row is None:
        session.add(DisciplineGearDefault(user_id=user.id,discipline_id=discipline_id,gear_id=gear.id))
    else:
        row.gear_id=gear.id
    session.add(ChangeAudit(user_id=user.id,action='gear_default_set',payload={'gear_id':gear.id,'discipline_id':discipline_id}))
    await session.commit()
    return {'gear_id':gear.id,'discipline_id':discipline_id,'applies_to':'newly_imported_activities'}


@router.delete('/{gear_id}/defaults/{discipline_id}',status_code=204)
async def remove_default(gear_id:int,discipline_id:int,session:AsyncSession=Depends(get_session),user:User=Depends(get_current_user)):
    await scope_lock(session,user.id,'changes')
    await owned_gear(session,user.id,gear_id)
    await session.execute(delete(DisciplineGearDefault).where(DisciplineGearDefault.user_id==user.id,
        DisciplineGearDefault.discipline_id==discipline_id,DisciplineGearDefault.gear_id==gear_id))
    session.add(ChangeAudit(user_id=user.id,action='gear_default_removed',payload={'gear_id':gear_id,'discipline_id':discipline_id}))
    await session.commit()
