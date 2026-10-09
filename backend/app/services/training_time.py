"""Recorded time replaces linked planned time; unplanned sessions consume time too."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.activity import Activity
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.training import PlannedSession, TrainingPlan
from app.services.athlete_day import plan_conditions

async def committed_minutes(session, user, start_day, end_day, exclude_session=None):
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(start_day, time.min, tzinfo=tz)
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)
    activities = (await session.scalars(select(Activity).where(Activity.user_id == user.id,
        Activity.start_time >= start, Activity.start_time < end))).all()
    plans = (await session.scalars(select(PlannedSession).join(TrainingPlan).where(
        TrainingPlan.user_id == user.id, *plan_conditions(PlannedSession.date),
        PlannedSession.date.between(start_day, end_day)))).all()
    ids = [r.id for r in plans]
    linked = set((await session.scalars(select(ActivityPlanLink.planned_session_id).where(
        ActivityPlanLink.user_id == user.id, ActivityPlanLink.planned_session_id.in_(ids)))).all()) if ids else set()
    skipped = set((await session.scalars(select(SessionCheckin.planned_session_id).where(
        SessionCheckin.user_id == user.id, SessionCheckin.status == "skipped",
        SessionCheckin.planned_session_id.in_(ids)))).all()) if ids else set()
    return sum((a.duration_s or 0)/60 for a in activities) + sum(
        p.target_duration_min or 0 for p in plans if p.id != exclude_session and p.id not in linked | skipped)
