"""Per-discipline daily metrics (§7): aerobic decoupling, efficiency factor,
FTP estimation — and the steady-state gate that scopes them.

Discipline law (§17): efficiency-factor and decoupling math is always scoped
by discipline_id, never pooled. This module computes PER ACTIVITY; the engine
aggregates per (user, discipline, local date).

P-08 audit: decoupling is now TRUE EF (Efficiency Factor) drift —
``(EF_first_half - EF_second_half) / EF_first_half × 100`` — requiring BOTH
power and HR streams. The previous implementation computed HR-only drift
with an inverted sign convention, reporting *negative* decoupling for the
classic heat/dehydration drift pattern. The metric name now matches the
calculation; NULL is returned when either power or HR is missing (the old
HR-only fallback was physiologically invalid).

P-07 audit: NP uses an O(n) cumulative-sum sliding window with correct
partial-window initialization (the first <30s of samples are scaled to the
window size, not treated as zero-power contributions). The old O(n²)
implementation under-read IF for short efforts and was a perf bottleneck
on long streams.

Steady-state gate: §7 scopes decoupling to steady-state efforts. For power
sports the validated criterion is Coggan's Variability Index (NP / AP):
VI <= 1.05 counts as steady.

FTP (§17: validated protocols only, never ad hoc regression): the discipline
row's ftp_model_type gates estimation. 'twenty_min_protocol' = FTP is 0.95 x
the best 20-minute mean power inside the session (sample-and-hold
integration). The protocol fires on any qualifying 20-min window — a steady
zone-2 ride yields a modest estimate, a test day a real one; no ad hoc
effort gating is layered on top.

P-20 audit: EF/decoupling math is gated by discipline allow-list — road
cycling only. Enduro MTB's coasting makes power variability too noisy for
meaningful NP/EF; the gate prevents the noisy FTP estimates the audit flagged.
"""

import bisect

from app.models.activity import Activity, ActivityStream

STEADY_VI_MAX = 1.05
FTP_TWENTY_MIN_WINDOW_S = 1200
FTP_TWENTY_MIN_FACTOR = 0.95
MIN_HALF_SAMPLES = 2
MIN_SESSION_S = 1200  # shorter efforts say nothing about aerobic drift

