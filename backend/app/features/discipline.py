"""Per-discipline daily metrics (§7): aerobic decoupling, efficiency factor,
FTP estimation — and the steady-state gate that scopes them.

Discipline law (§17): efficiency-factor and decoupling math is always scoped
by discipline_id, never pooled. This module computes PER ACTIVITY; the engine
aggregates per (user, discipline, local date).

Decoupling (§7): first half vs second half of a steady-state effort, arrays
aligned by TIME OFFSET, not sample count — the split is at duration/2
seconds, so a session recorded with mixed sampling rates cannot bias one
half (an earlier draft of this project misaligned these by count).

Steady-state gate: §7 scopes decoupling to steady-state efforts. For power
sports the validated criterion is Coggan's Variability Index (NP / AP):
VI <= 1.05 counts as steady. Non-power endurance gets no VI, so decoupling
is computed whenever half-means are defined (documented limitation).

Efficiency factor:
- cycling (power): NP / time-weighted avg HR
- other endurance (running & co): speed (m/min) / avg HR
- strength/technical: None — EF is not a meaningful metric there.

FTP (§17: validated protocols only, never ad hoc regression): the discipline
row's ftp_model_type gates estimation. 'twenty_min_protocol' = FTP is 0.95 x
the best 20-minute mean power inside the session (sample-and-hold
integration). The protocol fires on any qualifying 20-min window — a steady
zone-2 ride yields a modest estimate, a test day a real one; no ad hoc
effort gating is layered on top.
"""

import bisect

from app.models.activity import Activity, ActivityStream

STEADY_VI_MAX = 1.05
FTP_TWENTY_MIN_WINDOW_S = 1200
FTP_TWENTY_MIN_FACTOR = 0.95
MIN_HALF_SAMPLES = 2
MIN_SESSION_S = 1200  # shorter efforts say nothing about aerobic drift

CYCLING_DISCIPLINES = {"road_cycling", "enduro"}


def _split_mean(
    streams: list[ActivityStream], duration_s: int, attr: str
) -> tuple[float, float] | None:
    """Time-offset-aligned half means (first half vs second half), or None
    when either half lacks enough samples."""
    ordered = sorted(streams, key=lambda s: s.t_offset_s)
    split_s = duration_s / 2.0
    first: list[float] = []
    second: list[float] = []
    for sample in ordered:
        value = getattr(sample, attr)
        if value is None:
            continue
        (first if sample.t_offset_s < split_s else second).append(float(value))
    if len(first) < MIN_HALF_SAMPLES or len(second) < MIN_HALF_SAMPLES:
        return None
    return sum(first) / len(first), sum(second) / len(second)


def _time_weighted_mean(
    streams: list[ActivityStream], duration_s: int, attr: str
) -> float | None:
    """Mean weighted by each sample's interval — the time-correct average
    under varying sampling rates (the count-weighted mean is the bug §7
    warns about)."""
    ordered = sorted(streams, key=lambda s: s.t_offset_s)
    weighted = 0.0
    total_s = 0.0
    for i, sample in enumerate(ordered):
        value = getattr(sample, attr)
        if value is None:
            continue
        interval = (
            ordered[i + 1].t_offset_s - sample.t_offset_s
            if i + 1 < len(ordered)
            else duration_s - sample.t_offset_s
        )
        if interval <= 0:
            continue
        weighted += float(value) * interval
        total_s += interval
    if total_s <= 0:
        return None
    return weighted / total_s


def _sample_hold_power_at(
    powered: list[ActivityStream], t: float
) -> float:
    """Power at instant t under sample-and-hold (the power between samples is
    the last recorded value). `powered` must be sorted by t_offset_s."""
    value = 0.0
    for sample in powered:
        if sample.t_offset_s <= t:
            if sample.power is not None:
                value = float(sample.power)
        else:
            break
    return value


def normalized_power(streams: list[ActivityStream], duration_s: int) -> float | None:
    """Coggan NP: fourth root of the session mean of the 30-second rolling
    mean power raised to the 4th power. Power is read as sample-and-hold
    between samples; integration steps at 1s (personal scale, deterministic).
    Returns None without power data."""
    powered = sorted(
        (s for s in streams if s.power is not None),
        key=lambda s: s.t_offset_s,
    )
    if not powered or duration_s <= 0:
        return None
    step_s = 1.0
    total = 0.0
    t = 0.0
    window: list[float] = []  # trailing 30s of sample-and-hold power
    while t < duration_s:
        window.append(_sample_hold_power_at(powered, t))
        if len(window) > 30:
            window.pop(0)
        rolling_mean = sum(window) / len(window)
        total += rolling_mean**4
        t += step_s
    return (total / duration_s) ** 0.25


