"""Versioned descriptive endurance metrics; absent inputs are never synthesized.

The API computes from the current raw rows, so corrected streams/laps cannot
leave stale derived values behind. No thresholds, power or predictions inferred.
"""
from math import isfinite, sqrt
from statistics import mean, pstdev
from app.services.activity_presentation import number, recorded_zones
from app.services.evidence import digest

RUNNING_VERSION = "apex-running-v1"
MAX_SAMPLE_GAP_S = 5
MIN_DRIFT_MOVING_S = 1800
MIN_COVERAGE = .9


def positive(value, *, zero=False):
    value = number(value)
    return value if value is not None and (value >= 0 if zero else value > 0) else None


def metric(key, value, unit, formula, dependencies, *, version=RUNNING_VERSION, recorded=False,
           reason=None, limitations=None, prerequisites=None):
    return {"key": key, "value": value, "unit": unit, "kind": "recorded" if recorded else "calculated",
        "formula": formula, "formula_version": version, "source_dependencies": dependencies,
        "availability": "available" if value is not None else "unavailable",
        "unavailable_reason": reason if value is None else None, "limitations": limitations or [],
        "prerequisites": prerequisites or []}


def recorded_field(metrics, keys):
    for provider, block in (metrics or {}).items():
        if not isinstance(block, dict):
            continue
        for key in keys:
            value = positive(block.get(key), zero=True)
            if value is not None:
                return value, f"source_metrics.{provider}.{key}"
    return None, None


def moving_time(activity):
    value, dependency = recorded_field(activity.source_metrics, ("moving_time_s", "total_moving_time", "timer_time_s"))
    duration = positive(activity.duration_s)
    if duration is None or value is None or value <= 0 or value > duration:
        return None, None
    return value, dependency


def paired_intervals(streams, first="speed", second="hr", *, allow_zero_first=False):
    """Recorded sample intervals only: no interpolation across missing or sparse data."""
    intervals, longest, run = [], 0, 0
    for a, b in zip(streams, streams[1:]):
        dt = b.t_offset_s - a.t_offset_s
        x, y = positive(getattr(a, first, None), zero=allow_zero_first), positive(getattr(a, second, None))
        moving = positive(getattr(a, "speed", None))
        if 0 < dt <= MAX_SAMPLE_GAP_S and x is not None and y is not None and (first != "speed" or moving is not None):
            intervals.append((dt, x, y))
            run += dt
            longest = max(longest, run)
        else:
            run = 0
    return intervals, longest


def half_means(intervals):
    total = sum(row[0] for row in intervals)
    split, elapsed = total / 2, 0
    accum = [[0, 0, 0], [0, 0, 0]]
    for dt, x, y in intervals:
        first = max(0, min(dt, split - elapsed))
        for index, seconds in ((0, first), (1, dt-first)):
            accum[index][0] += seconds
            accum[index][1] += seconds * x
            accum[index][2] += seconds * y
        elapsed += dt
    return [(row[1] / row[0], row[2] / row[0]) for row in accum] if all(row[0] for row in accum) else None


