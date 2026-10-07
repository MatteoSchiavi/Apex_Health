"""Comparable load windows: Edwards TRIMP or recorded Garmin load.

Both acute and chronic use one selected method; provider units are never
converted using an unsupported multiplier. Recorded source values remain
unchanged. Window metadata declares exclusions and method.
"""

from datetime import date, timedelta
from math import isfinite

from app.models.activity import Activity, ActivityStream

# Lower bounds of Edwards zones 2..5 as fractions of HRmax; zone 1 is
# everything below 0.60. factor() maps a %HRmax to 1..5 points.
_ZONE_BOUNDS = (0.50, 0.60, 0.70, 0.80, 0.90)

# Cold-start guard for the strain ceiling normalization (scores.py).
STRAIN_CEILING_FLOOR = 300.0

# P-05 audit: HRmax_FALLBACK removed — when age is unknown the load is marked
# unreliable (None) instead of inventing a magic 190. Callers must handle None.
# The constant is kept for backward-compat in callers that still reference it,
# but hr_max_for now returns None for unknown age.
HRMAX_FALLBACK = 190  # deprecated — do not use; see hr_max_for




def zone_factor(pct_hrmax: float) -> int:
    """Edwards zone points 1..5 for a fraction of HRmax.

    0.55 -> 1, 0.65 -> 2, 0.75 -> 3, 0.85 -> 4, 0.95 -> 5; below 0.50 and
    above 1.00 clamp to 1 and 5.
    """
    # +1e-9 guards exact decimal boundaries (0.7 * 10 evaluates to 6.999...).
    return min(5, max(1, int(pct_hrmax * 10 + 1e-9) - 4))


def zone_bounds() -> tuple[float, ...]:
    return _ZONE_BOUNDS


def hr_max_for(age_years: int | None) -> int | None:
    """Tanaka population HRmax estimate: 208 − 0.7·age.

    This is an age-based estimate, not an athlete's measured maximum; its
    individual error can materially affect zone-based load. Unknown age
    yields unavailable HRmax rather than an invented constant.
    """
    if age_years is None:
        return None
    # Tanaka: 208 − 0.7·age. Round to nearest int — zone boundaries are
    # percentage-based so a fractional HRmax works too, but int matches
    # the existing API contract.
    return round(208 - 0.7 * age_years)


def age_at(dob, on_date: date) -> int | None:
    if dob is None:
        return None
    return on_date.year - dob.year - (
        (on_date.month, on_date.day) < (dob.month, dob.day)
    )


def _zone_seconds_from_streams(streams: list[ActivityStream], duration_s: int, hrm: int) -> dict[int, float]:
    """Seconds per zone via sample-interval integration.

    Each stream sample represents the interval until the next sample (the
    last until the activity end) — this is the time-aligned reading of the
    session, immune to varying sampling rates (§7 decoupling lesson, applied
    to load too).
    """
    zone_seconds: dict[int, float] = {}
    ordered = sorted(streams, key=lambda s: s.t_offset_s)
    if not ordered:
        return zone_seconds
    for i, sample in enumerate(ordered):
        if sample.hr is None:
            continue
        if i + 1 < len(ordered):
            interval = ordered[i + 1].t_offset_s - sample.t_offset_s
        else:
            interval = duration_s - sample.t_offset_s
        if interval <= 0:
            continue
        factor = zone_factor(sample.hr / hrm)
        zone_seconds[factor] = zone_seconds.get(factor, 0.0) + interval
    return zone_seconds


def activity_trimp(
    activity: Activity, streams: list[ActivityStream], hrm: int | None
) -> float | None:
    """Edwards load from measured HR only; provider load stays separate."""
    # P-05: HR-based TRIMP requires a real HRmax — None means age unknown.
    if hrm is not None and hrm > 0:
        zone_seconds = _zone_seconds_from_streams(streams, activity.duration_s, hrm)
        if zone_seconds:
            return sum(seconds * factor for factor, seconds in zone_seconds.items()) / 60.0
        if activity.avg_hr is not None:
            minutes = activity.duration_s / 60.0
            return minutes * zone_factor(activity.avg_hr / hrm)
    # Proprietary provider load is not Edwards TRIMP and has no validated
    # conversion. Keep it on its recorded scale in a separate series.
    return None


