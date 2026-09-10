"""Composite daily scores (§7): recovery, strain, readiness, sleep
architecture, illness risk, injury risk, cross-discipline fatigue index.

Design laws:
- Blend weights ALWAYS come from feature_weights via the §6.4 selection rule
  (the engine passes them in); nothing here hardcodes a blend weight (§17).
- Component values are normalized to 0..1 before blending; a composite is the
  weighted mean over AVAILABLE components, renormalized by their weights —
  never padded with invented values. None components are simply absent; a
  composite over zero available components is None.
- Functional-form constants (saturation points like "a 30% HRV drop is a
  full illness signal") are code constants, versioned by the golden-dataset
  regression tests — the weights table owns blend weights, not formulas.
- All scores are 0..100; the cross-discipline fatigue index is an unbounded
  unitless index.
"""

from datetime import date, timedelta

from app.features.baselines import BASELINE_DAYS
from app.features.load import STRAIN_CEILING_FLOOR

# --- component normalizations (0..1) --------------------------------------


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def hrv_recovery_component(dev_pct: float) -> float:
    """0.5 at baseline; a ±25% deviation saturates the full 0..1 swing."""
    return clamp01(0.5 + dev_pct / 50.0)


def resting_hr_component(dev_bpm: float) -> float:
    """1.0 at baseline; each bpm of elevation costs 1/10 of the range."""
    return clamp01(1.0 - dev_bpm / 10.0)


def sleep_quality_component(sleep_score: float) -> float:
    return clamp01(sleep_score / 100.0)


def prior_day_strain_component(prior_strain_score: float) -> float:
    return clamp01(1.0 - prior_strain_score / 100.0)


def rem_component(rem_pct: float) -> float:
    """10% -> 0, 25% -> 1 (typical healthy REM sits near the top)."""
    return clamp01((rem_pct - 10.0) / 15.0)


def deep_component(deep_pct: float) -> float:
    """10% -> 0, 23% -> 1."""
    return clamp01((deep_pct - 10.0) / 13.0)


def efficiency_component(total_sleep_s: float, awake_s: float) -> float:
    """Share of time in bed spent asleep."""
    if total_sleep_s + awake_s <= 0:
        return 0.0
    return clamp01(total_sleep_s / (total_sleep_s + awake_s))


def hrv_drop_component(dev_pct: float) -> float:
    """A 30% drop below baseline is a full illness signal; rises count 0."""
    return clamp01(-dev_pct / 30.0)


def resting_hr_elevation_component(dev_bpm: float) -> float:
    """+8 bpm over baseline is a full signal; drops count 0."""
    return clamp01(dev_bpm / 8.0)


def respiration_elevation_component(dev_pct: float) -> float:
    """+10% over baseline is a full signal."""
    return clamp01(dev_pct / 10.0)


def acwr_readiness_component(acwr: float) -> float:
    """Sweet spot 0.8-1.3 -> 1.0; ramping above 1.3 folds to 0 at 2.0;
    detraining below 0.8 scales linearly to 0 at 0.0."""
    if acwr > 1.3:
        return clamp01(1.0 - (acwr - 1.3) / 0.7)
    if acwr < 0.8:
        return clamp01(acwr / 0.8)
    return 1.0


def acwr_spike_component(acwr: float) -> float:
    """Injury-signal side only: 1.3 -> 0, 2.0 -> 1."""
    return clamp01((acwr - 1.3) / 0.7)


def load_spike_component(day_load: float, mean28: float, std28: float) -> float:
    """Today's load vs. the personal distribution; 2 std above the mean is a
    full spike. A degenerate (zero-variance) distribution spikes only if
    today actually exceeds the mean."""
    if std28 <= 0:
        return 1.0 if day_load > mean28 else 0.0
    return clamp01((day_load - mean28) / (2.0 * std28))


# --- blending --------------------------------------------------------------


def blend(
    components: dict[str, float | None], weights: dict[str, float]
) -> float | None:
    """Weighted mean over available components, renormalized by their active
    weights. None if nothing usable survives (missing weight rows count as
    absent — the weights table is the source of truth)."""
    active = [
        (weights[name], value)
        for name, value in components.items()
        if value is not None and name in weights
    ]
    if not active:
        return None
    total_weight = sum(w for w, _ in active)
    if total_weight <= 0:
        return None
    return sum(w * v for w, v in active) / total_weight


# --- composites ------------------------------------------------------------


def recovery_score(
    weights: dict[str, float],
    hrv_dev_pct: float | None,
    resting_hr_dev_bpm: float | None,
    sleep_score: float | None,
    prior_strain_score: float | None,
) -> float | None:
    value = blend(
        {
            "hrv_deviation": None
            if hrv_dev_pct is None
            else hrv_recovery_component(hrv_dev_pct),
            "resting_hr_deviation": None
            if resting_hr_dev_bpm is None
            else resting_hr_component(resting_hr_dev_bpm),
            "sleep_quality": None
            if sleep_score is None
            else sleep_quality_component(sleep_score),
            "prior_day_strain": None
            if prior_strain_score is None
            else prior_day_strain_component(prior_strain_score),
        },
        weights,
    )
    return None if value is None else value * 100.0


