"""Coach routing regressions without database, Redis or provider requests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import entrypoint, routing
from app.agent.loop import AgentLoopResult


# Override the repository's destructive integration fixtures for this module.
@pytest.fixture(scope="session")
def migrated_database():
    yield


@pytest.fixture(scope="session")
def owner_account():
    yield


@pytest.fixture(autouse=True)
def clean_redis():
    yield


@pytest.mark.parametrize("text", [
    "Fammi un'analisi dei miei allenamenti.",
    "Analisi del recupero e del sonno di questa settimana",
    "Analisi: posso seguire il piano di corsa oggi?",
    "Analisi della frequenza cardiaca durante la corsa",
    "Can you analyze my training and recovery?",
    "Compare training labs and performance experiments.",
    "My workout title is Doctoral intervals.",
    "Il mio allenamento si chiama paramedico.",
    "How was my HRV yesterday?",
])
def test_training_analysis_is_not_a_deterministic_medical_trigger(text):
    assert not routing.is_medical_intent(text)


@pytest.mark.parametrize("text", [
    "What do my blood work results mean?",
    "Can you explain these blood tests?",
    "BLOOD-TEST results and training",
    "Review my laboratory results",
    "My ferritin is high and hemoglobin is low",
    "My haemoglobin changed",
    "Symptoms after exercise",
    "My prescribed medications",
    "Discuss this with my doctor",
    "My injury diagnosis",
    "What do thyroid, cholesterol and vitamin D mean?",
    "Esame del sangue",
    "Esami del sangue",
    "Esami ematici e allenamento",
    "ANALISI DEL SANGUE",
    "Puoi spiegare l'analisi clinica?",
    "Analisi cliniche",
    "Analisi ematiche",
    "Analisi mediche",
    "Analisi di laboratorio",
    "Ferritina, emoglobina e colesterolo",
    "Tiroide e vitamina D",
    "Ho questi sintomi dopo la corsa",
    "Farmaci e medicinali",
    "Cosa devo chiedere alla mia medica?",
    "Parlerò con i miei medici",
    "Referto medicale",
])
def test_explicit_medical_questions_keep_the_protected_route(text):
    assert routing.is_medical_intent(text)


@pytest.mark.parametrize("cap", ["full", "cheap_only"])
async def test_training_analysis_respects_account_cap_without_medical_shortcut(monkeypatch, cap):
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(ai_access_tier=cap)
    classify = AsyncMock(return_value="strategic")
    monkeypatch.setattr("app.services.ai_access.require_access", AsyncMock())
    monkeypatch.setattr(routing, "_classify", classify)
    decision = await routing.resolve_tier(session, 1, "Analisi dei miei allenamenti", object())
    assert decision.tier == ("powerful" if cap == "full" else "cheap")
    assert decision.classification == ("strategic" if cap == "full" else None)
    assert classify.await_count == (1 if cap == "full" else 0)


@pytest.mark.parametrize("cap,enabled,tier", [
    ("full", False, "powerful"), ("full", True, "medical"),
    ("cheap_only", True, "cheap"),
])
async def test_clinical_phrase_keeps_medical_classification_and_cap(monkeypatch, cap, enabled, tier):
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(ai_access_tier=cap)
    classify = AsyncMock(side_effect=AssertionError("Clinical phrase should bypass classification"))
    monkeypatch.setattr("app.services.ai_access.require_access", AsyncMock())
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(medical_tier_enabled=enabled))
    monkeypatch.setattr(routing, "_classify", classify)
    decision = await routing.resolve_tier(session, 1, "Puoi spiegare le analisi del sangue?", object())
    assert decision.tier == tier and decision.classification == "medical"
    classify.assert_not_awaited()


@pytest.mark.parametrize("locale", ["en", "it"])
@pytest.mark.parametrize("classification", ["medical", "strategic"])
async def test_turn_preserves_classifier_medical_disclosure_on_powerful_fallback(monkeypatch, locale, classification):
    """Exercise the turn boundary, including the persisted assistant message."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.scalar.return_value = SimpleNamespace(id=12)
    session.get.return_value = SimpleNamespace(ai_access_tier="full")
    saved = []

    def add(row):
        row.id = len(saved) + 1
        saved.append(row)

    session.add = add
    now = datetime(2026, 10, 17, tzinfo=UTC)
    snapshot = {"_local_today": now.date(), "profile": {"locale": locale},
                "snapshot_revision": "test", "coverage": {}}
    monkeypatch.setattr("app.services.ai_access.require_access", AsyncMock())
    monkeypatch.setattr(entrypoint, "scope_lock", AsyncMock())
    monkeypatch.setattr(entrypoint, "_history_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(entrypoint, "_build_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(entrypoint, "resolve_tier", AsyncMock(return_value=
                        routing.RoutingDecision("powerful", classification, "full")))
    loop = AsyncMock(return_value=AgentLoopResult("Recorded context is available.", "powerful", "fixture",
                                                grounding={"status": "narrative_only"}))
    monkeypatch.setattr(entrypoint, "run_agent_loop", loop)
    turn = await entrypoint.run_agent_turn(lambda: session, object(), 1,
                                          "Help me understand this change", now=now, session_id=12)
    prefix = entrypoint.MEDICAL_DISCLAIMER_IT if locale == "it" else entrypoint.MEDICAL_DISCLAIMER_EN
    expected = (prefix if classification == "medical" else "") + "Recorded context is available."
    assert turn.reply == saved[-1].content == expected
    assert loop.await_args.kwargs["tier"] == "powerful"
