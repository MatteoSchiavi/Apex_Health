"""Registered, reproducible recipes. No arbitrary code or mixed load arithmetic."""

from datetime import UTC, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.activity import Activity, ActivitySourceLink, ActivityStream, Discipline
from app.models.coach import UserEvent
from app.models.lab import AnalysisResult, AthleteEntry
from app.models.training import PlannedSession, TrainingPlan
from app.services.alpha_events import record_event
from app.services.evidence import (
    EvidenceError,
    eligible_activity_conditions,
    query_observations,
    snapshot_revision,
    scope_lock,
)

RECIPES = {
    "personal_baseline": "median-mad-v1",
    "multisport_load": "parallel-load-v1",
    "session_quality": "recorded-stream-quality-v1",
    "sleep_timing": "sleep-timing-v1",
    "intervention_association": "matched-day-association-v1",
    "gym_progression": "epley-recorded-sets-v1",
}


def robust_baseline(values):
    if len(values) < 14:
        return {
            "state": "INSUFFICIENT_DATA",
            "sample_count": len(values),
            "required_samples": 14,
            "median": None,
            "mad": None,
            "empirical_range": None,
        }
    ordered = sorted(values)
    mid = median(values)
    return {
        "state": "available",
        "sample_count": len(values),
        "required_samples": 14,
        "median": round(mid, 3),
        "mad": round(median(abs(x - mid) for x in values), 3),
        "empirical_range": [
            ordered[int((len(ordered) - 1) * 0.1)],
            ordered[int((len(ordered) - 1) * 0.9)],
        ],
    }


async def baseline(session, user, metric, start, end, *, origin=None, for_ai=False):
    rows = await query_observations(
        session, user.id, metric, start, end, for_ai=for_ai, origin=origin
    )
    devices = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind == "device_change",
                AthleteEntry.date <= end,
                AthleteEntry.payload["metrics"].contains([metric]),
            )
            .order_by(AthleteEntry.date.desc())
            .limit(1)
        )
    ).all()
    # A new context/device warms up its own baseline, rather than inheriting a
    # pre-change distribution. Entries explicitly name the affected metrics.
    cut = next(
        (d.date for d in devices if metric in d.payload.get("metrics", [])), None
    )
    rows = [r for r in rows if cut is None or r.local_date >= cut]
    groups = {
        (
            r.origin,
            r.metadata_json.get("reading_context"),
            r.metadata_json.get("device_id"),
        )
        for r in rows
        if r.value.get("value") is not None
    }
    if len(groups) > 1:
        raise EvidenceError(
            "CONFLICT",
            "Select one source/measurement context for a comparable baseline",
        )
    # One sample per local day, most recent within the SAME source/context.
    daily = {
        r.local_date: r for r in rows if isinstance(r.value.get("value"), (int, float))
    }
    rows = list(daily.values())
    result = robust_baseline([r.value["value"] for r in rows])
    return {
        **result,
        "metric": metric,
        "period": {"start": str(start), "end": str(end)},
        "origin": rows[-1].origin if rows else origin,
        "device_change_date": str(cut) if cut else None,
        "unit": rows[-1].unit if rows else None,
        "evidence_ids": [f"observation:{r.id}:{r.revision}" for r in rows],
        "missing_days": (end - start).days + 1 - len(rows),
        "interpretation": "Empirical personal distribution; not a clinical reference range.",
    }


async def constraints(session, user, day):
    tz = ZoneInfo(user.timezone)
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    events = (
        await session.scalars(
            select(UserEvent)
            .where(
                UserEvent.user_id == user.id,
                UserEvent.starts_at >= start,
                UserEvent.starts_at < start + timedelta(days=30),
            )
            .order_by(UserEvent.starts_at)
            .limit(50)
        )
    ).all()
    entries = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind.in_(("availability", "daily_checkin")),
                AthleteEntry.date == day,
            )
            .order_by(AthleteEntry.id)
        )
    ).all()
    plans = (
        await session.scalars(
            select(PlannedSession)
            .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(
                TrainingPlan.user_id == user.id,
                TrainingPlan.status.in_(("confirmed", "active")),
                PlannedSession.date >= day,
                PlannedSession.date <= day + timedelta(days=14),
            )
            .order_by(PlannedSession.date, PlannedSession.id)
        )
    ).all()
    return {
        "date": str(day),
        "timezone": user.timezone,
        "events": [
            {
                "id": e.id,
                "title": e.title,
                "kind": e.kind,
                "date": str(e.starts_at.astimezone(tz).date()),
                "days_away": (e.starts_at.astimezone(tz).date() - day).days,
                "priority": e.priority,
                "taper_days": e.taper_days,
            }
            for e in events
        ],
        "availability": [r.payload for r in entries if r.kind == "availability"],
        "subjective": [r.payload for r in entries if r.kind == "daily_checkin"],
        "sessions": [
            {
                "id": p.id,
                "date": str(p.date),
                "duration_min": p.target_duration_min,
                "session_type": p.session_type,
                "description": p.description,
                "discipline_id": p.discipline_id,
            }
            for p in plans
        ],
    }


