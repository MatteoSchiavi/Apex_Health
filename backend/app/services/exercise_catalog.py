"""Deterministic exercise names from the bundled Garmin FIT profile.

Free text is a label, never an instruction. Conservative EN/IT aliases identify
known movements; unsupported categories remain unknown rather than painting a
muscle that was never established. The map describes movement groups, not
measured activation or injury risk.
"""
import io
import re
import unicodedata
from functools import lru_cache

CATEGORY_GROUPS = {
    **dict.fromkeys(("bench_press", "push_up", "flye", "shoulder_press", "lateral_raise", "triceps_extension"), "push"),
    **dict.fromkeys(("row", "pull_up", "curl", "shrug"), "pull"),
    **dict.fromkeys(("squat", "lunge", "deadlift", "calf_raise", "leg_curl", "leg_extension", "hip_raise", "hip_stability", "hip_swing"), "legs"),
    **dict.fromkeys(("core", "crunch", "plank", "sit_up", "leg_raise", "chop", "hyperextension"), "core"),
    **dict.fromkeys(("olympic_lift", "burpee", "carry", "total_body"), "full_body"),
}
ALIASES = {
    "panca piana": ("bench_press", "push"),
    "panca inclinata": ("incline_bench_press", "push"),
    "bench press": ("bench_press", "push"),
    "piegamenti": ("push_up", "push"), "push up": ("push_up", "push"),
    "military press": ("shoulder_press", "push"),
    "alzate laterali": ("lateral_raise", "push"),
    "croci": ("flye", "push"),
    "trazioni": ("pull_up", "pull"), "lat machine": ("lat_pulldown", "pull"),
    "rematore": ("row", "pull"), "pulley": ("seated_cable_row", "pull"),
    "curl bicipiti": ("biceps_curl", "pull"), "biceps curl": ("biceps_curl", "pull"),
    "squat": ("squat", "legs"),
    "stacco": ("deadlift", "legs"), "stacchi da terra": ("deadlift", "legs"),
    "affondi": ("lunge", "legs"), "leg press": ("leg_press", "legs"),
    "pressa": ("leg_press", "legs"), "leg extension": ("leg_extension", "legs"),
    "leg curl": ("leg_curl", "legs"), "calf raise": ("calf_raise", "legs"),
    "plank": ("plank", "core"), "crunch": ("crunch", "core"),
    "addominali": ("crunch", "core"), "burpees": ("burpee", "full_body"),
}


def clean_label(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", re.sub(r"<[^>]*>", "", value))
    value = re.split(r"[\r\n]|\s(?:[-–—|]|//)\s|\b(?:note|notes|nota|appunti|commento)\s*:", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"[\x00-\x1f\x7f]", "", value)
    return re.sub(r"\s+", " ", value).strip()[:120]


def key(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)).replace("_", " ").replace("-", " ").split())


@lru_cache(maxsize=1)
def catalog():
    from fitdecode import profile

    rows = {}
    for category, group in CATEGORY_GROUPS.items():
        field = profile.FIELD_TYPES.get(category + "_exercise_name")
        for name in (field.enum or {}).values() if field else ():
            rows[key(name)] = {"id": name, "name": name.replace("_", " ").title(), "muscle_group": group}
    for alias, (name, group) in ALIASES.items():
        rows[alias] = {"id": name, "name": name.replace("_", " ").title(), "muscle_group": group}
    return rows


def identify(value, group=None):
    label = clean_label(value)
    match = catalog().get(key(label))
    return {
        "name": match["name"] if match else label or "Unknown exercise",
        "muscle_group": group if group in set(CATEGORY_GROUPS.values()) else match["muscle_group"] if match else None,
    }


def garmin_exercises(payload):
    """Garmin exerciseSets records; REST/planned entries are never workout sets.

    Numeric weight without an explicit unit is preserved in raw ingestion but
    excluded from volume: upstream schemas differ and magnitude is not a unit.
    """
    from math import isfinite

    rows = payload.get("exerciseSets") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out = {}
    for row in rows[:10000]:
        if not isinstance(row, dict) or str(row.get("setType", "")).lower() != "active":
            continue
        reps = row.get("repetitionCount")
        if isinstance(reps, bool) or not isinstance(reps, (int, float)) or not isfinite(reps) or not 0 <= reps <= 10000 or reps != int(reps):
            continue
        names = row.get("exercises")
        names = [e for e in names if isinstance(e, dict)] if isinstance(names, list) else []
        categories = {str(e.get("category", "")).lower() for e in names}
        group = CATEGORY_GROUPS.get(next(iter(categories))) if len(categories) == 1 else None
        name = names[0].get("name") if len(names) == 1 else None
        info = identify(name or row.get("exerciseName") or (next(iter(categories)) if len(categories) == 1 else "Unknown exercise"), group)
        weight = row.get("weight_kg")
        if weight is None and str(row.get("weightUnit", "")).lower() in ("kg", "kilogram", "kilograms"):
            weight = row.get("weight")
        if weight is None and str(row.get("weightUnit", "")).lower() in ("g", "gram", "grams"):
            grams = row.get("weight")
            weight = grams / 1000 if isinstance(grams, (int, float)) and not isinstance(grams, bool) else None
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not isfinite(weight) or weight < 0:
            weight = None
        item = out.setdefault((info["name"], info["muscle_group"]), {**info, "recorded_sets": []})
        item["recorded_sets"].append({"reps": int(reps), "weight_kg": weight})
    return list(out.values())


def fit_exercises(content, start=None, end=None):
    import fitdecode
    from fitdecode import profile

    sets, titles = [], {}
    with fitdecode.FitReader(io.BytesIO(content), check_crc=fitdecode.CrcCheck.RAISE) as reader:
        for frame in reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name not in ("set", "exercise_title"):
                continue
            row = {f.name: f.value for f in frame.fields if f.value is not None}
            if frame.name == "exercise_title":
                titles[row.get("message_index")] = row.get("wkt_step_name")
            else:
                sets.append(row)
            if len(sets) > 10000 or len(titles) > 10000:
                raise ValueError("FIT exercise limits exceeded")
    exercises = {}
    for row in sets:
        stamp = row.get("start_time")
        if start and (stamp is None or stamp < start or end and stamp >= end):
            continue
        if row.get("set_type") != "active":
            continue
        reps = row.get("repetitions")
        if not isinstance(reps, (int, float)) or isinstance(reps, bool) or not 0 <= reps <= 10000:
            continue
        categories = row.get("category", ())
        categories = categories if isinstance(categories, (list, tuple)) else [categories]
        subtypes = row.get("category_subtype", ())
        subtypes = subtypes if isinstance(subtypes, (list, tuple)) else [subtypes]
        category = categories[0] if categories else None
        subtype = subtypes[0] if subtypes else None
        field = profile.FIELD_TYPES.get(str(category) + "_exercise_name")
        canonical = field.enum.get(subtype) if field and field.enum else None
        # Recorded category is stronger evidence than a custom workout note.
        label = canonical or titles.get(row.get("wkt_step_index")) or str(category or "Unknown exercise")
        info = identify(label, CATEGORY_GROUPS.get(category))
        item = exercises.setdefault((info["name"], info["muscle_group"]), {**info, "recorded_sets": []})
        weight = row.get("weight")  # fitdecode has already applied the FIT kg scale.
        item["recorded_sets"].append({"reps": int(reps), "weight_kg": weight})
    return list(exercises.values())
