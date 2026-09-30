"""Physiological safety + lab-data integrity tests (P-02, P-04, P-10, P-13).

Covers the audit's Phase 1 clinical-safety fixes:
- P-02: HRV/RHR/SpO2 plausibility validators drop sensor artifacts.
- P-04: deterministic exertion-veto interlock gates gym prescriptions.
- P-10: lab metrics without a measured value store NULL (never fabricated).
- P-13: injury-risk load-spike component does not max on a degenerate baseline.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.connectors.validation import (
    valid_body_battery,
    valid_hrv_ms,
    valid_respiration_bpm,
    valid_resting_hr_bpm,
    valid_sleep_score,
    valid_spo2_pct,
    valid_weight_kg,
)
from app.features import scores
from app.services.safety_interlock import (
    exertion_veto,
    impact_allowed_by_ceiling,
    safety_block,
)


# ---- P-02: Plausibility validators ----------------------------------------


@pytest.mark.parametrize("bad", [0.0, 0.5, 1.9, 400.1, 450.0, 5000.0, -10.0])
def test_implausible_hrv_is_dropped(bad: float) -> None:
    """P-02: HRV outside [2, 400] ms returns None (sensor artifact dropped)."""
    assert valid_hrv_ms(bad) is None


@pytest.mark.parametrize("good", [2.0, 25.0, 65.0, 120.0, 400.0])
def test_plausible_hrv_survives(good: float) -> None:
    """P-02: HRV inside [2, 400] ms returns the value (valid reading kept)."""
    assert valid_hrv_ms(good) == good


def test_hrv_decimal_input_is_coerced() -> None:
    """P-02: Decimal column values are coerced to float for the range check."""
    assert valid_hrv_ms(Decimal("65.0")) == 65.0
    assert valid_hrv_ms(Decimal("0.5")) is None


@pytest.mark.parametrize("bad", [10, 200, -5, 0])
def test_implausible_resting_hr_is_dropped(bad: int) -> None:
    """P-02: RHR outside [25, 120] bpm returns None."""
    assert valid_resting_hr_bpm(bad) is None


@pytest.mark.parametrize("bad", [50.0, 69.9, -1.0, 100.1, 150.0])
def test_implausible_spo2_is_dropped(bad: float) -> None:
    """P-02: SpO2 outside [70, 100] % returns None."""
    assert valid_spo2_pct(bad) is None


def test_plausible_spo2_survives() -> None:
    assert valid_spo2_pct(97.0) == 97.0
    assert valid_spo2_pct(70.0) == 70.0
    assert valid_spo2_pct(100.0) == 100.0


def test_implausible_sleep_score_dropped() -> None:
    assert valid_sleep_score(-1.0) is None
    assert valid_sleep_score(101.0) is None
    assert valid_sleep_score(75.0) == 75.0


def test_implausible_respiration_dropped() -> None:
    assert valid_respiration_bpm(2.0) is None
    assert valid_respiration_bpm(70.0) is None
    assert valid_respiration_bpm(15.0) == 15.0


def test_implausible_weight_dropped() -> None:
    assert valid_weight_kg(10.0) is None
    assert valid_weight_kg(500.0) is None
    assert valid_weight_kg(75.0) == 75.0


def test_implausible_body_battery_dropped() -> None:
    assert valid_body_battery(-1.0) is None
    assert valid_body_battery(101.0) is None
    assert valid_body_battery(50.0) == 50.0


def test_none_inputs_return_none() -> None:
    """P-02: None stays None (missing observation, not an artifact)."""
    assert valid_hrv_ms(None) is None
    assert valid_resting_hr_bpm(None) is None
    assert valid_spo2_pct(None) is None


# ---- P-04: Safety interlock ----------------------------------------------


def test_high_illness_risk_triggers_rest_veto() -> None:
    """P-04: illness_risk ≥ 70 → ceiling='rest', verdict blocks all work."""
    decision = exertion_veto(illness_risk=88, hrv_dev_pct=-31, rhr_dev_bpm=9)
    assert decision.vetoed is True
    assert decision.intensity_ceiling == "rest"
    assert any("illness" in r.lower() or "rest" in r.lower() for r in decision.reasons)


def test_high_injury_risk_caps_below_zone_3() -> None:
    """P-04: injury_risk ≥ 75 → ceiling='low' (cap below Zone 3)."""
    decision = exertion_veto(injury_risk=80)
    assert decision.vetoed is True
    assert decision.intensity_ceiling == "low"


def test_acwr_spike_replaces_high_impact() -> None:
    """P-04: ACWR > 1.5 → ceiling='low' (replace high-impact with volume)."""
    decision = exertion_veto(acwr=1.8)
    assert decision.vetoed is True
    assert decision.intensity_ceiling == "low"
    assert any("ACWR" in r for r in decision.reasons)


def test_combined_hrv_rhr_deviation_caps_at_moderate() -> None:
    """P-04: HRV ≤ -25% AND RHR ≥ +5bpm → ceiling='moderate'."""
    decision = exertion_veto(hrv_dev_pct=-30, rhr_dev_bpm=7)
    assert decision.vetoed is True
    assert decision.intensity_ceiling == "moderate"


def test_low_acwr_does_not_veto_but_notes_detraining() -> None:
    """P-03: ACWR < 0.8 is detraining — informative note, NOT a veto."""
    decision = exertion_veto(acwr=0.5)
    assert decision.vetoed is False
    assert any("detraining" in r.lower() for r in decision.reasons)


def test_no_risk_scores_no_veto() -> None:
    """P-04: absent inputs do NOT trigger a veto (graceful degradation)."""
    decision = exertion_veto()
    assert decision.vetoed is False
    assert decision.intensity_ceiling is None


def test_impact_allowed_by_ceiling_matrix() -> None:
    """P-04: the ceiling→impact lookup table is correct."""
    assert impact_allowed_by_ceiling("high", None) is True
    assert impact_allowed_by_ceiling("high", "rest") is False
    assert impact_allowed_by_ceiling("high", "low") is False
    assert impact_allowed_by_ceiling("high", "moderate") is False
    assert impact_allowed_by_ceiling("moderate", "moderate") is True
    assert impact_allowed_by_ceiling("low", "low") is True
    assert impact_allowed_by_ceiling("low", "rest") is False


def test_safety_block_with_no_feature_returns_go() -> None:
    """P-04/W-02: no scored day → verdict='go' (interlock not engaged)."""
    block = safety_block(None)
    assert block["verdict"] == "go"
    assert block["intensity_ceiling"] is None


def test_safety_block_with_high_illness_returns_rest() -> None:
    """W-02: the watch/agent contract surfaces verdict='rest' on illness."""

    class _StubFeature:
        illness_risk_score = Decimal("88")
        injury_risk_score = Decimal("30")
        acwr = Decimal("1.1")
        hrv_deviation_from_baseline = Decimal("-31")

    block = safety_block(_StubFeature())
    assert block["verdict"] == "rest"
    assert block["intensity_ceiling"] == "rest"
    assert block["risk_scores"]["illness_risk"] == 88.0


# ---- P-13: Degenerate-spike injury alarm ---------------------------------


def test_return_from_break_does_not_max_injury_risk() -> None:
    """P-13: an athlete returning from a 4-week break (active_days < 7)
    does NOT max injury risk on their first normal session.

    Before the fix: std=0 → spike=1.0 → injury_risk saturated.
    After the fix: active_days < 7 → load_spike_component returns 0.0.
    """
    # Day load 50, mean28 0, std28 0, active_days 0 — degenerate baseline.
    component = scores.load_spike_component(50.0, 0.0, 0.0, active_days=0)
    assert component == 0.0  # no full alarm on zero-variance baseline


def test_active_days_above_threshold_enables_spike() -> None:
    """P-13: with ≥7 active days the spike component activates normally."""
    # Std=0 but active_days=10 (baseline established) → spike fires when
    # today exceeds the mean.
    component = scores.load_spike_component(50.0, 30.0, 0.0, active_days=10)
    assert component == 1.0


def test_injury_risk_score_passes_active_days() -> None:
    """P-13: the composite injury_risk_score honors the active_days gate."""
    weights = {"acwr_spike": 0.5, "load_spike": 0.5}
    # With active_days=0 the load_spike component is 0; with acwr=1.0 (no
    # spike) the composite should be 0.
    risk = scores.injury_risk_score(weights, acwr=1.0, day_load=50.0, mean28=0.0, std28=0.0, active_days=0)
    assert risk == 0.0


# ---- P-10: Lab fabrication ------------------------------------------------


def test_lab_metric_value_can_be_null() -> None:
    """P-10: a LabMetric with no measured value is constructed with value=None.

    The record_lab_panel function used to default missing values to ref_low
    or 0. The fix stores None; this test confirms the LabMetric model
    accepts None (the migration already permits it).
    """
    from app.models.medical import LabMetric

    metric = LabMetric(
        lab_panel_id=1,
        metric_name="ferritin",
        value=None,  # P-10: NULL when not measured
        unit="ng/mL",
        ref_low=Decimal("30"),
        ref_high=Decimal("400"),
    )
    assert metric.value is None
    assert metric.ref_low == Decimal("30")
