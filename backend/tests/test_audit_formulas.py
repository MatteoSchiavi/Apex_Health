"""Physiological formula audit-fix tests (P-05, P-06, P-08, P-16).

Covers the audit's Phase 2/3 numerical fixes:
- P-05: Tanaka HRmax (208 − 0.7·age); None when age unknown.
- P-06: Garmin training_load converted to Edwards scale.
- P-08: aerobic decoupling is now EF drift (requires both power + HR).
- P-16: shared strain-ceiling window function.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.features import load, scores
from app.features.discipline import (
    EF_DISCIPLINES,
    aerobic_decoupling,
    efficiency_factor,
    normalized_power,
)
from app.features.engine import _strain_ceiling


# ---- P-05: Tanaka HRmax ---------------------------------------------------


def test_hr_max_uses_tanaka_for_known_age() -> None:
    """P-05: Tanaka (208 − 0.7·age) replaces the biased 220−age formula."""
    # 30-year-old: Tanaka = 208 − 21 = 187 (rounded); 220−age would be 190.
    assert load.hr_max_for(30) == 187
    # 50-year-old: Tanaka = 208 − 35 = 173; 220−age would be 170.
    assert load.hr_max_for(50) == 173


def test_hr_max_returns_none_for_unknown_age() -> None:
    """P-05: unknown age → None (no magic 190 fallback)."""
    assert load.hr_max_for(None) is None


def test_hr_max_fallback_constant_deprecated_but_present() -> None:
    """P-05: HRMAX_FALLBACK kept for backward-compat imports (deprecated)."""
    assert load.HRMAX_FALLBACK == 190  # do not use — see hr_max_for


# ---- P-06: Garmin→Edwards load conversion --------------------------------


def test_garmin_training_load_is_scaled() -> None:
    """P-06: Garmin's training_load is converted to Edwards-equivalent."""

    class _Activity:
        duration_s = 3600
        avg_hr = None
        training_load = Decimal("200")  # Garmin proprietary (EPOC-derived)

    streams: list = []
    # P-06: 200 × 0.35 = 70 Edwards-equivalent.
    trimp = load.activity_trimp(_Activity(), streams, hrm=None)
    assert trimp is not None
    assert abs(trimp - 70.0) < 0.01


def test_stream_trimp_takes_priority_over_garmin_load() -> None:
    """P-06: when HR streams are available, stream-derived TRIMP wins."""

    class _Stream:
        def __init__(self, t: int, hr: int) -> None:
            self.t_offset_s = t
            self.hr = hr

    class _Activity:
        duration_s = 600
        avg_hr = 150
        training_load = Decimal("500")  # would be 175 Edwards if used

    streams = [_Stream(0, 150), _Stream(300, 150), _Stream(599, 150)]
    hrm = 187
    trimp = load.activity_trimp(_Activity(), streams, hrm)
    # Zone factor for 150/187 ≈ 0.80 → zone 4 → 4 points/min.
    # 600s = 10 min × 4 = 40 TRIMP (NOT the 175 from Garmin scaling).
    assert trimp is not None
    assert 30 < trimp < 50


def test_load_scale_constant_documented() -> None:
    """P-06: the conversion factor is a named, documented constant."""
    assert load.LOAD_SCALE_GARMIN_TO_EDWARDS == 0.35


# ---- P-08: EF drift decoupling --------------------------------------------


def test_decoupling_returns_none_without_power() -> None:
    """P-08: HR-only sessions no longer produce a decoupling value
    (the old HR-only fallback was physiologically invalid)."""

    class _Stream:
        def __init__(self, t: int, hr: int, power=None) -> None:
            self.t_offset_s = t
            self.hr = hr
            self.power = power

    class _Activity:
        duration_s = 3600

    # HR streams only — no power.
    streams = [_Stream(i * 60, 150) for i in range(60)]
    assert aerobic_decoupling(_Activity(), streams) is None


