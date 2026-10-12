"""Read-only, account-scoped sport history from canonical activity/session records.

Overview facts are descriptive. Missing measurements and unverified conventions
never become zero, physiological thresholds, or injury predictions.
"""
from collections import Counter, defaultdict
from math import sqrt
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models.activity import Activity, ActivityLap, ActivityStream, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.lab import AthleteEntry, Observation
from app.models.training import PlannedSession, TrainingPlan
from app.services.activity_presentation import number
from app.services.cycling_metrics import confirmed_ftp, cycling_metrics, dense_power
from app.services.endurance_metrics import (metric, moving_time, paired_intervals,
    positive, running_metrics, steady_effort, half_means)
from app.connectors.validation import valid_weight_kg
from app.services.athlete_constraints import focus_configuration
from app.services.recorded_dynamics import DYNAMICS_FIELDS

VERSION = "apex-sport-progress-v1"
SPORTS = {"running": ("running",), "cycling": ("road_cycling", "mountain_biking", "gravel_cycling")}
ACTIVITY_LIMIT = 10000
STREAM_BUDGET = 500000
LAP_BUDGET = 10000
RECENT_LIMIT = 20
POWER_DURATIONS = (5, 15, 30, 60, 300, 600, 1200, 1800, 3600)
ADVANCED_SEGMENT_BUDGET = 1000


def valid_stream_value(field, value):
    value = positive(value,zero=field in {"power","speed","cadence"})
    upper = {"power":5000,"speed":100,"cadence":500,"hr":300}[field]
    return value if value is not None and value <= upper else None


def outcome(key, value, unit, formula, dependencies=(), *, reason=None, quality=None,
            recorded=False, limitations=(), prerequisites=()):
    row = metric(key, value, unit, formula, list(dependencies), version=VERSION,
        reason=reason, recorded=recorded, limitations=list(limitations), prerequisites=list(prerequisites))
    row["quality"] = quality or {}
    return row


def local_day(activity, timezone):
    return activity.start_time.astimezone(ZoneInfo(timezone)).date()


