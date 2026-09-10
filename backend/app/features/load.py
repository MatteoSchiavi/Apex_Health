"""Daily training load — Edwards-style TRIMP, rolling windows, ACWR (§7).

Load metric law (§17): ACWR uses exactly ONE load metric for both windows.
That metric is the daily TRIMP series defined here; acute (7d) and chronic
(28d) windows both sum the same series. Chronic is stored on a weekly-average
scale (28d sum / 4) so the ratio reads ~1.0 at steady state.

TRIMP source priority per activity:
1. HR streams — zone seconds via sample-interval integration (Edwards zones:
   5 points at 90-100% HRmax down to 1 point below 60%), which is exact for
   piecewise-constant HR regardless of sampling rate.
2. avg_hr — duration x zone factor of the average (no stream detail).
3. activity.training_load — the source's own load number, kept verbatim.

An activity with none of the three contributes 0 load and is a sensor gap
(the engine flags the day data_completeness='partial', §17).

HRmax estimate: 220 - age (dob from the user profile); 190 when dob is
unknown. A formula constant, pinned by the golden-dataset tests — not a
feature weight (§6.4 weights own blend weights, not functional forms).
"""

from datetime import date, timedelta

from app.models.activity import Activity, ActivityStream

# Lower bounds of Edwards zones 2..5 as fractions of HRmax; zone 1 is
# everything below 0.60. factor() maps a %HRmax to 1..5 points.
_ZONE_BOUNDS = (0.50, 0.60, 0.70, 0.80, 0.90)

# Cold-start guard for the strain ceiling normalization (scores.py).
STRAIN_CEILING_FLOOR = 300.0

HRMAX_FALLBACK = 190


def zone_factor(pct_hrmax: float) -> int:
    """Edwards zone points 1..5 for a fraction of HRmax.

    0.55 -> 1, 0.65 -> 2, 0.75 -> 3, 0.85 -> 4, 0.95 -> 5; below 0.50 and
    above 1.00 clamp to 1 and 5.
    """
    # +1e-9 guards exact decimal boundaries (0.7 * 10 evaluates to 6.999...).
    return min(5, max(1, int(pct_hrmax * 10 + 1e-9) - 4))


def zone_bounds() -> tuple[float, ...]:
    return _ZONE_BOUNDS


def hr_max_for(age_years: int | None) -> int:
    if age_years is None:
        return HRMAX_FALLBACK
    return 220 - age_years


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
    activity: Activity, streams: list[ActivityStream], hrm: int
) -> float | None:
    """TRIMP-style load for one activity; None only when the activity carries
    no load signal at all (no HR streams, no avg_hr, no training_load)."""
    zone_seconds = _zone_seconds_from_streams(streams, activity.duration_s, hrm)
    if zone_seconds:
        return sum(seconds * factor for factor, seconds in zone_seconds.items()) / 60.0
    if activity.avg_hr is not None:
        minutes = activity.duration_s / 60.0
        return minutes * zone_factor(activity.avg_hr / hrm)
    if activity.training_load is not None:
        return float(activity.training_load)
    return None


def daily_loads(
    activities_with_streams: list[tuple[Activity, list[ActivityStream]]],
    hrm: int,
) -> dict[date, float]:
    """Daily TRIMP series keyed by the activity's LOCAL date (§17)."""
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
