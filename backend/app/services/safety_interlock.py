"""Deterministic safety interlock for training prescription (P-04, W-02 audit).

Conservative planning rules applied before prescription. These heuristic
signals and load ratios do not diagnose illness, predict injury or establish
that a proposed workout is safe. Existing caps are product guardrails, not
clinically validated thresholds. Missing inputs leave this interlock
uninformed; the separate coverage and symptom rules still apply.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, SupportsFloat

logger = logging.getLogger("services.safety_interlock")

# Product guardrails retained conservatively; no calibrated clinical validity.
SYSTEMIC_STRESS_VETO_THRESHOLD = 70.0       # ≥70 → rest or mobility only
LOAD_SPIKE_VETO_THRESHOLD = 75.0        # ≥75 → cap below Zone 3
ACWR_HIGH_VETO = 1.5                     # >1.5 → replace high-impact with low
ACWR_LOW_CONTEXT = 0.8                  # lower recent load; no detraining inference
HRV_DEV_DEVIATION_BPM = -25.0            # HRV ≥25% below baseline → descriptive deviation
RHR_DEV_ELEVATION_BPM = 5.0              # RHR ≥5bpm above baseline → descriptive deviation


@dataclass(frozen=True)
class VetoDecision:
    """Result of ``exertion_veto`` — the prescription contract."""

    vetoed: bool
    intensity_ceiling: str | None  # None | "rest" | "low" | "moderate"
    reasons: tuple[str, ...]

    @property
    def message(self) -> str | None:
        return " | ".join(self.reasons) if self.reasons else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, SupportsFloat):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def exertion_veto(
    *,
    systemic_stress: Any | None = None,
    load_spike: Any | None = None,
    acwr: Any | None = None,
    hrv_dev_pct: Any | None = None,
    rhr_dev_bpm: Any | None = None,
) -> VetoDecision:
    """Return the veto decision for a single day's prescription.

    Inputs come from the latest ``DailyFeature`` row (computed by the feature
    engine). Any input may be None — the veto is computed from whatever is
    available; absent inputs do NOT trigger a veto (the engine's
    data_completeness flag already marks such days partial).

    The returned ``intensity_ceiling`` is the highest intensity permitted:

    - ``None`` — no veto, prescription proceeds unchanged.
    - ``"rest"`` — rest or mobility only; drop all high/moderate impact.
    - ``"low"`` — cap at low impact (Zone 1-2 equivalent).
    - ``"moderate"`` — cap below Zone 3 (drop high impact only).

    ``reasons`` carries one human-readable sentence per triggered rule; the
    caller appends these to the user-facing notes so the athlete understands
    WHY the workout was modified.
    """
    reasons: list[str] = []
    ceiling: str | None = None

    illness = _to_float(systemic_stress)
    injury = _to_float(load_spike)
    acwr_v = _to_float(acwr)
    hrv_dev = _to_float(hrv_dev_pct)
    rhr_dev = _to_float(rhr_dev_bpm)

    # P-04: systemic stress heuristic dominates — full rest veto.
    if illness is not None and illness >= SYSTEMIC_STRESS_VETO_THRESHOLD:
        ceiling = "rest"
        reasons.append(
            f"Systemic stress signal elevated ({illness:.0f}/100): rest or mobility only."
        )

    # P-04: acute load spike — cap below Zone 3.
    if injury is not None and injury >= LOAD_SPIKE_VETO_THRESHOLD:
        ceiling = "low" if ceiling is None else ceiling
        if ceiling != "rest":
            ceiling = "low"
        reasons.append(
            f"Acute load spike (load spike indicator {injury:.0f}/100): cap intensity below Zone 3."
        )

    # P-04: ACWR > 1.5 — replace high-impact with low-impact volume.
    if acwr_v is not None and acwr_v > ACWR_HIGH_VETO:
        ceiling = "low" if ceiling is None else ceiling
        if ceiling != "rest":
            ceiling = "low"
        reasons.append(
            f"ACWR {acwr_v:.2f} > 1.5: replace high-impact work with low-impact volume."
        )

    # P-04 secondary triggers (HRV/RHR deviations) — only fire when the
    # composite scores did not already veto (avoids double-counting).
    if ceiling is None:
        hrv_signal = hrv_dev is not None and hrv_dev <= HRV_DEV_DEVIATION_BPM
        rhr_signal = rhr_dev is not None and rhr_dev >= RHR_DEV_ELEVATION_BPM
        if hrv_signal and rhr_signal:
            ceiling = "moderate"
            reasons.append(
                f"Recovery suppressed (HRV {hrv_dev:+.0f}%, RHR {rhr_dev:+.0f}bpm vs baseline): "
                "cap at moderate intensity."
            )

    # Lower recent load is context, not proof of detraining or a health band.
    advisory_notes: list[str] = []
    if acwr_v is not None and acwr_v < ACWR_LOW_CONTEXT:
        advisory_notes.append(
            f"ACWR {acwr_v:.2f} < 0.8: recent recorded load is lower than its "
            "longer-window average. Consider training history before increasing intensity."
        )

    # A veto requires an intensity_ceiling — informative notes alone do NOT
    # count as a veto (the prescription proceeds, with the note appended).
    if ceiling is None:
        if advisory_notes:
            # Advisory notes only — no veto, but the caller still surfaces them.
            return VetoDecision(
                vetoed=False,
                intensity_ceiling=None,
                reasons=tuple(advisory_notes),
            )
        return VetoDecision(vetoed=False, intensity_ceiling=None, reasons=())
    # Veto + any advisory notes are merged so the caller sees everything.
    return VetoDecision(
        vetoed=True,
        intensity_ceiling=ceiling,
        reasons=tuple(reasons + advisory_notes),
    )


# Impact-level ordering used by gym_advisor to compare against the ceiling.
# 'low' < 'moderate' < 'high' — a ceiling of 'moderate' permits low+moderate
# but not high; 'low' permits low only; 'rest' permits nothing.
_IMPACT_ORDER = {"low": 0, "moderate": 1, "high": 2}
_CEILING_MAX = {"rest": -1, "low": 0, "moderate": 1}


def impact_allowed_by_ceiling(impact_level: str | None, ceiling: str | None) -> bool:
    """True when ``impact_level`` is at or below ``ceiling``.

    ``ceiling=None`` → everything allowed.
    ``ceiling='rest'`` → nothing allowed (caller drops all rows).
    ``ceiling='low'`` → only low-impact allowed.
    ``ceiling='moderate'`` → low and moderate allowed, high dropped.
    Unknown impact levels are treated as 'moderate' (conservative default).
    """
    if ceiling is None:
        return True
    if ceiling == "rest":
        return False
    impact_rank = _IMPACT_ORDER.get((impact_level or "moderate").lower(), 1)
    ceiling_rank = _CEILING_MAX.get(ceiling, 1)
    return impact_rank <= ceiling_rank


def safety_block(feature: Any | None) -> dict:
    """Build the machine-readable safety-interlock block injected into the
    agent's system context and the watch payload (W-02 contract).

    ``feature`` is the latest ``DailyFeature`` row (or None when no scored
    day exists). The block carries:

    - ``verdict``: ``"go"`` | ``"modify"`` | ``"rest"`` — the machine-readable
      contract the watch/agent consumes.
    - ``intensity_ceiling``: None | "rest" | "low" | "moderate".
    - ``reasons``: list of human-readable strings (may be empty).
    - ``risk_scores``: the raw scores used (for transparency/debugging).
    """
    if feature is None:
        return {
            "verdict": "go",
            "intensity_ceiling": None,
            "reasons": [],
            "risk_scores": {},
            "note": "no scored day available — safety interlock not engaged",
        }
    decision = exertion_veto(
        systemic_stress=getattr(feature, "systemic_stress_signal", None),
        load_spike=getattr(feature, "load_spike_indicator", None),
        acwr=getattr(feature, "acwr", None),
        hrv_dev_pct=getattr(feature, "hrv_deviation_from_baseline", None),
        rhr_dev_bpm=None,  # not stored on DailyFeature directly
    )
    if not decision.vetoed:
        verdict = "go"
    elif decision.intensity_ceiling == "rest":
        verdict = "rest"
    else:
        verdict = "modify"
    return {
        "verdict": verdict,
        "intensity_ceiling": decision.intensity_ceiling,
        "reasons": list(decision.reasons),
        "risk_scores": {
            "systemic_stress": _to_float(getattr(feature, "systemic_stress_signal", None)),
            "load_spike": _to_float(getattr(feature, "load_spike_indicator", None)),
            "acwr": _to_float(getattr(feature, "acwr", None)),
            "hrv_dev_pct": _to_float(getattr(feature, "hrv_deviation_from_baseline", None)),
        },
    }