async def multisport_load(session, user, start, end, *, for_ai=False):
    conditions = (
        await eligible_activity_conditions(session, user.id)
        if for_ai
        else [Activity.user_id == user.id]
    )
    rows = (
        await session.execute(
            select(Activity, Discipline.name)
            .outerjoin(Discipline, Activity.discipline_id == Discipline.id)
            .where(*conditions, Activity.local_date.between(start, end))
            .order_by(Activity.start_time)
            .limit(2000)
        )
    ).all()
    totals, sessions = {}, []
    links = (
        (
            await session.execute(
                select(ActivitySourceLink.activity_id, ActivitySourceLink.source).where(
                    ActivitySourceLink.user_id == user.id,
                    ActivitySourceLink.activity_id.in_([a.id for a, _ in rows]),
                )
            )
        ).all()
        if rows
        else []
    )
    source_map = {}
    for ident, source in links:
        source_map.setdefault(ident, set()).add(source)
    for item, sport in rows:
        sources = sorted(source_map.get(item.id, set()))
        # Only a single provider with a known scale can own a legacy load.
        scale = (
            "Garmin load"
            if "garmin" in sources
            and (
                (item.source_metrics or {})
                .get("_merged_fields", {})
                .get("training_load", "garmin")
                == "garmin"
            )
            else "unknown_legacy_scale"
        )
        metric = f"{sport or 'unknown'}:{scale}"
        bucket = totals.setdefault(
            metric,
            {
                "sport": sport or "unknown",
                "scale": scale,
                "sessions": 0,
                "duration_min": 0,
                "recorded_load": None,
                "missing_load_sessions": 0,
            },
        )
        bucket["sessions"] += 1
        bucket["duration_min"] += item.duration_s / 60
        if item.training_load is None or scale == "unknown_legacy_scale":
            bucket["missing_load_sessions"] += 1
        else:
            bucket["recorded_load"] = (bucket["recorded_load"] or 0) + float(
                item.training_load
            )
        # Qualitative demands describe the discipline; they are not fatigue scores.
        name = sport or "unknown"
        demands = (
            ["aerobic"]
            if "cycl" in name
            else ["aerobic", "impact"]
            if "run" in name
            else ["muscular_legs", "technical"]
            if "ski" in name
            else ["upper_body", "technical"]
            if "sail" in name
            else ["muscular"]
            if name in ("gym", "strength", "strength_training", "gym_general")
            else ["unclassified"]
        )
        sessions.append(
            {
                "id": item.id,
                "date": str(item.local_date),
                "sport": name,
                "sources": sources,
                "duration_min": round(item.duration_s / 60, 1),
                "load_scale": scale,
                "load": float(item.training_load)
                if item.training_load is not None and scale != "unknown_legacy_scale"
                else None,
                "demand_dimensions": demands,
            }
        )
    return {
        "tracks": list(totals.values()),
        "sessions": sessions,
        "sample_count": len(rows),
        "truncated": len(rows) == 2000,
        "unit": "separate provider scales",
        "note": "Provider load, TSS, TRIMP and strain are not summed. Demands are descriptive, not measured fatigue.",
    }


