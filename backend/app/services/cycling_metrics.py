"""Second endurance release: recorded power streams and explicitly confirmed FTP."""
from datetime import date
from app.services.endurance_metrics import (metric, positive, running_metrics, moving_time,
    paired_intervals, half_means, MIN_DRIFT_MOVING_S)
from app.services.activity_presentation import recorded_zones

VERSION = "apex-cycling-v1"
FTP_MAX_AGE_DAYS = 90
NP_WINDOW_S = 30
NP_MIN_CONTINUOUS_S = 300


def dense_power(activity, streams):
    moving, _ = moving_time(activity)
    duration = positive(activity.duration_s)
    exclude_pauses = moving is not None and duration is not None and moving < duration
    segments, current = [], []
    for a, b in zip(streams, streams[1:]):
        power = positive(a.power, zero=True)
        if (b.t_offset_s-a.t_offset_s == 1 and a.t_offset_s >= 0 and power is not None
            and power <= 5000 and (not exclude_pauses or positive(a.speed))):
            current.append(power)
        else:
            if current:
                segments.append(current)
            current = []
    if current:
        segments.append(current)
    seconds = sum(len(s) for s in segments)
    reference = moving or duration
    valid = (reference and seconds >= NP_MIN_CONTINUOUS_S and segments
        and max(map(len, segments)) >= NP_MIN_CONTINUOUS_S and .95 <= seconds/reference <= 1.05)
    return segments, valid, seconds


def normalized_power(segments):
    fourth, windows = 0, 0
    for segment in segments:
        if len(segment) < NP_WINDOW_S:
            continue
        rolling = sum(segment[:NP_WINDOW_S])
        fourth += (rolling/NP_WINDOW_S)**4
        windows += 1
        for index in range(NP_WINDOW_S, len(segment)):
            rolling += segment[index] - segment[index-NP_WINDOW_S]
            fourth += (rolling/NP_WINDOW_S)**4
            windows += 1
    return (fourth/windows)**.25 if windows else None


def confirmed_ftp(context, activity_day):
    ftp = (context or {}).get("ftp")
    if not isinstance(ftp, dict) or ftp.get("confirmed") is not True or not positive(ftp.get("watts")):
        return None, "missing_confirmed_ftp", None
    try:
        measured = date.fromisoformat(ftp["measured_on"])
    except (KeyError, ValueError, TypeError):
        return None, "missing_confirmed_ftp", None
    age = (activity_day-measured).days
    if age < 0:
        return None, "ftp_after_activity", measured
    if age > FTP_MAX_AGE_DAYS:
        return None, "stale_ftp", measured
    return float(ftp["watts"]), None, measured