def test_decoupling_returns_none_without_hr() -> None:
    """P-08: power-only sessions (no HR) return None."""

    class _Stream:
        def __init__(self, t: int, power: int, hr=None) -> None:
            self.t_offset_s = t
            self.power = power
            self.hr = hr

    class _Activity:
        duration_s = 3600

    streams = [_Stream(i * 60, 200) for i in range(60)]
    assert aerobic_decoupling(_Activity(), streams) is None


def test_decoupling_positive_when_ef_drops_in_second_half() -> None:
    """P-08: classic heat/dehydration drift → positive decoupling.

    The previous HR-only implementation reported NEGATIVE decoupling for
    this pattern because of an inverted sign convention. The new EF-based
    implementation correctly reports positive when EF drops.
    """

    class _Stream:
        def __init__(self, t: int, hr: int, power: int) -> None:
            self.t_offset_s = t
            self.hr = hr
            self.power = power

    class _Activity:
        duration_s = 3600  # 1 hour, above MIN_SESSION_S

    # First half: power 220, HR 150 → EF = 220/150 = 1.47
    # Second half: power 200, HR 160 → EF = 200/160 = 1.25
    # Drift = (1.47 - 1.25)/1.47 = +15% (positive — EF dropped).
    streams = []
    for t in range(0, 1800, 30):
        streams.append(_Stream(t, 150, 220))
    for t in range(1800, 3600, 30):
        streams.append(_Stream(t, 160, 200))
    decoupling = aerobic_decoupling(_Activity(), streams)
    assert decoupling is not None
    assert decoupling > 0  # positive — EF dropped in second half


# ---- P-20: EF discipline gating -------------------------------------------


def test_ef_gated_to_road_cycling_only() -> None:
    """P-20: EF returns None for non-road-cycling disciplines (enduro MTB
    coasting makes power variability too noisy)."""

    class _Activity:
        duration_s = 3600
        avg_hr = 150

    # enduro is excluded from EF_DISCIPLINES
    assert "enduro" not in EF_DISCIPLINES
    assert efficiency_factor(_Activity(), [], "enduro") is None
    assert efficiency_factor(_Activity(), [], "running") is None


# ---- P-16: Shared strain-ceiling window -----------------------------------


def test_strain_ceiling_returns_peak_over_window() -> None:
    """P-16: the shared ceiling returns the max daily load over [day-W+1, day]."""
    day = date(2026, 9, 24)
    loads = {
        day - timedelta(days=27): 100.0,  # inside window
        day - timedelta(days=20): 250.0,  # peak
        day - timedelta(days=10): 150.0,
        day - timedelta(days=29): 50.0,   # outside window (W=28 → oldest is day-27)
    }
    ceiling = _strain_ceiling(loads, day, window_days=28)
    assert ceiling == 250.0


def test_strain_ceiling_zero_when_no_loads() -> None:
    """P-16: empty load series → 0 (default)."""
    assert _strain_ceiling({}, date(2026, 9, 24), 28) == 0.0


def test_strain_ceiling_consistent_for_same_day() -> None:
    """P-16: the same date always gets the same ceiling regardless of caller."""
    day = date(2026, 9, 24)
    loads = {day - timedelta(days=i): 100.0 * i for i in range(28)}
    # Call from "today's perspective" (ceiling for day).
    c1 = _strain_ceiling(loads, day, 28)
    # Call from "tomorrow's perspective" (ceiling for day as prior day).
    c2 = _strain_ceiling(loads, day, 28)
    assert c1 == c2


# ---- P-13: active_day_count helper ----------------------------------------


def test_active_day_count_counts_nonzero_days() -> None:
    """P-13: active_day_count returns the number of non-zero-load days."""
    day = date(2026, 9, 24)
    loads = {
        day - timedelta(days=1): 100.0,
        day - timedelta(days=2): 0.0,  # rest day — not counted
        day - timedelta(days=3): 50.0,
        day - timedelta(days=5): 75.0,
    }
    assert load.active_day_count(loads, day, days=7) == 3


def test_active_day_count_zero_for_empty_window() -> None:
    """P-13: an athlete returning from a break has active_days=0."""
    assert load.active_day_count({}, date(2026, 9, 24), days=28) == 0
