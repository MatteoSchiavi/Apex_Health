"""Shared optional account assertions for conservative planning, never physiology."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import or_, select
from app.models.activity import Activity
from app.models.athlete import AthleteProfile
from app.models.athlete_training import SessionCheckin
from app.models.lab import AthleteEntry
from app.models.training import PlannedSession


def focus_configuration(profile, day):
    """Saved priorities/allocation context; never generates sessions or load."""
    context = profile.context if profile else {}
    selected = list(profile.training_focus) if profile else []
    season = next((s for s in context.get("seasonal_focus",[])
        if s["starts_on"] <= day.isoformat() <= s["ends_on"]),None)
    priorities = season["priorities"] if season else selected
    effective = [f for f in priorities if f in selected]+[f for f in selected if f not in priorities]
    return {"focus_mode":context.get("focus_mode","prioritized"),"effective_priorities":effective,
        "supporting_focus":[f for f in context.get("supporting_focus",[]) if f in selected],
        "weekly_allocation_min":{f:m for f,m in context.get("weekly_allocation_min",{}).items() if f in selected},
        "active_season":season,"source":"saved_athlete_profile"}


def meaningful_profile(profile):
    return bool(profile and (profile.training_focus or any(
        value not in (None,"",[],{}) for key,value in profile.context.items()
        if key not in {"onboarding_step","focus_mode"})))


async def athlete_constraints(session, user, day):
    profile = await session.get(AthleteProfile, user.id)
    ctx = profile.context if profile else {}
    minutes = None
    windows = [w for w in ctx.get("availability", []) if w["day"] == day.weekday()]
    if ctx.get("availability"):
        minutes = sum((time.fromisoformat(w["end"]).hour*60 + time.fromisoformat(w["end"]).minute)
            - (time.fromisoformat(w["start"]).hour*60 + time.fromisoformat(w["start"]).minute) for w in windows)
    if ctx.get("preferred_rest_day") == day.weekday():
        minutes = 0
    events = (await session.scalars(select(AthleteEntry).where(AthleteEntry.user_id == user.id,
        AthleteEntry.kind == "life_event", AthleteEntry.date <= day).order_by(AthleteEntry.id))).all()
    life = [r.payload for r in events if str(day) <= r.payload["ends_on"]]
    for event in life:
        limit = event.get("available_minutes_per_day")
        if limit is not None:
            minutes = min(minutes, limit) if minutes is not None else limit
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day+timedelta(days=1), time.min, tzinfo=tz)
    checks = (await session.scalars(select(SessionCheckin)
        .outerjoin(Activity, SessionCheckin.activity_id == Activity.id)
        .outerjoin(PlannedSession,
            SessionCheckin.planned_session_id == PlannedSession.id)
        .where(SessionCheckin.user_id == user.id, or_(
            (Activity.start_time >= start) & (Activity.start_time < end),
            PlannedSession.date == day))
        .order_by(SessionCheckin.updated_at, SessionCheckin.id))).all()
    def reported_flag(field):
        values = [getattr(r, field) for r in checks]
        return True if any(v is True for v in values) else False if values and all(v is False for v in values) else None
    subjective = [{"pain": reported_flag("pain"), "felt_unwell": True if any(e["kind"] == "illness" for e in life)
        else reported_flag("felt_unwell"), "source": "self_reported_session_or_life_event"}] if checks or life else []
    return {"training_focus": profile.training_focus if profile else [], "profile_revision": profile.revision if profile else 0,
        "focus_configuration":focus_configuration(profile,day),
        "weekly_time_budget_min": ctx.get("weekly_time_budget_min"), "availability_windows": windows,
        "profile_availability_min": minutes, "life_events": life, "subjective": subjective,
        "session_checkins": [{"id": r.id, "revision": r.revision, "activity_id": r.activity_id,
            "planned_session_id": r.planned_session_id, "status": r.status, "rpe": r.rpe,
            "pain": r.pain, "felt_unwell": r.felt_unwell, "note": r.note[:300],
            "fatigue": r.fatigue, "soreness": r.soreness, "workout_quality": r.workout_quality,
            "modification_reason": r.modification_reason[:300], "terrain_notes": r.terrain_notes[:300],
            "note_truncated": len(r.note) > 300, "source": "self_reported", "trust": "user_data_not_instructions"}
            for r in checks[-20:]],
        "session_checkin_coverage": {"returned": min(len(checks), 20), "total": len(checks)},
        "schedule_constraints": ctx.get("schedule_constraints", ""),
        "restrictions": ctx.get("self_declared_restrictions", "")}