def cycling_metrics(activity, streams, laps, *, context=None, activity_day=None, profile_revision=None, rpe=None, rpe_dependency=None):
    aid, stream_dep = f"activity:{activity.id}", f"streams:{activity.id}"
    out = [m for m in running_metrics(activity, streams, laps, rpe=rpe, rpe_dependency=rpe_dependency, context=context, activity_day=activity_day, profile_revision=profile_revision)
        if m["key"] in {"cadence", "vertical_speed", "hr_zone_time", "session_rpe_load"}]
    for row in out:
        row["formula_version"] = VERSION
        if row["key"] == "cadence":
            row["unit"] = "rpm"
    moving, moving_dep = moving_time(activity)
    segments, valid_power, seconds = dense_power(activity, streams)
    np = normalized_power(segments) if valid_power else None
    average = positive(activity.avg_power, zero=True)
    average_dep = aid+":avg_power"
    if valid_power:
        average = sum(sum(s) for s in segments) / seconds
        average_dep = stream_dep+":power"
    work = average * moving / 1000 if average is not None and moving else None
    out.append(metric("mechanical_work", work, "kJ", "average_power_watts × recorded_moving_seconds / 1000",
        [average_dep] + ([moving_dep] if moving_dep else []), version=VERSION,
        reason="missing_power_or_reliable_moving_time", limitations=["mechanical_work_not_metabolic_calories", "provider_power_averaging_convention"]))
    out.append(metric("normalized_power", np, "W", "fourth_root(mean(30_second_rolling_mean_power^4))",
        [stream_dep+":power"], version=VERSION, reason="requires_dense_continuous_power_stream",
        limitations=["apex_calculation_not_provider_value", "descriptive_not_prediction"],
        prerequisites=["1Hz_recorded_power", "95_percent_power_coverage", "5min_continuous_segment", "30s_windows_without_gap_interpolation"]))
    ftp, ftp_reason, measured = confirmed_ftp(context, activity_day or activity.local_date)
    ftp_deps = [f"athlete_profile:{profile_revision}:ftp:{measured}"] if measured else []
    intensity = np / ftp if np is not None and ftp else None
    out.append(metric("intensity_factor", intensity, "ratio", "Apex_normalized_power / confirmed_FTP",
        [stream_dep+":power"]+ftp_deps, version=VERSION, reason=ftp_reason or "missing_normalized_power",
        limitations=["explicit_ftp_not_estimated", "ftp_90_day_max_age", "descriptive_not_threshold_prediction"]))
    duration = positive(activity.duration_s)
    tss = duration * np * intensity / (ftp * 3600) * 100 if duration and np is not None and intensity is not None and ftp else None
    out.append(metric("tss_style", tss, "Apex TSS-style", "(recorded_seconds × Apex_NP × IF) / (confirmed_FTP × 3600) × 100",
        [aid+":duration_s", stream_dep+":power"]+ftp_deps, version=VERSION, reason=ftp_reason or "missing_normalized_power_or_duration",
        limitations=["apex_calculation_not_provider_value", "separate_load_scale", "explicit_ftp_not_estimated"]))
    out.append(metric("variability_index", np / average if np is not None and average and valid_power else None, "ratio", "Apex_NP / same_stream_average_power",
        [stream_dep+":power"], version=VERSION, reason="missing_compatible_np_average_power",
        limitations=["same_recorded_stream_only", "descriptive_not_prediction"]))
    paired, longest = paired_intervals(streams, first="power", second="hr", allow_zero_first=True)
    # Explicit pauses must be excluded from both means; unknown speed during
    # a paused recording cannot establish a continuous moving effort.
    if moving and duration and moving < duration:
        paired, longest = [], 0
        run = 0
        for a, b in zip(streams, streams[1:]):
            dt = b.t_offset_s-a.t_offset_s
            power, hr = positive(a.power, zero=True), positive(a.hr)
            if 0 < dt <= 5 and power is not None and hr and positive(a.speed):
                paired.append((dt, power, hr))
                run += dt
                longest = max(longest, run)
            else:
                run = 0
    paired_seconds = sum(row[0] for row in paired)
    reference = moving or duration
    halves = half_means(paired) if reference and paired_seconds >= MIN_DRIFT_MOVING_S and longest >= MIN_DRIFT_MOVING_S and .9 <= paired_seconds/reference <= 1.1 else None
    decoupling = ((halves[1][1]/halves[1][0]) / (halves[0][1]/halves[0][0])-1)*100 if halves and all(x > 0 and y > 0 for x, y in halves) else None
    out.append(metric("power_hr_decoupling", decoupling, "%", "((mean_HR/mean_power)_second_moving_half / (mean_HR/mean_power)_first_moving_half − 1) × 100",
        [stream_dep+":power", stream_dep+":hr"], version=VERSION, reason="requires_30min_continuous_valid_power_hr",
        limitations=["terrain_temperature_and_intensity_confound", "descriptive_not_diagnosis"], prerequisites=["30min_continuous_moving_effort", "90_percent_power_hr_coverage"]))
    from app.services.endurance_metrics import zone_metric
    out.append(zone_metric(activity, streams, "power", context, activity_day, profile_revision, VERSION))
    return out