def strain_score(day_load: float, peak28: float | None) -> float:
    """Daily cardiovascular load normalized against a personal ceiling: the
    28-day peak daily load, floored so early history (or a deload block) can
    never make a normal day read as maximal. Including today keeps the scale
    self-consistent — the hardest day of the window reads 100."""
    ceiling = max(peak28 if peak28 is not None else 0.0, STRAIN_CEILING_FLOOR)
    return min(100.0, max(0.0, day_load / ceiling * 100.0))


def sleep_architecture_score(
    weights: dict[str, float],
    rem_pct: float | None,
    deep_pct: float | None,
    total_sleep_s: float | None,
    awake_s: float | None,
) -> float | None:
    """REM%, deep% and efficiency vs. personal baselines (§7). Latency and
    circadian regularity need fields the §6.4 schema does not carry yet —
    v1 covers the three measurable components; the gap is structural, not a
    data-completeness issue."""
    value = blend(
        {
            "rem_pct": None if rem_pct is None else rem_component(rem_pct),
            "deep_pct": None if deep_pct is None else deep_component(deep_pct),
            "efficiency": None
            if total_sleep_s is None or awake_s is None
            else efficiency_component(total_sleep_s, awake_s),
        },
        weights,
    )
    return None if value is None else value * 100.0


def readiness_score(
    weights: dict[str, float],
    recovery: float | None,
    sleep_architecture: float | None,
    acwr: float | None,
) -> float | None:
    """The single most important daily number (§7): recovery, sleep
    architecture and acute:chronic balance."""
    value = blend(
        {
            "recovery": None if recovery is None else recovery / 100.0,
            "sleep_architecture": None
            if sleep_architecture is None
            else sleep_architecture / 100.0,
            "acwr": None if acwr is None else acwr_readiness_component(acwr),
        },
        weights,
    )
    return None if value is None else value * 100.0


def illness_risk_score(
    weights: dict[str, float],
    hrv_dev_pct: float | None,
    resting_hr_dev_bpm: float | None,
    respiration_dev_pct: float | None,
) -> float | None:
    """§7: HRV drop + resting-HR elevation + elevated respiration + journal
    soreness/fatigue. The journal component is part of the feature definition
    (its weight is seeded) but no journal source exists until the medical /
    lifestyle module — it stays structurally absent, which does NOT flag the
    day partial (that flag tracks sensor data, §17)."""
    value = blend(
        {
            "hrv_drop": None
            if hrv_dev_pct is None
            else hrv_drop_component(hrv_dev_pct),
            "resting_hr_elevation": None
            if resting_hr_dev_bpm is None
            else resting_hr_elevation_component(resting_hr_dev_bpm),
            "respiration_elevation": None
            if respiration_dev_pct is None
            else respiration_elevation_component(respiration_dev_pct),
            "journal_soreness_fatigue": None,  # no journal source yet
        },
        weights,
    )
    return None if value is None else value * 100.0


def injury_risk_score(
    weights: dict[str, float],
    acwr: float | None,
    day_load: float | None,
    mean28: float | None,
    std28: float | None,
) -> float | None:
    value = blend(
        {
            "acwr_spike": None if acwr is None else acwr_spike_component(acwr),
            "load_spike": None
            if day_load is None or mean28 is None or std28 is None
            else load_spike_component(day_load, mean28, std28),
        },
        weights,
    )
    return None if value is None else value * 100.0


def cross_discipline_fatigue_index(
    discipline_loads: dict[str, dict[date, float]],
    day: date,
) -> float | None:
    """Load aggregated across the disciplines active in the last 7 days,
    each with an exponential decay (half-life 3 days) and normalized by that
    discipline's own 28-day peak daily load INCLUDING today (floored at 1.0)
    — including today keeps a discipline's first-ever session from dividing
    by the floor and exploding, the same self-consistent scale the strain
    ceiling uses. A discipline bleeding fatigue into another is what
    single-sport platforms cannot see (§7). None when nothing was active."""
    total = 0.0
    any_active = False
    for loads in discipline_loads.values():
        recent = [loads.get(day - timedelta(days=i), 0.0) for i in range(7)]
        if not any(recent):
            continue
        any_active = True
        peak = max(
            (loads.get(day - timedelta(days=i), 0.0) for i in range(BASELINE_DAYS)),
            default=0.0,
        )
        decayed = sum(
            load * 0.5 ** (i / 3.0) for i, load in enumerate(recent)
        )
        total += decayed / max(peak, 1.0)
    return total if any_active else None
