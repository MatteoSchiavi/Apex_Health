"""Regression checks for calibrated user-facing health/training language.

These checks reject a small set of affirmative medical promises while
preserving ordinary discussion of injury/illness signals, uncertainty and
explicit negation.
"""

import json
import re
from datetime import date
from pathlib import Path

from app.agent.claims import inspect_claim_safety
from app.services.gym_advisor import adjust
from app.services.safety_interlock import exertion_veto

ROOT = Path(__file__).resolve().parents[2]
_CLAIM_VERBS = re.compile(
    r"\b(?:will|can)\s+(?:diagnose|prevent|predict|cure|treat|guarantee)\b|"
    r"\b(?:può|potrà)\s+(?:diagnosticare|prevenire|prevedere|curare|trattare|garantire)\b",
    re.IGNORECASE,
)
_DIRECT_DIAGNOSIS = re.compile(
    r"\b(?:you have|you are suffering from|hai sicuramente|soffri di)\s+"
    r"(?:an?\s+)?(?:illness|injury|disease|infection|malattia|infortunio|infezione)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:not|never|cannot|can't|does not|doesn't|do not|don't|non|mai|"
    r"non è|non può)\b",
    re.IGNORECASE,
)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _affirmative_match(pattern: re.Pattern, value: str) -> bool:
    for match in pattern.finditer(value):
        prefix = re.split(
            r"[.;!?]|\bbut\b|\bhowever\b|\bma\b|\bperò\b",
            value[: match.start()],
            flags=re.IGNORECASE,
        )[-1][-90:]
        if not _NEGATION.search(prefix):
            return True
    return False


def test_english_and_italian_user_copy_stays_calibrated() -> None:
    catalogs = {
        language: json.loads(
            (ROOT / "frontend" / "src" / "locales" / f"{language}.json").read_text()
        )
        for language in ("en", "it")
    }
    flattened = {language: list(_strings(catalog)) for language, catalog in catalogs.items()}

    # The shared answer-boundary checker and the small affirmative phrase set
    # catch overclaims while keeping medical vocabulary available for context.
    for language, values in flattened.items():
        for value in values:
            assert inspect_claim_safety(value) == [], (language, value)
            assert not _affirmative_match(_CLAIM_VERBS, value), (language, value)
            assert not _affirmative_match(_DIRECT_DIAGNOSIS, value), (language, value)

    english = "\n".join(flattened["en"]).lower()
    italian = "\n".join(flattened["it"]).lower()
    assert "does not diagnose injury risk" in english
    assert "non diagnostica il rischio di infortunio" in italian
    assert "illness" in english and "injury" in english
    assert "malattia" in italian and "infortunio" in italian


def test_negated_and_uncertain_scientific_discussion_remains_allowed() -> None:
    safe_statements = (
        "This score does not predict injury.",
        "A stress signal may be associated with illness, but it is not a diagnosis.",
        "Questo valore non diagnostica una malattia.",
        "Una variazione può associarsi a un infortunio, ma non lo dimostra.",
    )
    for statement in safe_statements:
        assert inspect_claim_safety(statement) == []
        assert not _affirmative_match(_CLAIM_VERBS, statement)
        assert not _affirmative_match(_DIRECT_DIAGNOSIS, statement)


def test_interlock_and_gym_messages_describe_signals_and_reported_feedback() -> None:
    veto = exertion_veto(systemic_stress=82, load_spike=78)
    assert veto.vetoed
    assert veto.intensity_ceiling == "rest"
    assert any("signal elevated" in reason.lower() for reason in veto.reasons)

    exercises, notes = adjust(
        exercises=[
            {
                "exercise_id": "squat",
                "name": "Squat",
                "muscle_group": "legs",
                "movement_pattern": "squat",
                "impact_level": "high",
                "sets": 4,
                "reps_min": 6,
                "reps_max": 10,
            }
        ],
        events=[],
        feedback=[
            {"soreness": ["knee"], "injury_flag": True, "rpe": 8}
        ],
        today=date(2026, 10, 7),
        safety={"systemic_stress": 82, "load_spike": 78},
    )
    emitted = " ".join([*veto.reasons, *notes]).lower()
    assert exercises == []
    assert "injury flag" in emitted
    assert "signal elevated" in emitted
    assert inspect_claim_safety(emitted) == []
    assert not _affirmative_match(_CLAIM_VERBS, emitted)
    assert not _affirmative_match(_DIRECT_DIAGNOSIS, emitted)
