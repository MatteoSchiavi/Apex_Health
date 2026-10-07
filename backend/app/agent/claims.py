"""Pure lexical safety and epistemic claim checks for the answer boundary.

This detects explicit unsafe statements, not clinical truth or all possible
paraphrases. Evidence matching and association recipe eligibility remain the
runtime's responsibility. A passed lexical check is never clinical validation.
"""

import re
from math import isfinite

CLAIM_KINDS = frozenset({"MEASURED", "CALCULATED", "ASSOCIATION", "HYPOTHESIS", "UNKNOWN"})
CLAIM_FIELDS = frozenset({"evidence_id", "metric", "value", "kind", "unit"})
_CAUSAL = re.compile(
    r"\b(?:caused?|causes|guarantees?|will prevent|proves? that|will improve by|"
    r"ha causato|causa|garantisce|preverrà|dimostra che)\b", re.I)
_NEGATION = re.compile(
    r"\b(?:not|never|no|cannot|can't|doesn't|don't|do not|does not|did not|"
    r"non|mai|nessuna|impossibile)\b", re.I)
_UNCERTAINTY = re.compile(
    r"\b(?:may|might|could|hypothesis|hypothes(?:is|es)|association|uncertain|"
    r"whether|possible|possibly|ipot(?:esi|etico)|potrebbe|associazione)\b", re.I)
_RED_FLAGS = re.compile(
    r"\b(?:fever|illness|chest pain|sharp pain|severe pain|fainting|infection|"
    r"febbre|malattia|dolore toracico|dolore acuto|svenimento|infezione)\b", re.I)
_TRAIN_HARD = re.compile(
    r"\b(?:train hard|training hard|hard training|intense training|push through|"
    r"continue (?:hard|intense)|safe to train|allenati intensamente|"
    r"allenamento intenso|spingi comunque)\b", re.I)
_DIAGNOSIS = re.compile(
    r"\b(?:i diagnose|you (?:definitely |certainly )?have (?:myocarditis|"
    r"a heart attack|a disease|an infection)|this (?:confirms|proves) (?:a |your )?diagnosis|"
    r"diagnostico|hai sicuramente|conferma la diagnosi)\b", re.I)
_MEDICATION = re.compile(
    r"\b(?:increase (?:your |the )?(?:prescribed )?(?:dose|dosage)|"
    r"stop (?:your |the )?prescribed|double (?:your |the )?(?:dose|dosage)|"
    r"raddoppia la dose|interrompi (?:il|la) farmac)\b", re.I)


def validate_claim_kind(claim: dict, *, is_analysis: bool) -> str:
    """Return canonical kind or raise ValueError for unsupported claim shapes.

    Legacy claims retain their measured/registered-calculation interpretation.
    ASSOCIATION requires a registered association analysis check by the caller.
    Qualitative HYPOTHESIS/UNKNOWN claims cannot carry a measured numeric value.
    """
    if not isinstance(claim, dict) or set(claim) - CLAIM_FIELDS:
        raise ValueError("Unsupported claim fields")
    for key in ("evidence_id", "metric", "unit"):
        if key in claim and not isinstance(claim[key], str):
            raise ValueError("Claim identifiers and units must be strings")
    value = claim.get("value")
    if isinstance(value, (dict, list)) or isinstance(value, float) and not isfinite(value):
        raise ValueError("Claim value must be a finite scalar")
    raw = claim.get("kind", "CALCULATED" if is_analysis else "MEASURED")
    if not isinstance(raw, str) or raw.upper() not in CLAIM_KINDS:
        raise ValueError("Unsupported claim kind")
    kind = raw.upper()
    if kind == "MEASURED" and is_analysis:
        raise ValueError("Measured claims require observation evidence")
    if kind in {"CALCULATED", "ASSOCIATION"} and not is_analysis:
        raise ValueError("Calculated and association claims require analysis evidence")
    if kind in {"HYPOTHESIS", "UNKNOWN"} and isinstance(claim.get("value"), (int, float, bool)):
        raise ValueError("Qualitative claims cannot verify numeric measurements")
    return kind


def _asserted_match(text, pattern, *, uncertain_allowed=False):
    for match in pattern.finditer(text):
        # Look within the same clause, before the assertion. A disclaimer after
        # an unsafe assertion cannot erase it. Negations and hypotheses before
        # the assertion preserve ordinary calibrated explanations.
        prefix = re.split(r"[.;!?]|\bbut\b|\bhowever\b", text[:match.start()], flags=re.I)[-1][-90:]
        if _NEGATION.search(prefix):
            continue
        if uncertain_allowed and _UNCERTAINTY.search(prefix):
            continue
        yield match


def inspect_claim_safety(text: str) -> list[str]:
    """Detect explicit causal certainty, diagnoses and unsafe symptom advice.

    Quoted user statements with an explicit reporting prefix are context, not
    the assistant's assertion. This small heuristic does not replace clinical
    review or evidence validation and deliberately reports only clear patterns.
    """
    if not isinstance(text, str):
        return ["INVALID_ANSWER_TEXT"]
    # Remove quoted material only when explicitly attributed to the user.
    text = re.sub(r"\b(?:you (?:said|reported|asked)|the user (?:said|reported|asked))\s*:\s*([\"“]).*?[\"”]",
                  "reported user context", text, flags=re.I | re.S)
    codes = []
    if any(_asserted_match(text, _CAUSAL, uncertain_allowed=True)):
        codes.append("UNSUPPORTED_CAUSAL_CERTAINTY")
    unsafe = any(_asserted_match(text, _DIAGNOSIS)) or any(_asserted_match(text, _MEDICATION))
    if _RED_FLAGS.search(text) and any(_asserted_match(text, _TRAIN_HARD)):
        unsafe = True
    if unsafe:
        codes.append("UNSAFE_MEDICAL_ADVICE")
    return codes