async def session_quality(session, user, ident, *, for_ai=False):
    conditions = (
        await eligible_activity_conditions(session, user.id)
        if for_ai
        else [Activity.user_id == user.id]
    )
    activity = await session.scalar(
        select(Activity).where(*conditions, Activity.id == ident)
    )
    if activity is None:
        raise EvidenceError("NOT_FOUND", "Session unavailable")
    streams = (
        await session.scalars(
            select(ActivityStream)
            .where(ActivityStream.activity_id == ident)
            .order_by(ActivityStream.t_offset_s)
            .limit(86400)
        )
    ).all()

    def drift(channel):
        samples = [
            (r.t_offset_s, float(getattr(r, channel)))
            for r in streams
            if getattr(r, channel) is not None
        ]
        if len(samples) < 60 or not samples or samples[-1][0] - samples[0][0] < 1200:
            return {
                "value": None,
                "state": "INSUFFICIENT_DATA",
                "sample_count": len(samples),
            }
        gaps = sum(
            b[0] - a[0] for a, b in zip(samples, samples[1:]) if b[0] - a[0] > 30
        )
        if gaps > 0.1 * (samples[-1][0] - samples[0][0]):
            return {"value": None, "state": "SENSOR_GAPS", "sample_count": len(samples)}
        mid = (samples[-1][0] + samples[0][0]) / 2
        first = [v for t, v in samples if t <= mid]
        last = [v for t, v in samples if t > mid]
        a, b = sum(first) / len(first), sum(last) / len(last)
        return {
            "value": round((b - a) / a * 100, 2) if a else None,
            "state": "available",
            "sample_count": len(samples),
        }

    from app.models.coach import SessionFeedback

    feedback = (
        await session.scalars(
            select(SessionFeedback)
            .where(
                SessionFeedback.user_id == user.id,
                SessionFeedback.date == activity.local_date,
            )
            .limit(20)
        )
    ).all()
    return {
        "activity_id": ident,
        "hr_half_change_pct": drift("hr"),
        "power_half_change_pct": drift("power"),
        "normalized_power": float(activity.np_power)
        if activity.np_power is not None
        else None,
        "stream_samples": len(streams),
        "sample_count": len(streams),
        "feedback": [
            {"rpe": f.rpe, "pain_flag": f.injury_flag, "soreness": f.soreness}
            for f in feedback
        ],
        "limitations": [
            "Half-session changes describe the recording; they are not aerobic decoupling or interval compliance without a matching intended workout.",
            "Missing power does not permit NP or TSS reconstruction.",
        ],
    }


