"""Deterministic safety interlock for training prescription (P-04, W-02 audit).

A hard-coded veto layer that runs BEFORE any coaching prescription is
generated. The deterministic risk scores (`illness_risk`, `injury_risk`,
`acwr`) are computed by the feature engine but were never consulted by
``gym_advisor.adjust()`` — the audit (P-04) flags this as a medical-safety
defect because non-deterministic LLM prompting is the only thing standing
between a sick athlete and a hard interval prescription.

This module is the single canonical source of veto rules. Every prescription
path (gym_advisor, watch glance, agent planner) calls ``exertion_veto``
BEFORE returning its prescription; the veto either:

- Returns ``None`` — no veto, prescription proceeds as planned.
- Returns a non-empty message — the prescription MUST be capped at the
  declared intensity ceiling and the message appended to the user-facing
  notes.

The veto is intentionally conservative: false positives (unnecessary rest)
are recoverable, false negatives (prescribing hard work during illness) are
not. Athletes can always override via journal feedback — the veto just
guarantees the DEFAULT path is safe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, SupportsFloat

logger = logging.getLogger("services.safety_interlock")

# Veto thresholds — clinical-grade triggers from the audit (P-04) and
# sports-medicine literature (Gabbett ACWR, Buchheit HRV).
ILLNESS_RISK_VETO_THRESHOLD = 70.0       # ≥70 → rest or mobility only
INJURY_RISK_VETO_THRESHOLD = 75.0        # ≥75 → cap below Zone 3
ACWR_HIGH_VETO = 1.5                     # >1.5 → replace high-impact with low
ACWR_LOW_DETRAINING = 0.8                # <0.8 → detraining band (P-03)
HRV_DEV_DEVIATION_BPM = -25.0            # HRV ≥25% below baseline → illness signal
RHR_DEV_ELEVATION_BPM = 5.0              # RHR ≥5bpm above baseline → illness signal


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
    illness_risk: Any | None = None,
    injury_risk: Any | None = None,
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

    illness = _to_float(illness_risk)
    injury = _to_float(injury_risk)
    acwr_v = _to_float(acwr)
    hrv_dev = _to_float(hrv_dev_pct)
    rhr_dev = _to_float(rhr_dev_bpm)

    # P-04: illness risk dominates — full rest veto.
    if illness is not None and illness >= ILLNESS_RISK_VETO_THRESHOLD:
        ceiling = "rest"
        reasons.append(
            f"Illness-risk elevated ({illness:.0f}/100): rest or mobility only."
        )

    # P-04: acute load spike — cap below Zone 3.
    if injury is not None and injury >= INJURY_RISK_VETO_THRESHOLD:
        ceiling = "low" if ceiling is None else ceiling
        if ceiling != "rest":
            ceiling = "low"
        reasons.append(
            f"Acute load spike (injury risk {injury:.0f}/100): cap intensity below Zone 3."
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

    # P-03: ACWR < 0.8 — detraining band, NOT a veto. Informative note only.
    # The athlete is undertrained; prescribing hard work is wrong but
    # prescription is not blocked — they need progressive rebuild, not rest.
    # Tracked separately so it doesn't flip `vetoed` (a veto requires an
    # intensity_ceiling; an informative note does not block prescription).
    advisory_notes: list[str] = []
    if acwr_v is not None and acwr_v < ACWR_LOW_DETRAINING:
        advisory_notes.append(
            f"ACWR {acwr_v:.2f} < 0.8 indicates detraining — recommend progressive "
            "rebuild rather than peak intensity."
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
        illness_risk=getattr(feature, "illness_risk_score", None),
        injury_risk=getattr(feature, "injury_risk_score", None),
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
            "illness_risk": _to_float(getattr(feature, "illness_risk_score", None)),
            "injury_risk": _to_float(getattr(feature, "injury_risk_score", None)),
            "acwr": _to_float(getattr(feature, "acwr", None)),
            "hrv_dev_pct": _to_float(getattr(feature, "hrv_deviation_from_baseline", None)),
        },
    }
