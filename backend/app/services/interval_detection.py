"""Bounded descriptive interval candidates from recorded speed or power.

Cutoffs are software eligibility rules, not physiological zones or prescribed
workout identification. No interpolation, HR inference, or compliance claims.
"""
from math import sqrt
from app.services.endurance_metrics import metric, positive

VERSION = "recorded-level-segmentation-v1"
BIN_SECONDS = 15
MAX_STREAM_ROWS = 200000
MAX_DURATION_S = 6*3600
MAX_CANDIDATES = 30


def automatic_intervals(activity, streams, *, field="speed", complete=True):
    duration = positive(activity.duration_s)
    unit = "W" if field == "power" else "m/s"
    quality = {"activity_id":activity.id, "signal":field, "signal_unit":unit,
        "bin_duration_s":BIN_SECONDS, "maximum_candidates":MAX_CANDIDATES,
        "maximum_duration_s":MAX_DURATION_S, "input_complete":complete}
    dependencies = [f"streams:{activity.id}:{field}", f"activity:{activity.id}:duration_s"]
    def result(value=None, reason=None):
        row = metric("automatic_intervals", value, "s",
            "15s time-weighted recorded bins; midpoint of 20th/80th percentile levels; repeated sustained high/low runs",
            dependencies, version=VERSION, reason=reason,
            prerequisites=["95_percent_recorded_signal_coverage", "strictly_increasing_offsets", "sample_gaps_at_most_5s",
                "two_30_to_900s_efforts_with_15_to_900s_recovery", "stable_effort_and_recovery_levels"],
            limitations=["descriptive_candidates_not_workout_compliance", "terrain_stops_and_sensor_error_can_mimic_intervals",
                "fixed_method_cutoffs_not_physiological_thresholds", "no_gap_interpolation", "boundaries_quantized_to_15s"])
        row["quality"] = quality
        return row
    if field not in {"speed","power"}:
        return result(reason="unsupported_recorded_interval_signal")
    if not complete or len(streams) > MAX_STREAM_ROWS:
        return result(reason="input_limit_exceeded")
    if not duration or not 180 <= duration <= MAX_DURATION_S:
        return result(reason="requires_3min_to_6h_recorded_duration")
    offsets = [positive(r.t_offset_s,zero=True) for r in streams]
    if (len(offsets) < 2 or any(t is None or t > duration for t in offsets)
            or any(b <= a for a,b in zip(offsets,offsets[1:]))):
        return result(reason="invalid_or_nonmonotonic_stream_offsets")
    bins = [[0.,0.] for _ in range(int(duration//BIN_SECONDS))]
    valid_seconds = 0
    for a,b in zip(streams,streams[1:]):
        start,end = a.t_offset_s,b.t_offset_s
        value = positive(getattr(a,field,None),zero=True)
        if end-start > 5 or value is None or value > (5000 if field == "power" else 100):
            continue
        valid_seconds += end-start
        while start < min(end,len(bins)*BIN_SECONDS):
            index = int(start//BIN_SECONDS)
            stop = min(end,(index+1)*BIN_SECONDS)
            bins[index][0] += (stop-start)*value
            bins[index][1] += stop-start
            start = stop
    quality.update(valid_seconds=valid_seconds, coverage=valid_seconds/duration)
    if valid_seconds/duration < .95:
        return result(reason="requires_95_percent_recorded_signal_coverage")
    levels = [total/seconds if seconds >= BIN_SECONDS*.95 else None for total,seconds in bins]
    observed = sorted(v for v in levels if v is not None)
    if not observed:
        return result(reason="requires_complete_15s_recorded_bins")
    low,high = observed[int((len(observed)-1)*.2)], observed[int((len(observed)-1)*.8)]
    contrast = 1.4 if field == "power" else 1.25
    quality.update(lower_level=low,upper_level=high,required_level_ratio=contrast)
    empty = {"activity_id":activity.id,"signal":field,"signal_unit":unit,"candidate_count":0,
        "classification":"no_repeated_pattern", "intervals":[]}
    if low <= 0 or high/low < contrast:
        return result(empty)
    threshold = (low+high)/2
    quality["segmentation_threshold"] = threshold
    runs = []
    for index,value in enumerate(levels):
        kind = None if value is None else "effort" if value >= threshold else "recovery"
        if not runs or runs[-1]["kind"] != kind:
            runs.append({"kind":kind,"start":index*BIN_SECONDS,"end":(index+1)*BIN_SECONDS,"values":[]})
        else:
            runs[-1]["end"] = (index+1)*BIN_SECONDS
        if value is not None:
            runs[-1]["values"].append(value)
    def stable(run):
        values = run["values"]
        mean = sum(values)/len(values) if values else 0
        return mean > 0 and sqrt(sum((v-mean)**2 for v in values)/len(values))/mean <= .15
    candidates = []
    for i in range(len(runs)-2):
        first,recovery,second = runs[i:i+3]
        if ([r["kind"] for r in (first,recovery,second)] != ["effort","recovery","effort"]
            or not all(stable(r) for r in (first,recovery,second))
            or not all(30 <= r["end"]-r["start"] <= 900 for r in (first,second))
            or not 15 <= recovery["end"]-recovery["start"] <= 900):
            continue
        for effort in (first,second):
            if not candidates or candidates[-1]["start_offset_s"] != effort["start"]:
                candidates.append({"start_offset_s":effort["start"],"end_offset_s":effort["end"],
                    "duration_s":effort["end"]-effort["start"], "mean_signal":sum(effort["values"])/len(effort["values"]),
                    "signal_unit":unit})
        if len(candidates) > MAX_CANDIDATES:
            return result(reason="interval_candidate_limit_exceeded")
    quality["method_confidence"] = "bounded_repeated_pattern" if candidates else "no_supported_repeated_pattern"
    return result({**empty, "classification":"repeated_recorded_level_changes" if candidates else "no_repeated_pattern",
        "candidate_count":len(candidates), "intervals":candidates})
