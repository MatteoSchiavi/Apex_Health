"""Sleep-stage timeline extraction from a stored Garmin sleep payload.

The normalizer folds the nightly aggregates (deep/light/rem/awake seconds)
into `sleep_sessions`, but the hypnogram needs the EPOCH timeline, which is
only present in the raw payload (`raw_ingest.raw_json`):

    raw_json.dailySleepDTO.sleepLevels = [
        {"activityLevel": {"value": 2}, "startGMT": "...", "endGMT": "..."},
        ...
    ]

Garmin's activityLevel codes: 0 = awake, 1 = deep, 2 = light, 3 = REM.
Some payload revisions nest the list elsewhere or carry string codes — the
extractor is deliberately defensive and returns None (not an error) when no
usable timeline exists, so the UI falls back to the proportional stage bar
instead of breaking the night page.
"""

from typing import Any

# Garmin activityLevel numeric codes -> canonical stage names.
_LEVEL_CODES: dict[int, str] = {0: "awake", 1: "deep", 2: "light", 3: "rem"}

# String variants seen across payload revisions.
_LEVEL_NAMES: dict[str, str] = {
    "awake": "awake",
    "alert": "awake",
    "awake_sleep": "awake",
    "deep": "deep",
    "deep_sleep": "deep",
    "light": "light",
    "light_sleep": "light",
    "rem": "rem",
    "core": "light",
}

_STAGE_ORDER = {"deep": 0, "rem": 1, "light": 2, "awake": 3}


def _stage_name(level: Any) -> str | None:
    if isinstance(level, bool):
        return None
    if isinstance(level, (int, float)):
        return _LEVEL_CODES.get(int(level))
    if isinstance(level, dict):
        return _stage_name(level.get("value", level.get("activityLevel")))
    if isinstance(level, str):
        return _LEVEL_NAMES.get(level.strip().lower())
    return None


def _extract_levels_list(dto: dict[str, Any]) -> list[Any] | None:
    """Locate the level-interval list wherever the payload nests it."""
    for key in ("sleepLevels", "sleepSleepLevels"):
        candidate = dto.get(key)
        if isinstance(candidate, list) and candidate:
            return candidate
        # map-shaped revision: {"<epochKey>": {"activityLevel": ...}}
        if isinstance(candidate, dict) and candidate:
            rows = []
            for epoch_key, item in candidate.items():
                if not isinstance(item, dict):
                    continue
                start = item.get("startGMT") or item.get("startTimeGMT")
                end = item.get("endGMT") or item.get("endTimeGMT")
                if start and end:
                    rows.append({**item, "startGMT": start, "endGMT": end})
            if rows:
                return rows
    # top level (outside dailySleepDTO)
    top = dto.get("_top")
    return top if isinstance(top, list) else None


def extract_sleep_stage_segments(payload: dict[str, Any]) -> list[dict] | None:
    """Return sorted, de-overlapped stage segments for one night.

    Each segment: {"t_start": "ISO-8601 UTC", "t_end": "ISO-8601 UTC",
    "stage": "deep|light|rem|awake"}. None when the payload has no usable
    level timeline (legacy rows, other providers, corrupted payloads)."""
    if not isinstance(payload, dict):
        return None
    dto = payload.get("dailySleepDTO")
    levels: list[Any] | None = None
    if isinstance(dto, dict):
        levels = _extract_levels_list(dto)
    if levels is None:
        # some revisions put the interval list at the top level
        levels = _extract_levels_list({**payload, "_top": payload.get("sleepLevels")})
    if not levels:
        return None

    segments: list[dict] = []
    for row in levels:
        if not isinstance(row, dict):
            continue
        start = row.get("startGMT") or row.get("startTimeGMT")
        end = row.get("endGMT") or row.get("endTimeGMT")
        if not start or not end:
            continue
        stage = _stage_name(row.get("activityLevel"))
        if stage is None:
            continue
        try:
            from datetime import datetime

            t0 = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t1 <= t0:
            continue
        segments.append({"t_start": t0.isoformat(), "t_end": t1.isoformat(), "stage": stage})

    if not segments:
        return None
    segments.sort(key=lambda s: (s["t_start"], _STAGE_ORDER[s["stage"]]))

    # Merge adjacent same-stage intervals (payloads often fragment stages).
    merged: list[dict] = []
    for seg in segments:
        if merged and merged[-1]["stage"] == seg["stage"] and merged[-1]["t_end"] == seg["t_start"]:
            merged[-1]["t_end"] = seg["t_end"]
        else:
            merged.append(seg)
    return merged
