from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import Activity
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.lab import AthleteEntry
from app.models.user import User
from app.api.training_documents import owned_workout
from app.schemas.athlete_training import AssociationIn, CheckinIn, LifeEventIn
from app.services.athlete_day import your_day, checkin_out
from app.services.evidence import scope_lock

router = APIRouter(prefix="/athlete", tags=["athlete-sessions"])


async def owned_activity(session, user_id, ident):
    row = await session.scalar(select(Activity).where(Activity.id == ident, Activity.user_id == user_id))
    if row is None:
        raise HTTPException(404, "Activity not found")
    return row


@router.get("/day")
async def day_view(date: date | None = None, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    day = date or datetime.now(UTC).astimezone(ZoneInfo(user.timezone)).date()
    await scope_lock(session, user.id, "changes")
    return await your_day(session, user, day)


@router.put("/activities/{ident}/association")
async def associate(ident: int, payload: AssociationIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    activity = await owned_activity(session, user.id, ident)
    if payload.planned_session_id:
        workout = await owned_workout(session, user.id, payload.planned_session_id)
        if workout.date != activity.start_time.astimezone(ZoneInfo(user.timezone)).date():
            raise HTTPException(422, "Associate a planned session on the same account-local day")
        used = await session.scalar(select(ActivityPlanLink).where(ActivityPlanLink.planned_session_id == workout.id, ActivityPlanLink.activity_id != ident))
        if used:
            raise HTTPException(409, "Session already associated; review the existing activity")
    row = await session.get(ActivityPlanLink, ident)
    if row is None:
        row = ActivityPlanLink(activity_id=ident, user_id=user.id)
        session.add(row)
    # Reassociation updates the shared check-in identity rather than making duplicates.
    check = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user.id, SessionCheckin.activity_id == ident))
    other_check = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user.id,
        SessionCheckin.planned_session_id == payload.planned_session_id)) if payload.planned_session_id else None
    if other_check and (not check or other_check.id != check.id):
        raise HTTPException(409, "Planned session has its own check-in; review it before associating")
    if check:
        check.planned_session_id = payload.planned_session_id
        check.revision += 1
    row.planned_session_id = payload.planned_session_id
    await session.commit()
    return {"activity_id": ident, "planned_session_id": row.planned_session_id, "method": "user_confirmed"}


@router.put("/checkins")
async def save_checkin(payload: CheckinIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    activity = await owned_activity(session, user.id, payload.activity_id) if payload.activity_id else None
    workout = await owned_workout(session, user.id, payload.planned_session_id) if payload.planned_session_id else None
    if activity and workout:
        link = await session.get(ActivityPlanLink, activity.id)
        if not link or link.planned_session_id != workout.id:
            raise HTTPException(422, "Confirm the activity/session association first")
    activity_id, workout_id = payload.activity_id, payload.planned_session_id
    if activity and not workout:
        link = await session.get(ActivityPlanLink, activity.id)
        workout_id = link.planned_session_id if link else None
    if workout and not activity:
        link = await session.scalar(select(ActivityPlanLink).where(ActivityPlanLink.user_id == user.id, ActivityPlanLink.planned_session_id == workout.id))
        activity_id = link.activity_id if link else None
        if activity_id and payload.status == "skipped":
            raise HTTPException(422, "Recorded associated activity cannot be skipped")
    conditions = []
    if activity_id:
        conditions.append(SessionCheckin.activity_id == activity_id)
    if workout_id:
        conditions.append(SessionCheckin.planned_session_id == workout_id)
    rows = (await session.scalars(select(SessionCheckin).where(SessionCheckin.user_id == user.id, or_(*conditions)))).all()
    if len(rows) > 1:
        raise HTTPException(409, "Session identities have separate check-ins; review them first")
    row = rows[0] if rows else None
    data = payload.model_dump(exclude={"expected_revision", "activity_id", "planned_session_id"})
    if row and all(getattr(row, k) == v for k, v in data.items()) and row.activity_id == activity_id and row.planned_session_id == workout_id:
        return checkin_out(row)  # idempotent exact retry
    if payload.expected_revision != (row.revision if row else 0):
        raise HTTPException(409, "Check-in changed; reload before editing")
    if not row:
        row = SessionCheckin(user_id=user.id, activity_id=activity_id, planned_session_id=workout_id, revision=1)
        session.add(row)
    else:
        row.revision += 1
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return checkin_out(row)


@router.get("/life-events")
async def life_events(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(AthleteEntry).where(AthleteEntry.user_id == user.id, AthleteEntry.kind == "life_event").order_by(AthleteEntry.id.desc()).limit(100))).all()
    return [{"id": r.id, **r.payload} for r in rows]


@router.post("/life-events", status_code=201)
async def add_life_event(payload: LifeEventIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    row = AthleteEntry(user_id=user.id, kind="life_event", date=payload.starts_on, payload=payload.model_dump(mode="json"))
    session.add(row)
    await session.commit()
    return {"id": row.id, **row.payload}


@router.delete("/life-events/{ident}", status_code=204)
async def remove_life_event(ident: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    row = await session.scalar(select(AthleteEntry).where(AthleteEntry.user_id == user.id, AthleteEntry.id == ident, AthleteEntry.kind == "life_event"))
    if row is None:
        raise HTTPException(404, "Life event not found")
    await session.delete(row)
    await session.commit()