async def run_recipe(
    session,
    user,
    recipe,
    *,
    metric=None,
    start=None,
    end=None,
    origin=None,
    activity_id=None,
    experiment_id=None,
    for_ai=False,
    job_id=None,
):
    if recipe not in RECIPES:
        raise EvidenceError("INVALID_ARGUMENTS", "Unknown analysis recipe")
    await scope_lock(session, user.id, "changes")
    input_revision = await snapshot_revision(session, user.id)
    today = datetime.now(ZoneInfo(user.timezone)).date()
    end = end or today
    start = start or end - timedelta(days=27)
    if start > end or (end - start).days > 365:
        raise EvidenceError("INVALID_ARGUMENTS", "Analysis range is capped at 366 days")
    if job_id is None:
        record_event(session, user.id, "analysis_started")
    if recipe == "personal_baseline":
        result = await baseline(
            session, user, metric, start, end, origin=origin, for_ai=for_ai
        )
    elif recipe == "multisport_load":
        result = await multisport_load(session, user, start, end, for_ai=for_ai)
    elif recipe == "session_quality":
        if activity_id is None:
            raise EvidenceError("INVALID_ARGUMENTS", "Choose an activity")
        result = await session_quality(session, user, activity_id, for_ai=for_ai)
    elif recipe == "gym_progression":
        from app.models.gym_detail import GymSetLog, GymDayExercise, GymExercise

        tz = ZoneInfo(user.timezone)
        rows = (
            await session.execute(
                select(GymSetLog, GymExercise)
                .join(
                    GymDayExercise, GymSetLog.gym_day_exercise_id == GymDayExercise.id
                )
                .join(GymExercise, GymDayExercise.exercise_id == GymExercise.id)
                .where(
                    GymSetLog.user_id == user.id,
                    GymSetLog.done_at
                    >= datetime.combine(start, datetime.min.time(), tzinfo=tz),
                    GymSetLog.done_at
                    < datetime.combine(
                        end + timedelta(days=1), datetime.min.time(), tzinfo=tz
                    ),
                )
                .order_by(GymSetLog.done_at)
                .limit(5000)
            )
        ).all()
        groups = {}
        for log, exercise in rows:
            key = (exercise.id, str(log.done_at.astimezone(tz).date()))
            bucket = groups.setdefault(
                key,
                {
                    "exercise": exercise.name,
                    "date": key[1],
                    "sets": 0,
                    "reps": 0,
                    "volume_kg": 0,
                    "e1rm_kg": None,
                },
            )
            bucket["sets"] += 1
            bucket["reps"] += log.reps_done
            if log.weight_kg is not None:
                weight = float(log.weight_kg)
                bucket["volume_kg"] += weight * log.reps_done
                if 1 <= log.reps_done <= 10 and weight > 0:
                    estimate = weight * (1 + log.reps_done / 30)
                    bucket["e1rm_kg"] = max(bucket["e1rm_kg"] or 0, round(estimate, 1))
        result = {
            "sample_count": len(rows),
            "sessions": list(groups.values()),
            "formula": "Epley: recorded load × (1 + reps/30), only 1–10 reps",
            "limitations": [
                "Estimated strength from recorded sets, not a tested maximum. Machine loads and different exercises are not comparable."
            ],
        }
    elif recipe == "sleep_timing":
        from statistics import pstdev

        rows = await query_observations(
            session, user.id, "sleep_duration", start, end, for_ai=for_ai, origin=origin
        )
        daily = {
            r.local_date: r
            for r in rows
            if isinstance(r.value.get("value"), (float, int))
        }
        rows = list(daily.values())
        values = [r.value["value"] for r in rows]
        setting = await session.scalar(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind == "metric_settings",
                AthleteEntry.date <= start,
            )
            .order_by(AthleteEntry.date.desc(), AthleteEntry.id.desc())
            .limit(1)
        )
        target = setting.payload.get("sleep_target_h") if setting else None
        bedtimes = []
        wake = []
        for row in rows:
            for field, dest in (("sleep_start", bedtimes), ("sleep_end", wake)):
                stamp = row.metadata_json.get(field)
                if stamp:
                    local = datetime.fromisoformat(stamp).astimezone(
                        ZoneInfo(user.timezone)
                    )
                    hour = local.hour + local.minute / 60
                    dest.append(
                        hour - 24 if field == "sleep_start" and hour > 12 else hour
                    )
        result = {
            "sample_count": len(values),
            "median_duration_h": median(values) if values else None,
            "sleep_target_h": target,
            "sleep_debt_h": round(sum(max(0, target - v) for v in values), 2)
            if target and values
            else None,
            "timing_consistency": {
                "bedtime_std_h": round(pstdev(bedtimes), 2)
                if len(bedtimes) >= 7
                else None,
                "wake_std_h": round(pstdev(wake), 2) if len(wake) >= 7 else None,
                "timing_samples": min(len(wake), len(bedtimes)),
            },
            "missing_days": (end - start).days + 1 - len(values),
            "limitations": [
                "Recorded nights only; missing nights do not equal zero sleep. Debt uses an explicit personal target effective at the start of this period."
            ],
            "evidence_ids": [f"observation:{r.id}:{r.revision}" for r in rows],
        }
    else:
        from app.services.experiments import experiment_analysis

        result = await experiment_analysis(session, user, experiment_id, for_ai=for_ai)
    if input_revision != await snapshot_revision(session, user.id):
        raise EvidenceError(
            "STALE_DATA",
            "Inputs changed during calculation; retry with a fresh snapshot",
        )
    row = AnalysisResult(
        user_id=user.id,
        recipe=recipe,
        formula_version=RECIPES[recipe],
        snapshot_revision=input_revision,
        result={**result, "_source_policy": "ai_eligible_v1" if for_ai else "ui_only"},
    )
    session.add(row)
    await session.flush()
    record_event(session, user.id, "analysis_completed", {"job_id": job_id} if job_id else {})
    return {
        "handle": f"analysis:{row.id}",
        "recipe": recipe,
        "formula_version": RECIPES[recipe],
        "computed_at": datetime.now(UTC).isoformat(),
        "timezone": user.timezone,
        "period": {"start": str(start), "end": str(end)},
        "snapshot_revision": row.snapshot_revision,
        "data": result,
    }