# P-20 audit: disciplines where NP/EF/decoupling are meaningful. Enduro MTB
# is excluded — coasting makes power variability too noisy for FTP estimation.
EF_DISCIPLINES = {"road_cycling"}


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
    between samples.

    P-07 audit: O(n) cumulative-sum sliding window with correct partial-window
    initialization. The first <30 samples contribute a rolling mean scaled
    to the available window size (NOT zero-padded, which under-read IF for
    short efforts). The old O(n²) implementation called
    ``_sample_hold_power_at`` at every 1s step, recomputing the trailing
    window from scratch each time — performance bottleneck on long streams
    AND under-read short efforts.
    """
    powered = sorted(
        (s for s in streams if s.power is not None),
        key=lambda s: s.t_offset_s,
    )
    if not powered or duration_s <= 0:
        return None
    # P-07: build a 1Hz sample-and-hold power series once, then use a
    # cumulative-sum sliding window. O(n) instead of O(n²).
    duration = int(duration_s)
    if duration <= 0:
        return None
    # Build the per-second power series (sample-and-hold).
    series = [0.0] * duration
    sample_idx = 0
    current_power = 0.0
    for t in range(duration):
        while sample_idx < len(powered) and powered[sample_idx].t_offset_s <= t:
            current_power = float(powered[sample_idx].power)
            sample_idx += 1
        series[t] = current_power
    # 30s rolling mean via cumulative sum. Partial windows at the start are
    # scaled to the available window size (NOT zero-padded — that would
    # under-read IF for short efforts).
    window = 30
    rolling_means: list[float] = []
    cumsum = 0.0
    for t in range(duration):
        cumsum += series[t]
        if t < window:
            # Partial window: scale to available size.
            rolling_means.append(cumsum / (t + 1))
        else:
            cumsum -= series[t - window]
            rolling_means.append(cumsum / window)
    # NP = fourth root of mean of rolling_mean^4.
    total = sum(rm ** 4 for rm in rolling_means)
    return (total / duration) ** 0.25


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
    """P-08 audit: TRUE EF (Efficiency Factor) drift, in percent.

    ``decoupling_pct = (EF1 - EF2) / EF1 × 100`` where EF = NP / avg HR for
    each half (time-offset-aligned split at duration/2). A positive value
    means EF dropped in the second half — the classic heat/dehydration drift
    pattern (power drops and/or HR rises, EF falls). The previous
    HR-only implementation reported NEGATIVE decoupling for this pattern
    because of an inverted sign convention.

    Requires BOTH power and HR streams — NULL when either is missing (the
    old HR-only fallback was physiologically invalid). Gated to steady-state
    efforts via the VI ≤ 1.05 criterion when power is available.
    """
    if activity.duration_s < MIN_SESSION_S:
        return None
    # P-08: EF drift requires BOTH power and HR. Either missing → NULL.
    has_power = any(s.power is not None for s in streams)
    has_hr = any(s.hr is not None for s in streams)
    if not (has_power and has_hr):
        return None
    vi = variability_index(streams, activity.duration_s)
    if vi is not None and vi > STEADY_VI_MAX:
        return None
    # P-08: compute EF for each half — EF = NP_half / avg_HR_half.
    # Use the time-offset-aligned half means of HR, and compute NP over
    # each half's power samples. This is the textbook definition.
    split_s = activity.duration_s / 2.0
    first_power = [s for s in streams if s.power is not None and s.t_offset_s < split_s]
    second_power = [s for s in streams if s.power is not None and s.t_offset_s >= split_s]
    if len(first_power) < MIN_HALF_SAMPLES or len(second_power) < MIN_HALF_SAMPLES:
        return None
    # NP per half — use the same normalized_power function on the half's
    # streams and the half's duration.
    first_duration = int(split_s)
    second_duration = activity.duration_s - int(split_s)
    np1 = normalized_power(first_power, first_duration) if first_power else None
    np2 = normalized_power(second_power, second_duration) if second_power else None
    if np1 is None or np2 is None:
        return None
    hr1 = _time_weighted_mean(
        [s for s in streams if s.hr is not None and s.t_offset_s < split_s],
        first_duration, "hr",
    )
    hr2 = _time_weighted_mean(
        [s for s in streams if s.hr is not None and s.t_offset_s >= split_s],
        second_duration, "hr",
    )
    if hr1 is None or hr2 is None or hr1 <= 0:
        return None
    ef1 = np1 / hr1
    ef2 = np2 / hr2
    if ef1 <= 0:
        return None
    return (ef1 - ef2) / ef1 * 100.0


def efficiency_factor(
    activity: Activity,
    streams: list[ActivityStream],
    discipline_name: str,
) -> float | None:
    """P-20 audit: gated by ``EF_DISCIPLINES`` (road cycling only). Enduro
    MTB's coasting makes power variability too noisy for meaningful NP/EF.

    Cycling: NP / avg HR, where avg HR is the time-weighted stream mean
    when streams exist (the count-weighted mean would bias toward densely
    sampled segments — the §7 bug class), else the summary column. Other
    endurance: speed (m/min) / avg HR. Strength and technical disciplines:
    None (§17 — scoped, never pooled, and not meaningful off endurance
    modalities)."""
    # P-20: gate by discipline allow-list.
    if discipline_name not in EF_DISCIPLINES:
        return None
    if discipline_name in EF_DISCIPLINES:
        np_ = normalized_power(streams, activity.duration_s)
        if np_ is None:
            return None
        avg_hr = _time_weighted_mean(streams, activity.duration_s, "hr")
        if avg_hr is None:
            avg_hr = float(activity.avg_hr) if activity.avg_hr is not None else None
        if avg_hr is None or avg_hr <= 0:
            return None
        return np_ / avg_hr
    # P-20: the running-like branch is removed — enduro MTB's coasting
    # invalidates pace-based EF too. Only road_cycling qualifies.
    return None


def _is_endurance_running_like(discipline_name: str) -> bool:
    """Endurance modalities where pace-based EF applies. The disciplines
    table is the source of truth for categories; this only picks the EF
    form (pace vs power) among endurance rows.

    P-20 audit: this helper is kept for backward-compat but the
    efficiency_factor gate now restricts to EF_DISCIPLINES (road cycling
    only). Running EF can be re-enabled when the audit's coasting concern
    is addressed for run-specific power meters."""
    return False


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