def date_bounds(start, end, timezone, *, now=None):
    """Inclusive account-local dates; UTC predicates also respect DST changes."""
    end = end or (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()
    start = start or end - timedelta(days=83)
    if start > end or (end-start).days >= 730:
        raise ValueError("Use an increasing range of at most 730 inclusive days")
    return start, end


def utc_bounds(start, end, timezone):
    tz = ZoneInfo(timezone)
    return (datetime.combine(start, time.min, tz).astimezone(UTC),
            datetime.combine(end + timedelta(days=1), time.min, tz).astimezone(UTC))


def volume_bucket(rows, start, end):
    totals, observed = {}, {}
    for name, attr in (("distance", "distance_m"), ("duration", "duration_s"), ("elevation", "elevation_gain_m")):
        valid = [positive(getattr(a, attr, None), zero=True) for a in rows]
        valid = [v for v in valid if v is not None]
        totals[attr] = sum(valid) if valid else None
        observed[name] = len(valid)
    return {"start": start.isoformat(), "end": end.isoformat(), "activity_count": len(rows),
        **totals, "observed": observed,
        "formula": "sum(nonnegative recorded field); count(canonical activities)",
        "formula_version": VERSION, "units": {"distance_m": "m", "duration_s": "s", "elevation_gain_m": "m"},
        "source_dependencies": [f"activity:{a.id}" for a in rows],
        "quality": {"partial_measurements": any(n < len(rows) for n in observed.values()),
                    "empty_bucket": not rows}}


def history_buckets(rows, start, end, timezone, *, monthly=False):
    grouped = defaultdict(list)
    for a in rows:
        day = local_day(a, timezone)
        key = day.replace(day=1) if monthly else day-timedelta(days=day.weekday())
        grouped[key].append(a)
    cursor = start.replace(day=1) if monthly else start-timedelta(days=start.weekday())
    result = []
    while cursor <= end:
        next_day = ((cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
                    if monthly else cursor+timedelta(days=7))
        result.append(volume_bucket(grouped[cursor], max(cursor, start), min(next_day-timedelta(days=1), end)))
        cursor = next_day
    return result


def eligible_run(a):
    return (positive(a.distance_m) is not None and positive(a.duration_s) is not None
        and getattr(a, "data_completeness", None) in {"full", "partial"})


def long_run_progression(current, history, timezone, *, complete=True, day_index=None):
    """Exact preceding 30 × 24 hours, including earlier same-day activities.

    Compare UTC instants so a DST change cannot alter the elapsed window.
    Historical references may precede the display range. Equal longest
    distances use earliest start, then canonical ID.
    """
    day = local_day(current, timezone)
    current_at = current.start_time.astimezone(UTC)
    start = current_at-timedelta(days=30)
    first_day = start.astimezone(ZoneInfo(timezone)).date()
    candidates = history if day_index is None else [a for i in range((day-first_day).days+1)
        for a in day_index.get(first_day+timedelta(days=i), [])]
    refs = [a for a in candidates if a.id != current.id and eligible_run(a)
            and start <= a.start_time.astimezone(UTC) < current_at]
    reference = sorted(refs, key=lambda a: (-float(a.distance_m), a.start_time, a.id))[0] if refs else None
    value = None
    reason = "incomplete_history" if not complete else "invalid_current_distance_or_source_quality" if not eligible_run(current) else "no_eligible_prior_30_day_run"
    if complete and eligible_run(current) and reference:
        value = {"activity_id": current.id, "date": day.isoformat(), "distance_m": float(current.distance_m),
            "reference_activity_id": reference.id, "reference_distance_m": float(reference.distance_m),
            "reference_date": local_day(reference, timezone).isoformat(),
            "window_start": start.isoformat(), "window_end_exclusive": current_at.isoformat(),
            "window_duration_s": 30*86400, "reference_start_time": reference.start_time.isoformat(),
            "change_pct": (float(current.distance_m)/float(reference.distance_m)-1)*100}
    return outcome("long_run_progression", value, "%", "(current_distance_m / longest_eligible_distance_m_in_[current_start_UTC-2592000s,current_start_UTC) - 1) * 100",
        [f"activity:{current.id}:distance_m"] + ([f"activity:{reference.id}:distance_m"] if reference else []), reason=reason,
        quality={"window_start": start.isoformat(), "window_end_exclusive": current_at.isoformat(), "window_duration_s":30*86400, "window_unit":"elapsed_seconds", "eligible_reference_count": len(refs), "history_complete": complete},
        limitations=["descriptive_not_injury_prediction", "no_universal_safe_percentage", "earlier_same_day_runs_eligible"],
        prerequisites=["positive_recorded_distance_and_duration", "full_or_partial_source_quality", "owned_running_reference"])


def consistency(rows, weekly, timezone, *, complete=True):
    days = len({local_day(a, timezone) for a in rows})
    active = sum(b["activity_count"] > 0 for b in weekly)
    value = {"active_weeks": active, "observed_weeks": len(weekly), "training_days": days,
             "activity_count": len(rows), "active_week_pct": active / len(weekly)*100} if complete and weekly else None
    return outcome("training_consistency", value, "%", "count(weeks with >=1 recorded activity) / count(observed calendar weeks) * 100",
        [f"activity:{a.id}:start_time" for a in rows], reason="incomplete_activity_history" if not complete else "empty_date_range",
        quality={"partial_boundary_weeks_included": True}, limitations=["recorded_history_not_proof_of_no_training", "partial_weeks_included"])


def adherence(planned, links, checks, activities, end, *, complete=True):
    """Association or explicit completed feedback; never merely the same date."""
    ids = {a.id for a in activities}
    associated = {link.planned_session_id for link in links
        if link.method == "user_confirmed" and link.activity_id in ids and link.planned_session_id is not None}
    by_plan = {}
    for c in sorted(checks,key=lambda c:c.id,reverse=True):
        if c.planned_session_id is not None:
            by_plan.setdefault(c.planned_session_id,c)
    due = [p for p in planned if p.date <= end]
    completed, partial, skipped = [], [], []
    for p in due:
        check = by_plan.get(p.id)
        if check and check.status == "skipped":
            skipped.append(p.id)
        elif check and check.status == "partial":
            partial.append(p.id)
        elif p.id in associated or check and check.status == "completed":
            completed.append(p.id)
    value = {"planned_count": len(due), "completed_count": len(completed), "partial_count": len(partial),
        "skipped_count": len(skipped), "unresolved_count": len(due)-len(completed)-len(partial)-len(skipped),
        "completed_session_ids": completed, "completion_pct": len(completed)/len(due)*100} if due and complete else None
    return outcome("planned_session_adherence", value, "%", "explicitly_completed_or_user_associated_due_sessions / confirmed_due_sessions * 100",
        [f"planned_session:{p.id}" for p in due] + [f"association:{l.activity_id}:{l.planned_session_id}" for l in links]
        + [f"checkin:{c.id}:{c.revision}" for c in checks], reason="incomplete_history" if not complete else "no_confirmed_due_sessions",
        limitations=["association_confirms_identity_not_target_intensity", "unresolved_is_not_automatically_skipped"],
        prerequisites=["confirmed_active_or_completed_plan", "explicit_session_identity"])


def best_duration_power(activity, streams, *, durations=POWER_DURATIONS):
    """Exact rolling means within the shared dense 1Hz power eligibility gate."""
    segments, valid, _ = dense_power(activity, streams)
    result = []
    for seconds in durations:
        best = None
        if valid:
            for segment in segments:
                if len(segment) < seconds:
                    continue
                rolling = sum(segment[:seconds])
                best = max(best if best is not None else 0, rolling/seconds)
                for i in range(seconds, len(segment)):
                    rolling += segment[i]-segment[i-seconds]
                    best = max(best, rolling/seconds)
        result.append(outcome(f"best_power_{seconds}s", best, "W", f"max(sum({seconds} contiguous recorded 1Hz power samples) / {seconds})",
            [f"streams:{activity.id}:power"], reason="requires_dense_power_and_full_duration_window",
            quality={"activity_id": activity.id, "duration_s": seconds, "dense_power_eligible": bool(valid)},
            limitations=["recorded_window_not_protocol_validated_FTP", "no_gap_interpolation"],
            prerequisites=["95_percent_power_coverage", "5min_continuous_segment", "1Hz_recorded_power", "complete_duration_window"]))
    return result


def power_curve(rows, streams, *, complete=True):
    by_key = defaultdict(list)
    for a in rows:
        for m in best_duration_power(a, streams.get(a.id, [])):
            if m["value"] is not None:
                by_key[m["key"]].append(m)
    result = []
    for seconds in POWER_DURATIONS:
        key = f"best_power_{seconds}s"
        eligible = by_key[key]
        if eligible:
            winner = max(eligible, key=lambda m: m["value"])
            winner["quality"]["eligible_activity_count"] = len(eligible)
            winner["quality"]["history_complete"] = complete
            winner["limitations"].append("best_in_loaded_eligible_history" if not complete else "best_in_requested_range")
            result.append(winner)
        else:
            result.append(outcome(key, None, "W", f"max(valid recorded {seconds}s mean power across range)",
                reason="no_eligible_dense_power_window", quality={"duration_s": seconds, "history_complete": complete}))
    return result


def recorded_best_efforts(rows):
    """Preserve provider, distance and duration convention; never merge scales."""
    groups = defaultdict(list)
    for a in rows:
        for provider, block in (a.source_metrics or {}).items():
            if not isinstance(block, dict) or not isinstance(block.get("best_efforts"), list):
                continue
            for i, effort in enumerate(block["best_efforts"][:100]):
                if not isinstance(effort, dict):
                    continue
                distance, duration = positive(effort.get("distance_m")), positive(effort.get("duration_s"))
                convention = effort.get("duration_convention")
                if distance and duration and distance <= (positive(a.distance_m) or 0) and duration <= (positive(a.duration_s) or 0) and convention in {"elapsed", "moving"}:
                    groups[(provider, distance, convention)].append((duration, a, i))
    result = []
    for (provider, distance, convention), entries in sorted(groups.items()):
        duration, a, i = min(entries, key=lambda e: (e[0], e[1].start_time, e[1].id))
        result.append(outcome("recorded_best_effort", {"activity_id": a.id, "provider": provider,
            "distance_m": distance, "duration_s": duration, "duration_convention": convention}, "s",
            "min(provider_recorded_duration for identical distance and duration convention)",
            [f"activity:{a.id}:source_metrics.{provider}.best_efforts[{i}]"], recorded=True,
            quality={"eligible_count": len(entries)}, limitations=["provider_recorded_not_independently_verified", "provider_conventions_kept_separate"]))
    return result or [outcome("recorded_best_effort", None, "s", "provider_recorded_best_efforts", reason="missing_recorded_efforts_with_explicit_distance_and_duration_convention")]


def comparable_context(a):
    """Only explicit recorded steady-session context qualifies for comparisons."""
    for provider, block in (a.source_metrics or {}).items():
        if not isinstance(block, dict):
            continue
        ctx = block.get("comparison_context")
        if not isinstance(ctx, dict) or not isinstance(ctx.get("effort_type"),str) or ctx.get("effort_type") not in {"easy", "steady"}:
            continue
        required = ("route_id", "terrain", "indoor", "time_convention")
        if any(ctx.get(k) is None for k in required) or not isinstance(ctx["indoor"], bool):
            continue
        if not isinstance(ctx["time_convention"],str) or ctx["time_convention"] not in {"elapsed", "moving"}:
            continue
        weather = a.weather_snapshot or {}
        env = [number(weather.get(k)) for k in ("temperature_c", "relative_humidity", "wind_speed_kmh")]
        if not ctx["indoor"] and any(v is None for v in env):
            continue
        return (provider, tuple(str(ctx[k]) for k in required), ctx["effort_type"], env)
    return None


def aerobic_trend(rows, streams, disciplines, timezone):
    eligible = []
    for a in sorted(rows, key=lambda a: (a.start_time, a.id)):
        context = comparable_context(a)
        intervals, longest = paired_intervals(streams.get(a.id, []))
        seconds = sum(dt for dt, _, _ in intervals)
        moving, _ = moving_time(a)
        reference = moving if context and context[1][-1] == "moving" else positive(a.duration_s)
        if (not context or not reference or (context[1][-1] == "moving" and moving is None)
            or not .9 <= seconds/reference <= 1.1 or longest < 1800 or not steady_effort(intervals)):
            continue
        speed = sum(dt*x for dt, x, _ in intervals)/seconds
        hr = sum(dt*y for dt, _, y in intervals)/seconds
        eligible.append((a, context, speed, hr))
    pair = None
    for later in reversed(eligible):
        for earlier in eligible:
            a, b = earlier[0], later[0]
            if a.start_time >= b.start_time or local_day(a, timezone) == local_day(b, timezone):
                continue
            if disciplines[a.id] != disciplines[b.id] or earlier[1][:3] != later[1][:3] or abs(earlier[3]-later[3]) > 3:
                continue
            indoor = earlier[1][1][2] == "True"
            if not indoor and any(abs(x-y) > tolerance for x,y,tolerance in zip(earlier[1][3], later[1][3], (3,10,5))):
                continue
            pair = earlier, later
            break
        if pair:
            break
    value, deps = None, []
    if pair:
        a, b = pair
        value = {"reference_activity_id": a[0].id, "current_activity_id": b[0].id,
            "reference_speed_m_s": a[2], "current_speed_m_s": b[2], "reference_hr_bpm": a[3], "current_hr_bpm": b[3],
            "speed_change_pct": (b[2]/a[2]-1)*100, "reference_date": local_day(a[0], timezone).isoformat(), "current_date": local_day(b[0], timezone).isoformat()}
        deps = [f"streams:{r[0].id}:speed,hr" for r in pair] + [f"activity:{r[0].id}:source_metrics,weather_snapshot" for r in pair]
    return outcome("comparable_easy_steady_speed_hr", value, "%", "(current_time_weighted_speed / reference_time_weighted_speed - 1) * 100",
        deps, reason="insufficient_comparable_easy_steady_recordings", quality={"eligible_activity_count": len(eligible), "comparison": "latest_eligible_vs_earliest_matching",
            "comparison_context_provenance":[{"activity_id":r[0].id,"provider":r[1][0],
                "assertion":(r[0].source_metrics.get(r[1][0],{}) or {}).get("provenance",{"kind":"recorded_context_verification_not_established"})} for r in pair] if pair else []},
        prerequisites=["explicit_easy_or_steady_context", "same_provider_discipline_route_terrain_indoor_and_time_convention", "HR_difference_at_most_3_bpm",
            "30min_contiguous_speed_HR", "90_percent_coverage", "time_weighted_speed_cv_at_most_10_percent", "outdoor_temperature_within_3C_humidity_10pp_wind_5kmh"],
        limitations=["descriptive_comparison_not_causal_progress", "recording_and_environment_confound", "eligibility_cutoffs_not_physiological_thresholds", "athlete_asserted_context_not_provider_verified"])


def goal_progress(focus, weekly, *, rows=(), streams=None, end=None, today=None,
        complete=True, streams_complete=True, profile_revision=None, strength=None):
    """Compare one explicit target with compatible recorded evidence only."""
    target = (focus or {}).get("measurable_goal")
    deps = [f"athlete_profile:{profile_revision}:context.focuses.measurable_goal"]
    value, unit, reason = None, "context", "no_explicit_measurable_progress_target"
    quality = {"history_complete":complete}
    formula = "recorded compatible measurement / explicit target * 100"
    if isinstance(target,dict) and positive(target.get("target")):
        key, goal = target.get("metric"), float(target["target"])
        measured, details = None, {}
        reason = "no_eligible_goal_measurement"
        if key in {"weekly_distance_km","weekly_duration_min"}:
            unit, attr, factor = ("km","distance_m",1000) if key == "weekly_distance_km" else ("min","duration_s",60)
            if end and today:
                # Most recent completed account-local Mon–Sun week, never a
                # clipped boundary or the in-progress current week.
                cutoff = min(end,today-timedelta(days=1))
                sunday = cutoff-timedelta(days=(cutoff.weekday()+1)%7)
                monday = sunday-timedelta(days=6)
                quality.update(window_start=monday.isoformat(),window_end=sunday.isoformat(),period="latest_completed_calendar_week")
                bucket = next((b for b in weekly if b["start"] == monday.isoformat() and b["end"] == sunday.isoformat()),None)
                observed = "distance" if attr == "distance_m" else "duration"
                if bucket and bucket["activity_count"] and bucket["observed"][observed] == bucket["activity_count"]:
                    measured = bucket[attr]/factor
                    deps.extend(bucket["source_dependencies"])
                else:
                    reason = "requires_complete_latest_calendar_week_measurements"
        elif key == "longest_distance_km":
            unit = "km"
            eligible = [a for a in rows if eligible_run(a)]
            # Missing distance/quality can hide a longer session.
            if len(eligible) != len(rows):
                reason = "incomplete_compatible_distance_measurements"
            elif eligible:
                winner = max(eligible,key=lambda a:(float(a.distance_m),a.start_time,a.id))
                measured = float(winner.distance_m)/1000
                details = {"activity_id":winner.id}
                deps.append(f"activity:{winner.id}:distance_m")
        elif key == "best_power_w":
            unit = "W"
            seconds = target.get("duration_s")
            if isinstance(seconds,int) and not isinstance(seconds,bool) and 1 <= seconds <= 3600:
                quality["duration_s"] = seconds
                candidates = [best_duration_power(a,(streams or {}).get(a.id,[]),durations=(seconds,))[0] for a in rows]
                candidates = [m for m in candidates if m["value"] is not None]
                if candidates and streams_complete:
                    winner = max(candidates,key=lambda m:m["value"])
                    measured = winner["value"]
                    details = {"activity_id":winner["quality"]["activity_id"],"duration_s":seconds}
                    deps.extend(winner["source_dependencies"])
                elif not streams_complete:
                    reason = "incomplete_power_stream_history"
            else:
                reason = "requires_explicit_power_duration_1_to_3600s"
        elif key == "exercise_estimated_1rm_kg":
            unit = "kg"
            sessions = [r for r in (strength or {}).get("sessions",[]) if r["exercise"] == target.get("exercise") and r["e1rm_kg"] is not None]
            if (strength or {}).get("history_complete") is False:
                reason = "incomplete_recorded_strength_history"
            elif len({r["exercise_id"] for r in sessions}) == 1:
                latest = max(sessions,key=lambda r:r["date"])
                earliest = min(sessions,key=lambda r:r["date"])
                measured = latest["e1rm_kg"]
                details = {"exercise":latest["exercise"],"exercise_id":latest["exercise_id"],"measured_on":latest["date"],
                    "reference_date":earliest["date"],"reference_estimate_kg":earliest["e1rm_kg"],
                    "change_pct":(measured/earliest["e1rm_kg"]-1)*100 if latest["date"] != earliest["date"] else None}
                deps.extend(latest["source_dependencies"]+earliest["source_dependencies"])
                quality["measurement_formula_version"] = strength.get("formula_version")
        else:
            reason = "unsupported_measurable_goal_metric"
        if not complete:
            reason, measured = "incomplete_activity_history", None
        if measured is not None:
            value = {"metric":key,"measurement":measured,"target":goal,"measurement_unit":unit,
                "progress_pct":measured/goal*100,**details}
    return outcome("goal_progress",value,unit,formula,list(dict.fromkeys(deps)),reason=reason,quality=quality,
        limitations=["saved_weekly_baseline_not_automatically_a_prescription", "no_mixed_quantity_progress_score",
            "recorded_history_not_proof_of_no_training", "target_attainment_not_event_performance_prediction"]
            + (["estimated_strength_not_tested_maximum", "same_catalog_exercise_only_equipment_and_technique_can_confound"] if unit == "kg" else []))


async def strength_overview(session, user, start=None, end=None, *, now=None):
    from app.services.gym_progression import recorded_sets, gym_progression
    start,end = date_bounds(start,end,user.timezone,now=now)
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(user.timezone)).date()
    rows,complete = await recorded_sets(session,user,start,min(end,today))
    # A future saved set is not an observed performance.
    rows = [(log,exercise) for log,exercise in rows if log.done_at <= (now or datetime.now(UTC))]
    progression = gym_progression(rows,user.timezone,complete=complete)
    profile = await session.get(AthleteProfile,user.id)
    focus = (profile.context or {}).get("focuses",{}).get("gym") if profile else None
    left,right = utc_bounds(start,end,user.timezone)
    activity_rows = (await session.scalars(select(Activity).join(Discipline,Discipline.id == Activity.discipline_id)
        .where(Activity.user_id == user.id,Discipline.name == "strength",Activity.start_time >= left,
            Activity.start_time < right,Activity.start_time <= (now or datetime.now(UTC)))
        .order_by(Activity.start_time.desc(),Activity.id.desc()).limit(ACTIVITY_LIMIT+1))).all()
    activity_complete = len(activity_rows) <= ACTIVITY_LIMIT
    activity_rows = activity_rows[:ACTIVITY_LIMIT]
    weekly = history_buckets(activity_rows,start,end,user.timezone)
    weekly_goal = ((focus or {}).get("measurable_goal") or {}).get("metric") == "weekly_duration_min"
    goal = goal_progress(focus,weekly,strength=progression,end=end,today=today,
        profile_revision=profile.revision if profile else None,complete=activity_complete if weekly_goal else complete)
    return {"sport":"strength","version":VERSION,"range":{"start":start.isoformat(),"end":end.isoformat(),"timezone":user.timezone},
        "state":"partial" if not complete or not activity_complete else "ready" if rows or activity_rows else "empty","progression":progression,
        "weekly":weekly,"quality":{"activity_history_complete":activity_complete,"set_history_complete":complete},
        "goal_context":{"focus":focus,"goal_progress":goal}}


def recent_body_mass(observations, at, *, excluded=(), complete=True):
    valid = [o for o in observations if o.id not in excluded and o.current
        and o.availability == "available" and o.unit == "kg"
        and valid_weight_kg((o.value or {}).get("value")) is not None
        and not o.quality_flags and at-timedelta(days=30) <= o.measured_at <= at]
    observation = max(valid, key=lambda o: (o.measured_at, o.id)) if valid and complete else None
    value = {"kg":float(observation.value["value"]), "measured_at":observation.measured_at.isoformat(),
        "origin":observation.origin, "acquisition":observation.acquisition,
        "user_asserted":observation.acquisition == "user_assertion", "revision":observation.revision} if observation else None
    return outcome("recent_body_mass",value,"kg","latest eligible recorded kg measurement at or before comparison time within 30 days",
        [f"observation:{observation.id}:{observation.revision}"] if observation else [], recorded=True,
        reason="incomplete_body_mass_history" if not complete else "missing_valid_recent_body_mass",
        quality={"at":at.isoformat(), "window_start":(at-timedelta(days=30)).isoformat(), "maximum_age_days":30},
        prerequisites=["current_available_owned_observation", "canonical_kg", "plausible_finite_body_mass", "no_quality_flags_or_analysis_exclusion"],
        limitations=["recorded_source_not_automatically_user_confirmed", "body_mass_varies_over_time"])


def stream_distribution(a, streams, field, width, unit):
    bins = defaultdict(float)
    seconds = 0
    for first, second in zip(streams, streams[1:]):
        dt = second.t_offset_s-first.t_offset_s
        value = valid_stream_value(field,getattr(first,field,None))
        if 0 <= first.t_offset_s < second.t_offset_s <= a.duration_s and dt <= 5 and value is not None:
            index = int(value//width)
            bins[index] += dt
            seconds += dt
    duration = positive(a.duration_s)
    valid = duration and .9 <= seconds/duration <= 1.1
    value = [{"lower":k*width,"upper":(k+1)*width,"duration_s":v,"unit":unit} for k,v in sorted(bins.items())] if valid else None
    return outcome(field+"_distribution",value,"s",f"sum(recorded interval seconds in [{width}-unit lower, upper) bins)",
        [f"streams:{a.id}:{field}"],reason="requires_90_percent_valid_stream_coverage",
        quality={"valid_seconds":seconds,"coverage":seconds/duration if duration else None},
        prerequisites=["sample_gaps_at_most_5s", "90_percent_stream_coverage"],limitations=["distribution_not_inferred_zones", "no_gap_interpolation"])



def recorded_running_dynamics(activity):
    """Exact unit-qualified sensor fields, kept separate for each provider."""
    records, dependencies = [], []
    for provider, block in list((activity.source_metrics or {}).items())[:16]:
        if not isinstance(block, dict) or not isinstance(block.get("running_dynamics"), dict):
            continue
        for field, (unit, lower, upper) in DYNAMICS_FIELDS.items():
            value = number(block["running_dynamics"].get(field))
            if value is not None and lower <= value <= upper:
                records.append({"provider": provider, "field": field, "value": value, "unit": unit})
                dependencies.append(f"activity:{activity.id}:source_metrics.{provider}.running_dynamics.{field}")
    return outcome("running_dynamics", records or None, "recorded units", "recorded sensor quantities without inference or cross-provider averaging",
        dependencies, recorded=True, reason="data_missing_recorded_unit_qualified_running_dynamics",
        quality={"activity_id": activity.id, "accepted_fields": list(DYNAMICS_FIELDS)},
        limitations=["sensor_and_provider_specific", "no_inferred_sensors", "current_importers_may_not_preserve_dynamics"],
        prerequisites=["explicit_unit_qualified_recorded_field", "finite_plausible_value"])


def distance_half_split(activity, streams, laps):
    """Prefer exact equal-distance lap boundaries; otherwise recorded speed integration."""
    distance, duration = positive(activity.distance_m), positive(activity.duration_s)
    halves, convention, method, deps = None, None, None, []
    ordered = sorted(laps, key=lambda lap: lap.lap_index)
    valid_laps = (len(ordered) >= 2 and len({lap.lap_index for lap in ordered}) == len(ordered)
        and all(positive(lap.distance_m) and positive(lap.duration_s) for lap in ordered))
    if valid_laps and distance:
        total_distance = sum(float(lap.distance_m) for lap in ordered)
        total_time = sum(float(lap.duration_s) for lap in ordered)
        # Canonical FIT laps store total_timer_time. Explicit alternative
        # conventions are supported only when every lap declares the same one.
        raw_conventions = [(getattr(lap,"extras",None) or {}).get("duration_convention","timer") for lap in ordered]
        conventions = set(raw_conventions) if all(isinstance(c,str) for c in raw_conventions) else set()
        first_distance, first_time = 0, 0
        if positive(total_distance) and positive(total_time) and len(conventions) == 1 and conventions <= {"timer","elapsed","moving"} and .95 <= total_distance/distance <= 1.05:
            for lap in ordered[:-1]:
                first_distance += float(lap.distance_m)
                first_time += float(lap.duration_s)
                if abs(first_distance-total_distance/2) <= .01:
                    halves = (first_distance, first_time, total_distance-first_distance, total_time-first_time)
                    convention, method = next(iter(conventions)), "recorded_equal_distance_laps"
                    deps = [f"laps:{activity.id}:distance_m,duration_s"]
                    break
    if halves is None and distance and duration:
        intervals, seconds, integrated_distance = [], 0, 0
        for first, second in zip(streams,streams[1:]):
            dt = second.t_offset_s-first.t_offset_s
            speed = valid_stream_value("speed",getattr(first,"speed",None))
            if 0 <= first.t_offset_s < second.t_offset_s <= duration and dt <= 5 and speed is not None:
                intervals.append((dt,speed))
                seconds += dt
                integrated_distance += dt*speed
            else:
                intervals = []
                break
        # Require complete elapsed coverage: no joining disconnected samples,
        # no moving-time corrections and no extrapolating the final sample.
        if intervals and abs(seconds-duration) <= .01 and .95 <= integrated_distance/distance <= 1.05:
            target, travelled, first_time = integrated_distance/2, 0, 0
            for dt,speed in intervals:
                segment_distance = dt*speed
                used = dt if travelled+segment_distance <= target else (target-travelled)/speed if speed else dt
                first_time += max(0,used)
                travelled += segment_distance
                if travelled >= target:
                    break
            if 0 < first_time < seconds:
                halves = (target,first_time,target,seconds-first_time)
                convention, method = "elapsed", "recorded_speed_sample_hold_integration"
                deps = [f"streams:{activity.id}:speed,t_offset_s",f"activity:{activity.id}:distance_m,duration_s"]
    value = None
    if halves:
        d1,t1,d2,t2 = halves
        first_pace, second_pace = t1/d1*1000,t2/d2*1000
        change = (second_pace/first_pace-1)*100
        value = {"activity_id":activity.id,"first_distance_m":d1,"second_distance_m":d2,
            "first_duration_s":t1,"second_duration_s":t2,"first_pace_s_km":first_pace,"second_pace_s_km":second_pace,
            "pace_change_pct":change,"classification":"positive" if change > 1e-9 else "negative" if change < -1e-9 else "even",
            "duration_convention":convention,"method":method}
    return outcome("distance_half_split",value,"%","(second_equal_distance_half_pace / first_equal_distance_half_pace - 1) * 100",
        deps,reason="data_missing_equal_distance_laps_or_complete_speed_stream",
        quality={"method":method,"lap_count":len(laps)},prerequisites=["positive_distance_and_duration", "95_to_105_percent_distance_agreement", "exact_equal_distance_lap_boundary_or_complete_elapsed_speed_coverage"],
        limitations=["positive_means_slower_second_half", "terrain_and_session_intent_confound", "stream_method_sample_hold_approximation", "lap_timer_not_automatically_elapsed_time"])


def lap_average_distribution(activity, laps, field, width, unit):
    """A histogram of recorded lap MEANS, not a sensor-sample distribution."""
    values = []
    for lap in laps:
        seconds = positive(lap.duration_s)
        value = valid_stream_value(field,getattr(lap,"avg_"+field,None))
        if value is None and field == "cadence":
            value = valid_stream_value("cadence",(getattr(lap,"extras",None) or {}).get("avg_cadence"))
        if seconds and value is not None:
            values.append((lap.lap_index,seconds,value))
    bins = defaultdict(float)
    for _,seconds,value in values:
        bins[int(value//width)] += seconds
    duration = positive(activity.duration_s)
    coverage = sum(v[1] for v in values)/duration if duration else None
    unique = len({v[0] for v in values}) == len(values)
    available = coverage is not None and .9 <= coverage <= 1.1 and unique
    return outcome(field+"_lap_average_distribution", [{"lower":k*width,"upper":(k+1)*width,"duration_s":v,"unit":unit} for k,v in sorted(bins.items())] if available else None,
        "s", "sum(recorded lap timer seconds grouped by recorded lap mean)", [f"laps:{activity.id}:duration_s,avg_{field}"],
        reason="data_missing_valid_90_percent_lap_average_coverage",quality={"coverage":coverage,"lap_count":len(values),"duration_convention":"lap_timer"},
        limitations=["lap_means_are_not_sample_distribution", "lap_timer_and_activity_duration_may_differ"],prerequisites=["unique_lap_indices", "90_to_110_percent_coverage"])


def cadence_relationship(activity, streams, *, cycling=False):
    pairs = [("cadence","hr")]+([("cadence","power"),("power","hr")] if cycling else [])
    results = []
    for first_field,second_field in pairs:
        samples, longest, continuous = [], 0, 0
        for a,b in zip(streams,streams[1:]):
            dt = b.t_offset_s-a.t_offset_s
            x = valid_stream_value(first_field,getattr(a,first_field,None))
            y = valid_stream_value(second_field,getattr(a,second_field,None))
            if 0 <= a.t_offset_s < b.t_offset_s <= activity.duration_s and dt <= 5 and x is not None and y is not None:
                samples.append((dt,x,y))
                continuous += dt
                longest = max(longest,continuous)
            else:
                continuous = 0
        seconds = sum(dt for dt,_,_ in samples)
        duration = positive(activity.duration_s)
        correlation = None
        reason = "data_missing_continuous_paired_streams"
        if duration and .9 <= seconds/duration <= 1.1 and longest >= 300:
            mx = sum(dt*x for dt,x,_ in samples)/seconds
            my = sum(dt*y for dt,_,y in samples)/seconds
            vx = sum(dt*(x-mx)**2 for dt,x,_ in samples)/seconds
            vy = sum(dt*(y-my)**2 for dt,_,y in samples)/seconds
            if vx > 0 and vy > 0:
                covariance = sum(dt*(x-mx)*(y-my) for dt,x,y in samples)/seconds
                correlation = max(-1,min(1,covariance/sqrt(vx*vy)))
            else:
                reason = "insufficient_recorded_variation"
        results.append({"first":first_field,"second":second_field,"correlation":correlation,"valid_seconds":seconds,"unavailable_reason":reason if correlation is None else None})
    return outcome("cadence_hr_power_relationship",results if any(r["correlation"] is not None for r in results) else None,"Pearson r",
        "time_weighted_covariance(x,y) / sqrt(time_weighted_variance(x) * time_weighted_variance(y))",
        [f"streams:{activity.id}:cadence,hr"+(",power" if cycling else "")],reason="data_missing_paired_streams_or_insufficient_variation",
        quality={"pairs":results},prerequisites=["90_percent_pair_coverage", "5min_continuous_recording", "sample_gaps_at_most_5s", "nonzero_recorded_variance"],
        limitations=["observational_relationship_not_causality", "cadence_convention_provider_specific", "not_an_optimal_cadence_prescription"])


def critical_speed(history, at, *, complete=True):
    """Distance-time OLS only on explicitly verified maximal protocol records."""
    groups = defaultdict(list)
    lower = at.astimezone(UTC)-timedelta(days=180)
    for a in history:
        if not eligible_run(a) or not lower <= a.start_time.astimezone(UTC) <= at:
            continue
        for provider,block in list((a.source_metrics or {}).items())[:16]:
            effort = block.get("verified_performance") if isinstance(block,dict) else None
            if not isinstance(effort,dict) or effort.get("verified") is not True or effort.get("maximal") is not True:
                continue
            if any(not isinstance(effort.get(k),str) for k in ("protocol","duration_convention","distance_unit","duration_unit","surface","distance_method")):
                continue
            distance,duration = positive(effort.get("distance_m")),positive(effort.get("duration_s"))
            if (effort.get("protocol") not in {"race","time_trial"} or effort.get("duration_convention") != "elapsed"
                or effort.get("distance_unit") != "m" or effort.get("duration_unit") != "s"
                or effort.get("surface") not in {"flat_road","track","treadmill"}
                or effort.get("distance_method") not in {"certified_course","track_laps","calibrated_treadmill"}
                or distance is None or duration is None or not 180 <= duration <= 1200 or distance > 30000
                or distance > float(a.distance_m)*1.05 or duration > float(a.duration_s)*1.05):
                continue
            key = (provider,effort["surface"],effort["distance_method"],effort["duration_convention"])
            groups[key].append((a,duration,distance,effort["protocol"]))
    eligible = [(key,points) for key,points in groups.items() if len({p[0].id for p in points}) >= 3
        and len({p[1] for p in points}) >= 3 and len({p[2] for p in points}) >= 3
        and max(p[1] for p in points)-min(p[1] for p in points) >= 300
        and max(p[1] for p in points)/min(p[1] for p in points) >= 2]
    eligible.sort(key=lambda item:(-len(item[1]),-max(p[0].start_time.timestamp() for p in item[1]),item[0]))
    value,deps = None,[]
    reason = "incomplete_verified_performance_history" if not complete else "insufficient_protocol_qualified_performances"
    fit_quality = {}
    if complete and eligible:
        key,points = eligible[0]
        mt = sum(p[1] for p in points)/len(points)
        md = sum(p[2] for p in points)/len(points)
        variance_t = sum((p[1]-mt)**2 for p in points)
        slope = sum((p[1]-mt)*(p[2]-md) for p in points)/variance_t
        intercept = md-slope*mt
        residual = sum((p[2]-(slope*p[1]+intercept))**2 for p in points)
        total = sum((p[2]-md)**2 for p in points)
        r2 = 1-residual/total if total else None
        fit_quality = {"r_squared":r2,"fit_count":len(points),"duration_min_s":min(p[1] for p in points),"duration_max_s":max(p[1] for p in points),"provider":key[0],"surface":key[1],"distance_method":key[2]}
        deps = [f"activity:{p[0].id}:source_metrics.{key[0]}.verified_performance" for p in points]
        if positive(slope) and slope <= 12 and number(intercept) is not None and intercept >= 0 and r2 is not None and r2 >= .95:
            value = {"speed_m_s":slope,"distance_intercept_m":intercept,"r_squared":r2,"activity_ids":[p[0].id for p in points],"protocols":[p[3] for p in points],"method":"OLS_distance_equals_speed_times_elapsed_time_plus_intercept","estimated":True}
        else:
            reason = "protocol_records_fail_distance_time_model_fit"
    return outcome("critical_speed",value,"m/s","OLS slope = sum((elapsed_s-mean_elapsed_s)*(distance_m-mean_distance_m)) / sum((elapsed_s-mean_elapsed_s)^2)",
        deps,reason=reason,quality={"window_start":lower.isoformat(),"window_end":at.isoformat(),"window_days":180,**fit_quality},
        prerequisites=["3_distinct_owned_verified_maximal_race_or_time_trial_activities", "elapsed_s_and_metre_conventions", "same_provider_surface_distance_method", "3_to_20_min_efforts", "duration_span_at_least_300s_and_ratio_at_least_2", "R_squared_at_least_0.95", "positive_slope_nonnegative_intercept"],
        limitations=["estimated_distance_time_model_not_direct_physiological_measurement", "recorded_verification_not_independent_protocol_audit", "no_extrapolated_race_prediction", "fit_cutoffs_are_implementation_eligibility"])


def efficiency_retention(activity, streams, *, cycling=False):
    """Descriptive early/late retention, never a direct fatigue measurement."""
    context = comparable_context(activity)
    field = "power" if cycling else "speed"
    paired,longest = paired_intervals(streams,first=field,second="hr",allow_zero_first=cycling)
    seconds = sum(dt for dt,_,_ in paired)
    moving,_ = moving_time(activity)
    reference = moving if context and context[1][-1] == "moving" else positive(activity.duration_s)
    valid = context and reference and .9 <= seconds/reference <= 1.1 and longest >= 1800 and steady_effort(paired)
    if cycling and moving and moving < activity.duration_s:
        # A power-only interval cannot verify moving continuity across pauses.
        valid = valid and all(positive(getattr(a,"speed",None)) for a in streams[:-1])
    halves = half_means(paired) if valid else None
    value = None
    if halves and all(x > 0 and hr > 0 for x,hr in halves):
        early,late = halves[0][0]/halves[0][1],halves[1][0]/halves[1][1]
        value = {"activity_id":activity.id,"earlier_efficiency":early,"later_efficiency":late,"efficiency_unit":"W/bpm" if cycling else "m/s/bpm",
            "retention_pct":late/early*100,"change_pct":(late/early-1)*100,"method":"equal_recorded_moving_time_halves","interpretation":"descriptive_efficiency_retention_proxy"}
    return outcome("fatigue_resistance" if cycling else "endurance_durability",value,"%",
        "(late_half_time_weighted_effort / late_half_time_weighted_HR) / (early_half_time_weighted_effort / early_half_time_weighted_HR) * 100",
        [f"streams:{activity.id}:{field},hr",f"activity:{activity.id}:source_metrics.comparison_context"],reason="data_missing_compatible_30min_steady_effort",
        quality={"paired_seconds":seconds,"continuous_seconds":longest,"activity_id":activity.id},
        prerequisites=["explicit_easy_or_steady_context", "90_percent_paired_coverage", "30min_continuous_recording", "effort_CV_at_most_10_percent"],
        limitations=["descriptive_efficiency_proxy_not_measured_durability_or_fatigue", "HR_environment_hydration_and_intent_confound", "no_exhaustion_or_injury_prediction"])


def route_progress(rows, streams, disciplines, timezone):
    metric = aerobic_trend(rows,streams,disciplines,timezone)
    metric["key"] = "comparable_route_performance"
    metric["unavailable_reason"] = "data_missing_compatible_recorded_route_environment_and_steady_effort" if metric["value"] is None else None
    metric["limitations"].append("same_explicit_route_identity_only_no_GPS_route_guess")
    return metric


def climb_progress(rows, disciplines, at):
    groups = defaultdict(list)
    scanned = 0
    for a in rows:
        if scanned >= ADVANCED_SEGMENT_BUDGET:
            break
        if a.start_time > at:
            continue
        for provider,block in list((a.source_metrics or {}).items())[:16]:
            segments = block.get("climb_segments") if isinstance(block,dict) else None
            if not isinstance(segments,list):
                continue
            for index,segment in enumerate(segments[:100]):
                if scanned >= ADVANCED_SEGMENT_BUDGET:
                    break
                scanned += 1
                if not isinstance(segment,dict) or segment.get("verified") is not True or segment.get("duration_convention") != "elapsed":
                    continue
                ascent,duration,distance = (positive(segment.get(k)) for k in ("ascent_m","duration_s","distance_m"))
                context = segment.get("comparison_context")
                if not ascent or ascent > 20000 or not duration or duration < 1 or not distance or distance > 100000 or not isinstance(context,dict):
                    continue
                required = ("segment_id","terrain","effort_type","temperature_c","relative_humidity","wind_speed_kmh")
                if any(context.get(k) is None for k in required) or not isinstance(context.get("effort_type"),str) or context.get("effort_type") not in {"easy","steady","maximal"}:
                    continue
                env = [number(context.get(k)) for k in required[-3:]]
                if any(v is None for v in env) or duration > a.duration_s or distance > (positive(a.distance_m) or 0) or ascent > (positive(a.elevation_gain_m) or 0):
                    continue
                key = (provider,disciplines[a.id],str(context["segment_id"]),str(context["terrain"]),context["effort_type"])
                groups[key].append((a,index,ascent,duration,distance,env))
    pair,key = None,None
    for candidate_key,entries in sorted(groups.items()):
        entries.sort(key=lambda e:(e[0].start_time,e[0].id,e[1]))
        for later in reversed(entries):
            for earlier in entries:
                if earlier[0].id == later[0].id or earlier[0].start_time >= later[0].start_time:
                    continue
                if abs(earlier[2]/later[2]-1) > .02 or abs(earlier[4]/later[4]-1) > .02:
                    continue
                if any(abs(x-y) > tolerance for x,y,tolerance in zip(earlier[5],later[5],(3,10,5))):
                    continue
                if pair is None or later[0].start_time > pair[1][0].start_time:
                    pair,key = (earlier,later),candidate_key
                break
    value,deps = None,[]
    if pair:
        earlier,later = pair
        first,second = earlier[2]/earlier[3]*3600,later[2]/later[3]*3600
        value = {"reference_activity_id":earlier[0].id,"current_activity_id":later[0].id,"segment_id":key[2],
            "reference_ascent_rate_m_h":first,"current_ascent_rate_m_h":second,"change_pct":(second/first-1)*100,
            "reference_ascent_m":earlier[2],"current_ascent_m":later[2],"reference_duration_s":earlier[3],"current_duration_s":later[3]}
        deps = [f"activity:{p[0].id}:source_metrics.{key[0]}.climb_segments[{p[1]}]" for p in pair]
    return outcome("climbing_performance",value,"%","(current_verified_segment_ascent_m / current_elapsed_s) / (reference_verified_segment_ascent_m / reference_elapsed_s) * 100 - 100",
        deps,reason="data_missing_verified_matching_climb_segments_and_context",quality={"eligible_segment_groups":len(groups),"segment_scan_budget":ADVANCED_SEGMENT_BUDGET,"budget_reached":scanned >= ADVANCED_SEGMENT_BUDGET},
        prerequisites=["same_verified_provider_discipline_segment_terrain_effort_type", "distance_and_ascent_within_2_percent", "elapsed_time_convention", "temperature_within_3C_humidity_10pp_wind_5kmh"],
        limitations=["recorded_segment_identity_not_GPS_guess", "no_grade_adjusted_model", "ascent_sensor_error_and_environment_confound", "implementation_matching_cutoffs_not_physiological_thresholds"])


def unsupported(sport):
    reasons = {"grade_adjusted_pace": "unsupported_model_no_validated_grade_adjustment"} if sport == "running" else {}
    return [outcome(key, None, "context", "not_computed", reason=reason,
        limitations=["unsupported_inputs_or_method_not_inferred"]) for key,reason in reasons.items()]


def ftp_assertion_history(entries,start,end,*,complete=True):
    records,deps = [],[]
    for entry in sorted(entries,key=lambda e:(e.date,e.id)):
        payload = entry.payload or {}
        watts = positive(payload.get("watts"))
        if watts is None or watts > 2000 or payload.get("source") != "user_confirmed" or not start <= entry.date <= end:
            continue
        if payload.get("measured_on") != entry.date.isoformat():
            continue
        records.append({"entry_id":entry.id,"watts":watts,"measured_on":entry.date.isoformat(),"source":"user_confirmed",
            "threshold_source":payload.get("threshold_source","manual"), "methodology":payload.get("methodology"),
            "source_reference":payload.get("source_reference"), "protocol":payload.get("protocol"),
            "recorded_at":entry.created_at.isoformat(),"method":"explicit_dated_profile_assertion","profile_revision":payload.get("profile_revision")})
        deps.append(f"athlete_entry:{entry.id}:{entry.revision}")
    return outcome("ftp_trend",records if records and complete else None,"W","accepted dated confirmed profile assertions ordered by measurement date and assertion ID",
        deps,recorded=True,reason="incomplete_ftp_assertion_history" if not complete else "data_missing_accepted_ftp_assertion_history",
        quality={"window_start":start.isoformat(),"window_end":end.isoformat(),"history_complete":complete},
        limitations=["user_confirmation_not_protocol_validation", "no_retroactive_history_backfill", "legacy_fractional_20min_estimates_not_merged"])


async def sport_overview(session, user, sport, start=None, end=None, *, now=None):
    start, end = date_bounds(start, end, user.timezone, now=now)
    left, right = utc_bounds(start, end, user.timezone)
    if sport == "running":
        # Critical-speed protocol history is independent of the display range.
        # Keep the exact long-run lookback too when a longer range is requested.
        left = min(left-timedelta(days=30), right-timedelta(days=180))
    query = (select(Activity, Discipline.name).join(Discipline, Discipline.id == Activity.discipline_id)
        .where(Activity.user_id == user.id, Discipline.name.in_(SPORTS[sport]), Activity.start_time >= left, Activity.start_time < right)
        .order_by(Activity.start_time.desc(), Activity.id.desc()).limit(ACTIVITY_LIMIT+1))
    loaded = (await session.execute(query)).all()
    truncated = len(loaded) > ACTIVITY_LIMIT
    loaded = loaded[:ACTIVITY_LIMIT]
    history = [a for a,_ in loaded]
    names = {a.id:name for a,name in loaded}
    rows = [a for a in history if start <= local_day(a, user.timezone) <= end]
    ids = [a.id for a in rows]
    id_set = set(ids)
    profile = await session.get(AthleteProfile, user.id)
    context = profile.context if profile else {}
    counts = dict((await session.execute(select(ActivityStream.activity_id, func.count()).join(Activity, Activity.id == ActivityStream.activity_id)
        .where(Activity.user_id == user.id, Activity.id.in_(ids)).group_by(ActivityStream.activity_id))).all()) if ids else {}
    selected, remaining = [], STREAM_BUDGET
    for a in rows:
        count = counts.get(a.id, 0)
        if 0 < count <= remaining:
            selected.append(a.id)
            remaining -= count
    selected_set = set(selected)
    budget_exceeded = any(counts.get(a.id, 0) > 0 and a.id not in selected_set for a in rows)
    streams = defaultdict(list)
    if selected:
        raw = (await session.scalars(select(ActivityStream).join(Activity, Activity.id == ActivityStream.activity_id)
            .where(Activity.user_id == user.id, Activity.id.in_(selected)).order_by(ActivityStream.activity_id, ActivityStream.t_offset_s)
            .limit(STREAM_BUDGET+1))).all()
        # Concurrent stream enrichment cannot turn a truncated row set into an exact metric.
        actual_counts = Counter(r.activity_id for r in raw)
        if len(raw) > STREAM_BUDGET or any(actual_counts[aid] != counts[aid] for aid in selected):
            budget_exceeded = True
        else:
            for r in raw:
                streams[r.activity_id].append(r)
    recent_ids = ids[:RECENT_LIMIT]
    laps = defaultdict(list)
    raw_laps = (await session.scalars(select(ActivityLap).join(Activity, Activity.id == ActivityLap.activity_id)
        .where(Activity.user_id == user.id, Activity.id.in_(recent_ids)).order_by(ActivityLap.activity_id, ActivityLap.lap_index)
        .limit(LAP_BUDGET+1))).all() if recent_ids else []
    lap_exceeded = len(raw_laps) > LAP_BUDGET
    if not lap_exceeded:
        for lap in raw_laps:
            laps[lap.activity_id].append(lap)
    # Plans have an owned parent; same-day coincidence never supplies an association.
    planned_rows = (await session.execute(select(PlannedSession, TrainingPlan).join(TrainingPlan, TrainingPlan.id == PlannedSession.training_plan_id)
        .join(Discipline, Discipline.id == PlannedSession.discipline_id).where(TrainingPlan.user_id == user.id,
            TrainingPlan.status.in_(("confirmed", "active", "completed")), Discipline.name.in_(SPORTS[sport]),
            PlannedSession.date >= start, PlannedSession.date <= end).order_by(PlannedSession.date, PlannedSession.id).limit(ACTIVITY_LIMIT+1))).all()
    plan_truncated = len(planned_rows) > ACTIVITY_LIMIT
    planned = [p for p,plan in planned_rows[:ACTIVITY_LIMIT]
        if (not plan.activated_on or p.date >= plan.activated_on) and (not plan.superseded_on or p.date < plan.superseded_on)]
    links = (await session.scalars(select(ActivityPlanLink).join(Activity, Activity.id == ActivityPlanLink.activity_id)
        .where(ActivityPlanLink.user_id == user.id, Activity.user_id == user.id, Activity.id.in_(ids)).limit(ACTIVITY_LIMIT+1))).all() if ids else []
    plan_ids = [p.id for p in planned]
    from sqlalchemy import or_
    check_conditions = []
    if ids:
        check_conditions.append(SessionCheckin.activity_id.in_(ids))
    if plan_ids:
        check_conditions.append(SessionCheckin.planned_session_id.in_(plan_ids))
    checks = (await session.scalars(select(SessionCheckin).where(SessionCheckin.user_id == user.id, or_(*check_conditions))
        .order_by(SessionCheckin.id.desc()).limit(ACTIVITY_LIMIT*2+1))).all() if check_conditions else []
    check_truncated = len(checks) > ACTIVITY_LIMIT*2
    link_truncated = len(links) > ACTIVITY_LIMIT
    checks_by_activity = {}
    for c in checks:
        if c.activity_id in id_set:
            checks_by_activity.setdefault(c.activity_id,c)
    links_by_activity = {l.activity_id:l for l in links if l.method == "user_confirmed"}
    recent = []
    for a in rows[:RECENT_LIMIT]:
        check = checks_by_activity.get(a.id)
        day = local_day(a, user.timezone)
        kwargs = {"context": context, "activity_day": day, "profile_revision": profile.revision if profile else None,
            "rpe": check.rpe if check else None, "rpe_dependency": f"checkin:{check.id}:{check.revision}" if check else None}
        calc = running_metrics if sport == "running" else cycling_metrics
        metrics = calc(a, streams[a.id], laps[a.id], **kwargs)
        if sport == "running":
            metrics.extend([recorded_running_dynamics(a),distance_half_split(a,streams[a.id],laps[a.id])])
        metrics.append(cadence_relationship(a,streams[a.id],cycling=sport == "cycling"))
        if sport == "cycling":
            efficiency = next(m for m in running_metrics(a,streams[a.id],[],**kwargs) if m["key"] == "aerobic_efficiency")
            efficiency["key"] = "cycling_speed_hr_efficiency"
            efficiency["limitations"].extend(["speed_affected_by_coasting_wind_surface_and_bicycle", "HR_only_mode"])
            metrics.append(efficiency)
        from app.services.interval_detection import automatic_intervals
        metrics.append(automatic_intervals(a,streams[a.id],field="power" if sport == "cycling" and any(r.power is not None for r in streams[a.id]) else "speed", complete=len(streams[a.id]) == counts.get(a.id,0)))
        metrics.extend(stream_distribution(a,streams[a.id],field,width,unit) for field,width,unit in
            (("hr",10,"bpm"),("speed",1,"m/s"),("cadence",10,"cadence/min")) + ((("power",50,"W"),) if sport == "cycling" else ()))
        metrics.extend(lap_average_distribution(a,laps[a.id],field,width,unit) for field,width,unit in
            (("hr",10,"bpm"),("cadence",10,"cadence/min")) + ((("power",50,"W"),) if sport == "cycling" else ()))
        for m in metrics:
            m["quality"] = {**m.get("quality",{}), "stream_rows": len(streams[a.id]), "stream_budget_excluded": a.id not in selected_set and counts.get(a.id, 0) > 0, "lap_budget_exceeded": lap_exceeded}
        recent.append({"id": a.id, "date": day.isoformat(), "start_time": a.start_time.isoformat(), "discipline": names[a.id],
            "distance_m": positive(a.distance_m, zero=True), "duration_s": positive(a.duration_s, zero=True),
            "elevation_gain_m": positive(a.elevation_gain_m, zero=True), "avg_hr": positive(a.avg_hr), "avg_power": positive(a.avg_power, zero=True),
            "metrics": metrics, "source_metrics": a.source_metrics, "weather": a.weather_snapshot,
            "checkin": {k:getattr(check,k) for k in ("status", "rpe", "pain", "felt_unwell", "fatigue", "soreness", "workout_quality", "modification_reason", "terrain_notes", "note")} if check else None,
            "planned_session_id": links_by_activity[a.id].planned_session_id if a.id in links_by_activity else None})
    weekly = history_buckets(rows, start, end, user.timezone)
    focus = context.get("focuses", {}).get(sport)
    mass_at = min(right-timedelta(microseconds=1), now or datetime.now(UTC))
    mass_rows = (await session.scalars(select(Observation).where(Observation.user_id == user.id,
        Observation.metric == "weight", Observation.current.is_(True), Observation.measured_at >= left-timedelta(days=30),
        Observation.measured_at <= mass_at).order_by(Observation.measured_at.desc(),Observation.id.desc()).limit(ACTIVITY_LIMIT+1))).all() if sport == "cycling" else []
    mass_complete = len(mass_rows) <= ACTIVITY_LIMIT
    mass_rows = mass_rows[:ACTIVITY_LIMIT]
    mass_ids = [o.id for o in mass_rows]
    annotation_observation_id = AthleteEntry.payload["observation_id"].as_integer()
    annotations = (await session.scalars(select(AthleteEntry).where(AthleteEntry.user_id == user.id,
        AthleteEntry.kind == "observation_annotation", annotation_observation_id.in_(mass_ids))
        .distinct(annotation_observation_id)
        .order_by(annotation_observation_id,AthleteEntry.id.desc()).limit(ACTIVITY_LIMIT+1))).all() if mass_ids else []
    mass_complete = mass_complete and len(annotations) <= ACTIVITY_LIMIT
    excluded_mass = {a.payload["observation_id"] for a in annotations if a.payload.get("exclude_from_analysis")}
    mass = recent_body_mass(mass_rows,mass_at,excluded=excluded_mass,complete=mass_complete)
    ftp, ftp_reason, measured = confirmed_ftp(context, end)
    ftp_out = outcome("confirmed_ftp", {"watts": ftp, "measured_on": measured.isoformat(), "mode": "manually_confirmed" if (context.get("ftp") or {}).get("source","manual") == "manual" else (context.get("ftp") or {}).get("source"), "source": "athlete_profile", "confirmed": True,
        "threshold_source":(context.get("ftp") or {}).get("source","manual"), "methodology":(context.get("ftp") or {}).get("methodology"),
        "source_reference":(context.get("ftp") or {}).get("source_reference"), "protocol":(context.get("ftp") or {}).get("protocol")} if ftp else None,
        "W", "explicitly_confirmed_profile_FTP_not_estimated", [f"athlete_profile:{profile.revision}:ftp"] if profile else [],
        recorded=True, reason=ftp_reason, quality={"maximum_age_days":90,"threshold_eligible":ftp is not None,
            "recorded_assertion":{k:(context.get("ftp") or {}).get(k) for k in ("watts","measured_on","confirmed","source","methodology","source_reference","protocol")}}, limitations=["confirmation_not_protocol_validation", "no_historical_threshold_series"])
    wkg = outcome("confirmed_ftp_watts_per_kg", ftp/mass["value"]["kg"] if ftp and mass["value"] else None,"W/kg",
        "explicitly_confirmed_FTP_watts / latest_eligible_recent_body_mass_kg",ftp_out["source_dependencies"]+mass["source_dependencies"],
        reason=ftp_reason or mass["unavailable_reason"],quality={"body_mass":mass["value"],"mass_window_days":30,"comparison_at":mass_at.isoformat()},
        limitations=["FTP_confirmation_not_protocol_validation", "recorded_mass_not_automatically_user_confirmed"])
    curve = power_curve(rows,streams,complete=not truncated and not budget_exceeded) if sport == "cycling" else []
    for point in curve:
        aid = point["quality"].get("activity_id")
        a = next((a for a in rows if a.id == aid),None)
        point_mass = recent_body_mass(mass_rows,a.start_time,excluded=excluded_mass,complete=mass_complete) if a else None
        point["quality"]["watts_per_kg"] = point["value"]/point_mass["value"]["kg"] if point["value"] is not None and point_mass and point_mass["value"] else None
        point["quality"]["body_mass"] = point_mass["value"] if point_mass else None
        point["quality"]["watts_per_kg_formula"] = "same_activity_best_recorded_mean_power_W / recent_body_mass_kg_at_activity_start"
        point["quality"]["body_mass_window_days"] = 30
        if point_mass:
            point["source_dependencies"].extend(point_mass["source_dependencies"])
    limitations = ["recorded_history_not_proof_of_no_training", "missing_measurements_not_zero", "provider_load_scales_kept_separate"]
    if truncated:
        limitations.append("activity_history_truncated_at_10000")
    if budget_exceeded:
        limitations.append("stream_budget_exceeded_recent_complete_activities_prioritized")
    if lap_exceeded:
        limitations.append("lap_budget_exceeded_split_metrics_unavailable")
    if plan_truncated:
        limitations.append("planned_session_history_truncated")
    if not mass_complete:
        limitations.append("body_mass_history_truncated")
    if check_truncated or link_truncated:
        limitations.append("feedback_or_association_history_truncated")
    day_index = defaultdict(list)
    for a in history:
        if eligible_run(a):
            day_index[local_day(a,user.timezone)].append(a)
    retention = [efficiency_retention(a,streams[a.id],cycling=sport == "cycling") for a in rows]
    available_retention = next((m for m in retention if m["value"] is not None),None)
    retention_out = available_retention or outcome("fatigue_resistance" if sport == "cycling" else "endurance_durability",None,"%",
        "late_half_effort_HR_efficiency / early_half_effort_HR_efficiency * 100",reason="data_missing_compatible_30min_steady_effort",
        limitations=["descriptive_efficiency_proxy_not_measured_durability_or_fatigue"])
    advanced = unsupported(sport)+[retention_out,route_progress(rows,streams,names,user.timezone),climb_progress(rows,names,mass_at)]
    if sport == "running":
        advanced.append(critical_speed(history,mass_at,complete=not truncated))
    else:
        advanced.append(wkg)
        ftp_history = (await session.scalars(select(AthleteEntry).where(AthleteEntry.user_id == user.id,
            AthleteEntry.kind == "ftp_assertion",AthleteEntry.date >= start,AthleteEntry.date <= min(end,mass_at.astimezone(ZoneInfo(user.timezone)).date()))
            .order_by(AthleteEntry.date.desc(),AthleteEntry.id.desc()).limit(ACTIVITY_LIMIT+1))).all()
        advanced.append(ftp_assertion_history(ftp_history[:ACTIVITY_LIMIT],start,end,complete=len(ftp_history) <= ACTIVITY_LIMIT))
    return {"sport": sport, "version": VERSION, "range": {"start":start.isoformat(), "end":end.isoformat(), "timezone":user.timezone},
        "state": "partial" if truncated or budget_exceeded or lap_exceeded or plan_truncated or check_truncated or link_truncated or not mass_complete else "ready" if rows else "empty",
        "quality": {"activity_limit_reached":truncated, "stream_budget_exceeded":budget_exceeded, "limitations":limitations},
        "totals":volume_bucket(rows,start,end), "weekly":weekly, "monthly":history_buckets(rows,start,end,user.timezone,monthly=True),
        "recent_activities":recent, "best_efforts":recorded_best_efforts(rows),
        "power_duration":curve,
        "long_run_progression":[long_run_progression(a,history,user.timezone,complete=not truncated,day_index=day_index) for a in rows] if sport == "running" else [],
        "aerobic_trend":aerobic_trend(rows,streams,names,user.timezone), "consistency":consistency(rows,weekly,user.timezone,complete=not truncated),
        "adherence":adherence(planned,links,checks,rows,min(end,(now or datetime.now(UTC)).astimezone(ZoneInfo(user.timezone)).date()),complete=not truncated and not plan_truncated and not link_truncated and not check_truncated),
        "goal_context":{"training_focus":profile.training_focus if profile else [], "focus":focus, "goal_progress":goal_progress(focus,weekly,rows=[a for a in rows if a.start_time <= (now or datetime.now(UTC))],streams=streams,end=end,today=(now or datetime.now(UTC)).astimezone(ZoneInfo(user.timezone)).date(),complete=not truncated,streams_complete=not budget_exceeded,profile_revision=profile.revision if profile else None),"focus_configuration":focus_configuration(profile,end)},
        "ftp":ftp_out if sport == "cycling" else outcome("confirmed_ftp",None,"W","not_applicable",reason="not_applicable_to_running"),
        "body_mass":mass if sport == "cycling" else outcome("recent_body_mass",None,"kg","not_applicable",reason="not_applicable_to_running"),
        "advanced_metrics":advanced}