def running_metrics(activity, streams, laps, *, rpe=None, rpe_dependency=None):
    aid = f"activity:{activity.id}"
    stream_dep = f"streams:{activity.id}"
    duration, distance = positive(activity.duration_s), positive(activity.distance_m)
    moving, moving_dep = moving_time(activity)
    out = []
    out.append(metric("average_pace", duration * 1000 / distance if duration and distance else None,
        "s/km", "recorded_duration_seconds / distance_metres × 1000", [aid+":duration_s", aid+":distance_m"],
        reason="missing_duration_or_distance", limitations=["recorded_duration_semantics", "terrain_and_session_context"]))
    out.append(metric("moving_pace", moving * 1000 / distance if moving and distance else None,
        "s/km", "recorded_moving_seconds / distance_metres × 1000", [aid+":distance_m"] + ([moving_dep] if moving_dep else []),
        reason="missing_reliable_moving_time", limitations=["provider_moving_time_definition"]))
    cadence, cadence_dep = recorded_field(activity.source_metrics, ("avg_cadence", "average_cadence"))
    out.append(metric("cadence", cadence, "cadence/min", "recorded_provider_cadence", [cadence_dep] if cadence_dep else [],
        recorded=True, reason="missing_recorded_cadence", limitations=["cadence_convention_provider_specific"]))
    elevation = positive(activity.elevation_gain_m, zero=True)
    out.append(metric("vertical_speed", elevation / duration * 3600 if elevation is not None and duration else None,
        "m/h", "recorded_ascent_metres / recorded_duration_seconds × 3600", [aid+":elevation_gain_m", aid+":duration_s"],
        reason="missing_elevation_or_duration", limitations=["ascent_rate_over_full_session", "altitude_recording_quality"]))
    splits, indices, covered = [], set(), 0
    for lap in laps:
        length, seconds = positive(lap.distance_m), positive(lap.duration_s)
        if length is not None and length >= 200 and seconds and lap.lap_index not in indices:
            splits.append(seconds / length * 1000)
            covered += length
            indices.add(lap.lap_index)
    valid_splits = len(splits) >= 3 and distance and .8 <= covered/distance <= 1.1
    cv = pstdev(splits) / mean(splits) * 100 if valid_splits else None
    out.append(metric("split_consistency", cv, "%", "population_SD(split_pace) / mean(split_pace) × 100", [f"laps:{activity.id}", aid+":distance_m"],
        reason="insufficient_valid_splits_or_coverage", limitations=["terrain_and_session_context", "split_lengths_may_differ"],
        prerequisites=["at_least_3_splits_of_200m", "80_to_110_percent_distance_coverage"]))
    intervals, longest = paired_intervals(streams)
    seconds = sum(row[0] for row in intervals)
    reference = moving or duration
    valid = bool(reference and seconds > 0 and MIN_COVERAGE <= seconds/reference <= 1.1)
    avg_speed = sum(dt*x for dt, x, _ in intervals) / seconds if valid else None
    avg_hr = sum(dt*y for dt, _, y in intervals) / seconds if valid else None
    out.append(metric("aerobic_efficiency", avg_speed / avg_hr if avg_speed and avg_hr else None,
        "m/s/bpm", "time_weighted_mean_speed / time_weighted_mean_HR", [stream_dep+":speed", stream_dep+":hr"],
        reason="missing_hr_speed_or_continuity", limitations=["descriptive_not_threshold", "terrain_and_session_context"],
        prerequisites=["90_percent_valid_hr_speed_coverage", "sample_gaps_at_most_5s"]))
    halves = half_means(intervals) if valid and seconds >= MIN_DRIFT_MOVING_S and longest >= MIN_DRIFT_MOVING_S else None
    drift = ((halves[1][1]/halves[1][0]) / (halves[0][1]/halves[0][0]) - 1) * 100 if halves and all(x > 0 and y > 0 for x, y in halves) else None
    out.append(metric("cardiac_drift", drift, "%", "((mean_HR/mean_speed)_second_moving_half / (mean_HR/mean_speed)_first_moving_half − 1) × 100",
        [stream_dep+":speed", stream_dep+":hr"], reason="requires_30min_continuous_valid_hr_speed",
        limitations=["descriptive_not_diagnosis", "terrain_temperature_and_intensity_confound"],
        prerequisites=["30min_continuous_moving_effort", "90_percent_valid_hr_speed_coverage", "pauses_excluded"]))
    zones = [z for z in recorded_zones(activity.source_metrics) if z["metric"] == "hr"]
    out.append(metric("hr_zone_time", zones or None, "s", "recorded_provider_HR_zone_durations", [aid+":source_metrics.hr_zones"],
        recorded=True, reason="missing_recorded_or_configured_zones", limitations=["provider_zone_definitions_required"]))
    exertion = number(rpe)
    rpe_load = duration / 60 * exertion if duration and exertion is not None and 0 <= exertion <= 10 else None
    out.append(metric("session_rpe_load", rpe_load, "session-RPE min", "recorded_duration_minutes × voluntary_session_RPE",
        [aid+":duration_s"] + ([rpe_dependency] if rpe_dependency else []), reason="missing_voluntary_rpe_or_duration",
        limitations=["subjective_self_report", "separate_load_scale"]))
    return out


def input_revision(activity, streams, laps, profile=None, checkin=None):
    return digest({"activity": {k: getattr(activity, k, None) for k in ("id", "duration_s", "distance_m", "elevation_gain_m", "source_metrics", "avg_power")},
        "streams": [[getattr(r, k, None) for k in ("t_offset_s", "hr", "power", "speed", "cadence", "altitude")] for r in streams],
        "laps": [[getattr(r, k, None) for k in ("lap_index", "duration_s", "distance_m")] for r in laps],
        "profile_revision": profile.revision if profile else None, "checkin_revision": checkin.revision if checkin else None})
