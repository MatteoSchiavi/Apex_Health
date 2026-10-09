"""Owned, versioned current-input endurance calculations with explicit provenance."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import Activity, ActivityLap, ActivityStream, ActivitySourceLink, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import SessionCheckin
from app.models.user import User
from app.services.activity_presentation import sport_kind
from app.services.endurance_metrics import running_metrics, input_revision
from app.services.cycling_metrics import cycling_metrics
from app.services.evidence import scope_lock

router = APIRouter(prefix="/activities", tags=["endurance"])


@router.get("/{ident}/endurance")
async def endurance(ident: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    activity = await session.scalar(select(Activity).where(Activity.id == ident, Activity.user_id == user.id))
    if activity is None:
        raise HTTPException(404, "Activity not found")
    discipline = await session.scalar(select(Discipline.name).where(Discipline.id == activity.discipline_id))
    kind = sport_kind(discipline, activity.source_metrics)
    streams = (await session.scalars(select(ActivityStream).where(ActivityStream.activity_id == ident)
        .order_by(ActivityStream.t_offset_s).limit(200001))).all()
    laps = (await session.scalars(select(ActivityLap).where(ActivityLap.activity_id == ident).order_by(ActivityLap.lap_index).limit(2001))).all()
    profile = await session.get(AthleteProfile, user.id)
    checkin = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user.id, SessionCheckin.activity_id == ident))
    sources = (await session.execute(select(ActivitySourceLink.source, ActivitySourceLink.external_id)
        .where(ActivitySourceLink.user_id == user.id, ActivitySourceLink.activity_id == ident))).all()
    rpe = checkin.rpe if checkin and checkin.status != "skipped" else None
    dependency = f"checkin:{checkin.id}:{checkin.revision}" if checkin else None
    from zoneinfo import ZoneInfo
    activity_day = activity.start_time.astimezone(ZoneInfo(user.timezone)).date()
    metrics = running_metrics(activity, streams, laps, rpe=rpe, rpe_dependency=dependency, context=profile.context if profile else {}, activity_day=activity_day, profile_revision=profile.revision if profile else None) if kind == "running" else []
    if kind == "cycling":
        from zoneinfo import ZoneInfo
        metrics = cycling_metrics(activity, streams, laps, context=profile.context if profile else {},
            activity_day=activity.start_time.astimezone(ZoneInfo(user.timezone)).date(),
            profile_revision=profile.revision if profile else None, rpe=rpe, rpe_dependency=dependency)
    if len(streams) > 200000 or len(laps) > 2000:
        for result in metrics:
            if any(d.startswith(("streams:", "laps:")) for d in result["source_dependencies"]):
                result.update(value=None, availability="unavailable", unavailable_reason="input_limit_exceeded")
    return {"activity_id": ident, "sport": kind, "input_revision": input_revision(activity, streams, laps, profile, checkin),
        "sources": [{"provider": source, "record_id": external} for source, external in sources],
        "metrics": metrics, "comparison": {"state": "not_computed", "reason": "Comparable sport, units, source conventions, quality and session context required"}}
