"""Official Oura v2 phase strings, anchored to the actual provider period."""
from datetime import datetime, timedelta


def extract_sleep_stage_segments(payload):
    try:
        start = datetime.fromisoformat(payload["bedtime_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(payload["bedtime_end"].replace("Z", "+00:00"))
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        return None
    phases = {"1": "deep", "2": "light", "3": "rem", "4": "awake"}
    # A partial string must not be stretched to invent the rest of the night.
    for key, step in (("sleep_phase_30_sec", 30), ("sleep_phase_5_min", 300)):
        values = payload.get(key)
        if not isinstance(values, str) or not values or any(v not in phases for v in values):
            continue
        if abs(len(values) * step - (end - start).total_seconds()) > step:
            continue
        segments = []
        for index, value in enumerate(values):
            t0, t1 = start + timedelta(seconds=index * step), min(end, start + timedelta(seconds=(index + 1) * step))
            if t0 >= end:
                break
            if segments and segments[-1]["stage"] == phases[value]:
                segments[-1]["t_end"] = t1.isoformat()
            else:
                segments.append({"t_start": t0.isoformat(), "t_end": t1.isoformat(), "stage": phases[value]})
        return segments or None
    return None