def _eligible_load(value) -> float | None:
    """A corrupt or absent source quantity is unknown, never a rest-day zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and number >= 0 else None


def consistent_window_loads(activities_with_streams, hrm):
    """Choose the best-covered single method for both rolling windows.

    Recorded Garmin load wins coverage ties. Unidentified provider values
    never become Garmin units; excluded sessions are disclosed as partial.
    """
    derived = {a.id: _eligible_load(activity_trimp(a, streams, hrm))
               for a, streams in activities_with_streams}
    recorded = {}
    for activity, _ in activities_with_streams:
        garmin = (activity.source_metrics or {}).get("garmin")
        if not isinstance(garmin, dict):
            continue
        # New rows retain the source quantity itself, independent of a
        # canonical activity merged with another selected provider.
        value = garmin.get("training_load")
        if value is None and "training_load_method" not in garmin:
            # Legacy Garmin rows: Garmin was the sole adapter populating
            # canonical training_load; other adapters retain their own scales.
            value = activity.training_load
        eligible = _eligible_load(value)
        if eligible is not None:
            recorded[activity.id] = eligible
    valid_derived = {key: value for key, value in derived.items() if value is not None}
    method = 'garmin_recorded' if recorded and len(recorded) >= len(valid_derived) else 'edwards_trimp'
    selected = recorded if method == 'garmin_recorded' else valid_derived
    loads = {}
    for activity, _ in activities_with_streams:
        if activity.id in selected:
            loads[activity.local_date] = loads.get(activity.local_date, 0.0) + selected[activity.id]
    metadata = {
        'method': method, 'unit': 'Garmin load' if method == 'garmin_recorded' else 'Edwards TRIMP',
        'included_sessions': len(selected), 'excluded_sessions': len(activities_with_streams) - len(selected),
        'acute_window_days': 7, 'chronic_window_days': 28, 'chronic_scale': '28d sum / 4',
        'limitation': 'One best-covered method per window; incompatible or missing load observations are excluded.',
    }
    return loads, selected, metadata


def daily_loads(
    activities_with_streams: list[tuple[Activity, list[ActivityStream]]],
    hrm: int | None,
) -> dict[date, float]:
    """Daily Edwards TRIMP series keyed by the activity's local date."""
    loads: dict[date, float] = {}
    for activity, streams in activities_with_streams:
        trimp = activity_trimp(activity, streams, hrm)
        if trimp is None:
            continue
        loads[activity.local_date] = loads.get(activity.local_date, 0.0) + trimp
    return loads


def rolling_sum(loads: dict[date, float], day: date, days: int) -> float:
    """Sum of the daily load series over [day - days + 1, day]. Days with no
    recorded activity count as zero — a rest day is a zero-load day."""
    total = 0.0
    for offset in range(days):
        total += loads.get(day - timedelta(days=offset), 0.0)
    return total


def acwr_from(acute7: float, chronic28: float) -> float | None:
    """ACWR = 7d load / weekly-averaged 28d load. One metric, both windows
    (§17). None when there is no chronic load to normalize against at all."""
    chronic_weekly = chronic28 / 4.0
    if chronic_weekly <= 0:
        return None
    return acute7 / chronic_weekly


def load_distribution(
    loads: dict[date, float], day: date, days: int = 28
) -> tuple[float, float]:
    """(mean, population std) of the daily load series over
    [day - days, day - 1], ZERO-FILLED — a rest day contributes a real 0,
    it is not a missing observation. Used by the injury-risk load-spike
    component ("today vs. my normal distribution")."""
    values = [
        loads.get(day - timedelta(days=offset), 0.0)
        for offset in range(1, days + 1)
    ]
    mean = sum(values) / days
    variance = sum((v - mean) ** 2 for v in values) / days
    return mean, variance**0.5


def active_day_count(loads: dict[date, float], day: date, days: int = 28) -> int:
    """P-13 audit: count of non-zero-load days in [day - days, day - 1].

    The descriptive load-spike component requires a minimum number of
    active days before activation — otherwise an athlete returning from a
    4-week break (28-day window all zeros) can overstate a descriptive load spike on
    their first normal session because std=0 makes the spike formula
    degenerate. ``active_day_count >= 7`` is the gate.
    """
    return sum(
        1
        for offset in range(1, days + 1)
        if loads.get(day - timedelta(days=offset), 0.0) > 0
    )