def best_mean_power(
    streams: list[ActivityStream], duration_s: int, window_s: int
) -> float | None:
    """Best mean power over any sliding `window_s` window (sample-and-hold
    integration). For a step function the window mean is piecewise linear in
    the window start; its max is therefore attained at a breakpoint: a sample
    offset, that offset shifted back by the window (the hold it leaves out
    enters), the domain edge 0, or the latest legal start. Anchoring only at
    sample offsets can miss the true best window (e.g. a hard finish after a
    long quiet warm-up)."""
    powered = sorted(
        (s for s in streams if s.power is not None),
        key=lambda s: s.t_offset_s,
    )
    if not powered or duration_s < window_s:
        return None
    offsets = [s.t_offset_s for s in powered]
    latest_start = duration_s - window_s
    starts = sorted(
        s
        for s in {0, latest_start, *offsets, *(o - window_s for o in offsets)}
        if 0 <= s <= latest_start
    )
    best: float | None = None
    for start in starts:
        end = start + window_s
        # Integrate sample-and-hold power over [start, end] segment by
        # segment: from t, the hold lasts until the next sample offset.
        total = 0.0
        t = start
        while t < end:
            i = bisect.bisect_right(offsets, t)
            next_edge = min(offsets[i], end) if i < len(offsets) else end
            total += _sample_hold_power_at(powered, t) * (next_edge - t)
            t = next_edge
        mean = total / window_s
        if best is None or mean > best:
            best = mean
    return best


def variability_index(streams: list[ActivityStream], duration_s: int) -> float | None:
    """NP / AP — the steady-effort criterion for the decoupling gate."""
    np_ = normalized_power(streams, duration_s)
    ap = _time_weighted_mean(streams, duration_s, "power")
    if np_ is None or ap is None or ap <= 0:
        return None
    return np_ / ap


def aerobic_decoupling(
    activity: Activity, streams: list[ActivityStream]
) -> float | None:
    """(first-half mean - second-half mean) / first-half mean, in percent,
    on HR (fallback: power for HR-less power sports). Time-offset aligned
    (§7); gated to steady-state efforts: a session WITH power must pass the
    VI <= 1.05 steadiness criterion regardless of which metric feeds the
    halves (an interval day's HR halves are meaningless), non-power sessions
    have no VI and are always computed (documented limitation)."""
    if activity.duration_s < MIN_SESSION_S:
        return None
    vi = variability_index(streams, activity.duration_s)
    if vi is not None and vi > STEADY_VI_MAX:
        return None
    if any(s.hr is not None for s in streams):
        halves = _split_mean(streams, activity.duration_s, "hr")
    elif vi is not None:  # power sport, HR-less
        halves = _split_mean(streams, activity.duration_s, "power")
    else:
        return None
    if halves is None:
        return None
    first, second = halves
    if first <= 0:
        return None
    return (first - second) / first * 100.0


def efficiency_factor(
    activity: Activity,
    streams: list[ActivityStream],
    discipline_name: str,
) -> float | None:
    """Cycling: NP / avg HR, where avg HR is the time-weighted stream mean
    when streams exist (the count-weighted mean would bias toward densely
    sampled segments — the §7 bug class), else the summary column. Other
    endurance: speed (m/min) / avg HR. Strength and technical disciplines:
    None (§17 — scoped, never pooled, and not meaningful off endurance
    modalities)."""
    if discipline_name not in CYCLING_DISCIPLINES and not _is_endurance_running_like(
        discipline_name
    ):
        return None
    if discipline_name in CYCLING_DISCIPLINES:
        np_ = normalized_power(streams, activity.duration_s)
        if np_ is None:
            return None
        avg_hr = _time_weighted_mean(streams, activity.duration_s, "hr")
        if avg_hr is None:
            avg_hr = float(activity.avg_hr) if activity.avg_hr is not None else None
        if avg_hr is None or avg_hr <= 0:
            return None
        return np_ / avg_hr
    if activity.avg_hr is None or activity.avg_hr <= 0:
        return None
    if activity.distance_m is None or activity.distance_m <= 0:
        return None
    speed_m_per_min = float(activity.distance_m) / (activity.duration_s / 60.0)
    return speed_m_per_min / activity.avg_hr


def _is_endurance_running_like(discipline_name: str) -> bool:
    """Endurance modalities where pace-based EF applies. The disciplines
    table is the source of truth for categories; this only picks the EF
    form (pace vs power) among endurance rows."""
    return discipline_name == "running"


def ftp_estimate(
    activity: Activity,
    streams: list[ActivityStream],
    ftp_model_type: str | None,
) -> float | None:
    """FTP estimate from a validated protocol only (§17)."""
    if ftp_model_type != "twenty_min_protocol":
        return None
    best = best_mean_power(streams, activity.duration_s, FTP_TWENTY_MIN_WINDOW_S)
    if best is None:
        return None
    return best * FTP_TWENTY_MIN_FACTOR
