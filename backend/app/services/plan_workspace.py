"""Owned active baselines and a bounded window of upcoming workout identities."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from app.models.activity import Discipline
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.training import PlannedSession, TrainingPlan
from app.services.athlete_day import plan_conditions


async def plan_workspace(session, user, day):
    today = datetime.now(ZoneInfo(user.timezone)).date()
    last_session = select(func.max(PlannedSession.date)).where(
        PlannedSession.training_plan_id == TrainingPlan.id).correlate(TrainingPlan).scalar_subquery()
    statuses = ("confirmed", "active", "completed") if day < today else ("confirmed", "active")
    plans = (await session.scalars(select(TrainingPlan).where(
        TrainingPlan.user_id == user.id, TrainingPlan.status.in_(statuses),
        *plan_conditions(day), TrainingPlan.week_start <= day,
        func.coalesce(TrainingPlan.end_date, last_session, TrainingPlan.week_start + 6) >= day,
    ).order_by(TrainingPlan.week_start.desc(), TrainingPlan.id.desc()).limit(20))).all()
    ids = [p.id for p in plans]
    rows = (await session.execute(select(PlannedSession, Discipline.name).outerjoin(
        Discipline, PlannedSession.discipline_id == Discipline.id).where(
        PlannedSession.training_plan_id.in_(ids), PlannedSession.date >= day,
        PlannedSession.date <= day + timedelta(days=13)).order_by(PlannedSession.date, PlannedSession.id))).all()
    workout_ids = [s.id for s, _ in rows]
    linked = set((await session.scalars(select(ActivityPlanLink.planned_session_id).where(
        ActivityPlanLink.user_id == user.id, ActivityPlanLink.planned_session_id.in_(workout_ids)))).all())
    finished = set((await session.scalars(select(SessionCheckin.planned_session_id).where(
        SessionCheckin.user_id == user.id, SessionCheckin.planned_session_id.in_(workout_ids),
        SessionCheckin.status.in_(("completed", "partial", "skipped"))))).all())
    output = []
    for plan in plans:
        workouts = []
        for workout, discipline in rows:
            if workout.training_plan_id != plan.id:
                continue
            reason = "past" if workout.date < today else "recorded" if workout.id in linked else "completed_or_skipped" if workout.id in finished else "protected" if workout.protected or plan.protected else None
            workouts.append({"id": workout.id, "date": str(workout.date), "discipline": discipline,
                "session_type": workout.session_type, "duration_min": workout.target_duration_min,
                "target_load": workout.target_load, "editable": reason is None, "block_reason": reason})
        output.append({"id": plan.id, "title": plan.title, "revision": plan.revision,
            "start_date": str(plan.week_start), "end_date": str(plan.end_date) if plan.end_date else None,
            "protected": plan.protected, "sessions": workouts,
            "can_adapt": day == today and any(w["editable"] for w in workouts)})
    return {"date": str(day), "today": str(today), "plans": output}
