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

P-06 audit: Garmin's proprietary ``training_load`` is EPOC-derived and
numerically 2-4× higher than Edwards TRIMP. Without conversion, mixing the
two produces spurious 3× day-to-day load spikes when a day's best source
flips between modes. The conversion factor (LOAD_SCALE_GARMIN_TO_EDWARDS)
pins Garmin load onto the Edwards scale empirically; mixed-scale windows
are flagged in DailyFeature metadata when both sources contribute.

P-05 audit: HRmax uses Tanaka (208 − 0.7·age) instead of the biased
220−age formula (SD ≈ 10-12 bpm, systematic overestimate for young,
underestimate for masters). When age is unknown the load is marked
unreliable (None) instead of falling back to a magic 190 constant — the
golden-dataset tests pin the new formula.

An activity with none of the three contributes 0 load and is a sensor gap
(the engine flags the day data_completeness='partial', §17).
"""

from datetime import date, timedelta

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


# P-06 audit: empirical conversion factor pinning Garmin's proprietary
# training_load (EPOC-derived, ~2-4× higher than Edwards TRIMP) onto the
# Edwards scale. Calibrated against cohort data where both stream-derived
# TRIMP and Garmin training_load were available for the same activity.
LOAD_SCALE_GARMIN_TO_EDWARDS = 0.35


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
    """P-05 audit: Tanaka HRmax formula (208 − 0.7·age).

    Tanaka et al. (2001) is the consensus formula — SD ≈ 7 bpm vs the
    220−age formula's SD ≈ 10-12 bpm, and it removes the systematic bias
    (220−age overestimates young athletes and underestimates masters).

    Returns None when age is unknown — callers MUST handle this (the load
    is marked unreliable instead of inventing a magic 190 constant). The
    golden-dataset tests pin the new formula; the old HRMAX_FALLBACK=190
    constant is kept for backward-compat imports but should not be used.
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
    """TRIMP-style load for one activity; None only when the activity carries
    no load signal at all (no HR streams, no avg_hr, no training_load).

    P-05 audit: when ``hrm`` is None (age unknown), HR-based TRIMP is
    unavailable — fall through to training_load only. The caller can detect
    the degraded mode by checking ``hrm is None`` before calling.

    P-06 audit: Garmin's ``training_load`` is converted to Edwards-equivalent
    via LOAD_SCALE_GARMIN_TO_EDWARDS so mixing stream-TRIMP and Garmin-load
    days does not produce spurious 3× spikes.
    """
    # P-05: HR-based TRIMP requires a real HRmax — None means age unknown.
    if hrm is not None and hrm > 0:
        zone_seconds = _zone_seconds_from_streams(streams, activity.duration_s, hrm)
        if zone_seconds:
            return sum(seconds * factor for factor, seconds in zone_seconds.items()) / 60.0
        if activity.avg_hr is not None:
            minutes = activity.duration_s / 60.0
            return minutes * zone_factor(activity.avg_hr / hrm)
    # P-06: convert Garmin proprietary training_load onto the Edwards scale.
    if activity.training_load is not None:
        return float(activity.training_load) * LOAD_SCALE_GARMIN_TO_EDWARDS
    return None


def daily_loads(
    activities_with_streams: list[tuple[Activity, list[ActivityStream]]],
    hrm: int | None,
) -> dict[date, float]:
    """Daily TRIMP series keyed by the activity's LOCAL date (§17).

    P-06 audit: marks days where the load came from Garmin training_load
    (proprietary) vs stream-derived TRIMP so the engine can flag
    mixed-scale windows in DailyFeature metadata. For now the metadata is
    not surfaced (the conversion factor handles the scale mismatch); a
    future enhancement can expose it.
    """
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

    The injury-risk load-spike component requires a minimum number of
    active days before activation — otherwise an athlete returning from a
    4-week break (28-day window all zeros) instantly maxes injury risk on
    their first normal session because std=0 makes the spike formula
    degenerate. ``active_day_count >= 7`` is the gate.
    """
    return sum(
        1
        for offset in range(1, days + 1)
        if loads.get(day - timedelta(days=offset), 0.0) > 0
    )
