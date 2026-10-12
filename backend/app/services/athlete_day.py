"""Account-local day composition. Suggestions never masquerade as completion."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import and_, exists, func, Integer, or_, select
from sqlalchemy.orm import aliased
from app.models.activity import Activity, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import ActivityPlanLink, PlanDocumentDraft, SessionCheckin, WeeklyTrainingTemplate
from app.models.coach import UserContextDoc
from app.models.gym_detail import GymDayPlan
from app.models.lab import ChangeDraft, LabDocument
from app.models.training import TrainingPlan, PlannedSession
from app.services.activity_presentation import sport_kind
from app.services.athlete_constraints import focus_configuration, meaningful_profile

VERSION = "athlete-day-v1"


def plan_conditions(day):
    return [TrainingPlan.status.in_(("confirmed", "active", "completed")),
        or_(TrainingPlan.activated_on.is_(None), TrainingPlan.activated_on <= day),
        or_(TrainingPlan.superseded_on.is_(None), TrainingPlan.superseded_on > day)]


def focus_for(discipline):
    return {"strength": "gym", "running": "running", "cycling": "cycling"}.get(sport_kind(discipline), discipline)


def checkin_out(row):
    return {key: getattr(row, key) for key in ("id", "activity_id", "planned_session_id", "status", "rpe", "pain", "felt_unwell", "note", "revision", "updated_at", "fatigue", "soreness", "workout_quality", "modification_reason", "terrain_notes")} if row else None


async def planning_context(session, user_id, day, profile):
    """Explain saved context separately from whether a workout exists today."""
    meaningful = meaningful_profile(profile)
    narrative = await session.scalar(select(UserContextDoc.id).where(
        UserContextDoc.user_id == user_id, func.length(func.trim(UserContextDoc.content)) > 0).limit(1))
    profile_state = "ready" if meaningful or narrative else "incomplete" if profile and profile.context else "none"
    active = await session.scalar(select(TrainingPlan.id).where(
        TrainingPlan.user_id == user_id, TrainingPlan.status.in_(("active", "confirmed")),
        *plan_conditions(day),
        or_(TrainingPlan.end_date >= day,
            and_(TrainingPlan.end_date.is_(None), TrainingPlan.week_start >= day - timedelta(days=6))))
        .order_by(TrainingPlan.id.desc()).limit(1))
    newer = aliased(PlanDocumentDraft)
    draft = await session.scalar(select(PlanDocumentDraft).outerjoin(LabDocument,
        PlanDocumentDraft.document_id == LabDocument.id).outerjoin(WeeklyTrainingTemplate,
        PlanDocumentDraft.template_id == WeeklyTrainingTemplate.id).where(
        PlanDocumentDraft.user_id == user_id, PlanDocumentDraft.status == "draft",
        or_(and_(LabDocument.user_id == user_id, LabDocument.status == "confirmed",
            PlanDocumentDraft.document_revision == LabDocument.revision),
            and_(WeeklyTrainingTemplate.user_id == user_id,
                PlanDocumentDraft.template_revision == WeeklyTrainingTemplate.revision)),
        ~exists(select(newer.id).where(newer.document_id == PlanDocumentDraft.document_id,
            newer.version > PlanDocumentDraft.version)),
        ~exists(select(newer.id).where(newer.template_id == PlanDocumentDraft.template_id,
            newer.version > PlanDocumentDraft.version)))
        .order_by(PlanDocumentDraft.id.desc()).limit(1))
    template = await session.scalar(select(WeeklyTrainingTemplate.id).where(
        WeeklyTrainingTemplate.user_id == user_id).order_by(WeeklyTrainingTemplate.id.desc()).limit(1))
    state = "plan_draft" if draft else "active_rest_day" if active else "template_ready" if template else "profile_ready" if profile_state == "ready" else "profile_incomplete" if profile_state == "incomplete" else "no_profile"
    return {"state": state, "profile_state": profile_state,
        "profile_revision": profile.revision if profile else 0, "active_plan_id": active,
        "draft_id": draft.id if draft else None, "draft_document_id": draft.document_id if draft else None,
        "draft_template_id": draft.template_id if draft else None, "template_id": template}


async def your_day(session, user, day):
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    linked_history = select(ActivityPlanLink.planned_session_id).join(
        Activity, Activity.id == ActivityPlanLink.activity_id).where(
        ActivityPlanLink.user_id == user.id, Activity.start_time >= start, Activity.start_time < end)
    reported_history = select(SessionCheckin.planned_session_id).where(
        SessionCheckin.user_id == user.id, SessionCheckin.status.in_(("completed", "partial", "skipped")))
    day_query = select(PlannedSession, TrainingPlan, Discipline.name).join(TrainingPlan).outerjoin(
        Discipline, PlannedSession.discipline_id == Discipline.id).where(
        TrainingPlan.user_id == user.id, PlannedSession.date == day,
        or_(and_(*plan_conditions(day)), PlannedSession.id.in_(linked_history), PlannedSession.id.in_(reported_history)))
    rows = (await session.execute(day_query)).all()
    activities = (await session.execute(select(Activity, Discipline.name).outerjoin(Discipline)
        .where(Activity.user_id == user.id, Activity.start_time >= start, Activity.start_time < end)
        .order_by(Activity.start_time, Activity.id))).all()
    activity_ids = [a.id for a, _ in activities]
    planned_ids = [w.id for w, _, _ in rows]
    links = (await session.scalars(select(ActivityPlanLink).where(ActivityPlanLink.user_id == user.id,
        or_(ActivityPlanLink.activity_id.in_(activity_ids), ActivityPlanLink.planned_session_id.in_(planned_ids))))).all()
    by_activity = {r.activity_id: r for r in links}
    by_planned = {r.planned_session_id: r for r in links if r.planned_session_id}
    checkins = (await session.scalars(select(SessionCheckin).where(SessionCheckin.user_id == user.id,
        or_(SessionCheckin.activity_id.in_(activity_ids), SessionCheckin.planned_session_id.in_(planned_ids))))).all()
    checks_activity = {r.activity_id: r for r in checkins if r.activity_id}
    checks_planned = {r.planned_session_id: r for r in checkins if r.planned_session_id}
    profile = await session.get(AthleteProfile, user.id)
    configuration = focus_configuration(profile,day)
    priorities = configuration["effective_priorities"]
    modifications = (await session.scalars(select(ChangeDraft).where(ChangeDraft.user_id == user.id,
        ChangeDraft.kind == "session_patch", ChangeDraft.status == "applied_locally",
        ChangeDraft.after["target_id"].astext.cast(Integer).in_(planned_ids)))).all()
    modified_ids = {r.after.get("target_id") for r in modifications}
    # Legacy gym day plans stay visible; they lack an enduring planned-session identity.
    gyms = (await session.scalars(select(GymDayPlan).where(GymDayPlan.user_id == user.id, GymDayPlan.date == day,
        GymDayPlan.status.in_(("confirmed", "active", "completed"))))).all()
    plans = []
    for workout, plan, discipline in rows:
        linked = by_planned.get(workout.id)
        check = checks_planned.get(workout.id)
        status = check.status if check else "completed" if linked else "modified" if workout.id in modified_ids else "planned"
        plans.append({"id": workout.id, "plan_id": plan.id, "plan_revision": plan.revision,
            "plan_title": plan.title, "date": str(workout.date), "discipline": discipline,
            "start_time": workout.start_time.isoformat() if workout.start_time else None,
            "session_type": workout.session_type, "duration_min": workout.target_duration_min,
            "distance_m": float(workout.target_distance_m) if workout.target_distance_m is not None else None,
            "intensity_targets": workout.intensity_targets, "description": workout.description,
            "plan_protected": plan.protected, "workout_protected": workout.protected,
            "protected": workout.protected or plan.protected, "status": status,
            "activity_id": linked.activity_id if linked else None, "checkin": checkin_out(check),
            "completion_source": "user_confirmed_activity" if linked else "self_reported" if check else None})
    plans.sort(key=lambda s: ((0 if configuration["focus_mode"] == "balanced" else priorities.index(focus_for(s["discipline"]))) if focus_for(s["discipline"]) in priorities else len(priorities), s["start_time"] or "99:99", s["id"]))
    recorded = []
    for activity, discipline in activities:
        link = by_activity.get(activity.id)
        check = checks_activity.get(activity.id)
        candidate = [s for s in plans if not s["activity_id"] and s["status"] not in {"completed", "skipped"}
            and focus_for(s["discipline"]) == focus_for(discipline)]
        candidates = [s["id"] for s in candidate if s["duration_min"] is not None and s["duration_min"] > 0
            and abs(activity.duration_s / 60 - s["duration_min"]) / s["duration_min"] <= .2]
        planned = next((s for s in plans if link and s["id"] == link.planned_session_id), None)
        rpe_load = activity.duration_s / 60 * check.rpe if check and check.rpe is not None and check.status != "skipped" else None
        recorded.append({"id": activity.id, "discipline": discipline, "start_time": activity.start_time,
            "duration_s": activity.duration_s, "distance_m": float(activity.distance_m) if activity.distance_m is not None else None,
            "elevation_gain_m": float(activity.elevation_gain_m) if activity.elevation_gain_m is not None else None,
            "calories": activity.calories, "session_rpe_load": rpe_load, "checkin": checkin_out(check),
            "planned_session_id": link.planned_session_id if link else None,
            "association": "confirmed" if planned else "independent" if link else "needs_confirmation" if candidates else "unplanned",
            "candidate_session_ids": candidates if not link else [], "association_rule": "same_local_day_sport_duration_within_20_percent_requires_confirmation_v1",
            "comparison": {"target_duration_min": planned["duration_min"], "recorded_duration_min": activity.duration_s / 60,
                "duration_delta_min": activity.duration_s / 60 - planned["duration_min"] if planned["duration_min"] is not None else None,
                "target_distance_m": planned["distance_m"], "recorded_distance_m": float(activity.distance_m) if activity.distance_m is not None else None} if planned else None})
    def summarize(items):
        totals = {}
        for key, unit in (("duration_s", "s"), ("distance_m", "m"), ("elevation_gain_m", "m"), ("calories", "kcal"), ("session_rpe_load", "session-RPE min")):
            values = [a[key] for a in items if a[key] is not None]
            totals[key] = {"value": sum(values) if values else None, "unit": unit, "available_sessions": len(values), "total_sessions": len(items)}
        return totals
    sports = {sport_kind(a["discipline"]) if sport_kind(a["discipline"]) != "other" else a["discipline"] or "other" for a in recorded}
    sport_totals = {sport: summarize([a for a in recorded if (sport_kind(a["discipline"]) if sport_kind(a["discipline"]) != "other" else a["discipline"] or "other") == sport]) for sport in sorted(sports)}
    totals = summarize(recorded)
    if len(sports) > 1:
        totals.pop("distance_m")  # Running/cycling distance remains meaningful within each sport.
    context = await planning_context(session, user.id, day, profile)
    return {"date": str(day), "timezone": user.timezone, "formula_version": VERSION,
        "training_focus": priorities, "sessions": plans, "activities": recorded, "totals": totals,
        "focus_configuration": configuration,
        "sport_totals": sport_totals, "planning_context": context,
        "is_historical": day < datetime.now(tz).date(),
        "legacy_gym_sessions": [{"gym_day_plan_id": g.id, "title": g.title, "status": g.status} for g in gyms],
        "state": "multiple_sessions" if len(recorded) > 1 else "activity_recorded" if recorded else "before_training" if plans or gyms else "no_plan",
        "limitations": ["Suggested associations require confirmation; provider load scales are never aggregated."]}
