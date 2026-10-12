"""Hermetic Coach regressions: synthetic responses, no database or network I/O."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.agent import loop
from app.core.llm import LLMResponse, parse_completion
from app.models.athlete import AiConsent
from app.services import ai_access
from app.services.evidence import EvidenceError
from evals.harness import MemoryStore
from evals.scenarios import NOW, Scenario


# Keep these unit/runtime tests independent of the repository's destructive
# PostgreSQL/Redis autouse fixtures, including when run in the full suite.
@pytest.fixture(scope="session")
def migrated_database():
    yield


@pytest.fixture(scope="session")
def owner_account():
    yield


@pytest.fixture(autouse=True)
def clean_redis():
    yield


EVIDENCE = [{"id": "observation:1:1", "metric": "hrv_overnight_rmssd",
             "value": 50.5, "unit": "ms"}]
CLAIM = {"evidence_id": "observation:1:1", "metric": "hrv_overnight_rmssd",
         "value": 50.5, "unit": "ms"}


def answer(text, claims=()):
    return json.dumps({"answer": text, "claims": list(claims), "limitations": []}, ensure_ascii=False)


@pytest.mark.parametrize("text", [
    "Hello! How can I help?", "Ciao! Come posso aiutarti?",
    "Alternate recovery and training according to how you feel.",
    "Alterna recupero e allenamento in base a come ti senti.",
    "Your saved focus is running and strength.",
    "Il tuo obiettivo salvato è corsa e forza.",
])
@pytest.mark.parametrize("structured", [False, True])
def test_qualitative_dialogue_needs_no_artificial_measurements(text, structured):
    content = answer(text) if structured else text
    reply, receipt = loop.validate_answer(content, [{"kind": "user_assertion", "focus": "running,strength"}])
    assert reply == text
    assert receipt["status"] == ("structured" if structured else "narrative_only")
    assert receipt["verified_claims"] == []


@pytest.mark.parametrize("envelope", ["{}", "```json\n{}\n```", "```\n{}\n```", " \n```JSON\r\n{}\r\n```\n "])
@pytest.mark.parametrize("text", ["HRV is 50.5 ms.", "La tua HRV è 50,5 ms."])
def test_real_provider_content_envelopes_preserve_exact_claims(envelope, text):
    response = parse_completion({"choices": [{"message": {"role": "assistant",
        "content": envelope.format(answer(text, [CLAIM])), "reasoning_content": "private thinking"}}],
        "model": "fixture-provider", "usage": {"prompt_tokens": 120, "completion_tokens": 60}}, "fixture")
    reply, receipt = loop.validate_answer(response.content, EVIDENCE)
    assert reply == text
    assert receipt["verified_claims"][0]["value"] == 50.5
    assert "private thinking" not in json.dumps(receipt)


def test_fenced_greeting_renders_answer_instead_of_json():
    reply, receipt = loop.validate_answer("```json\n" + answer("Ciao!") + "\n```", [])
    assert reply == "Ciao!" and receipt["status"] == "structured"


@pytest.mark.parametrize("content,code", [
    (None, "EMPTY_ANSWER"), ("", "EMPTY_ANSWER"),
    ('{"answer":"Ciao!", "claims":', "MALFORMED_JSON"),
    ('```json\n{"answer":"Ciao!"}\n', "MALFORMED_JSON"),
    ("Before\n```json\n" + answer("Ciao!") + "\n```", "MALFORMED_JSON"),
    ("```json\n" + answer("Ciao!") + "\n```\nAfter", "MALFORMED_JSON"),
    ("```json\n" + answer("Ciao!") + "\n```\n```json\n" + answer("Ciao!") + "\n```", "MALFORMED_JSON"),
    ("```python\n" + answer("Ciao!") + "\n```", "MALFORMED_JSON"),
    ('{"answer": [], "claims": []}', "INVALID_ANSWER_SHAPE"),
    ('{"answer": "Hello", "claims": {}}', "INVALID_ANSWER_SHAPE"),
    ("Prefix " + answer("HRV is 50.5 ms.", [CLAIM]), "UNCITED_NUMERIC_TEXT"),
])
def test_malformed_or_embedded_json_never_mints_verified_values(content, code):
    reply, receipt = loop.validate_answer(content, EVIDENCE, locale="it")
    assert receipt["error_code"] == code and receipt["verified_claims"] == []
    assert "50" not in reply and "Non sono riuscito" in reply


@pytest.mark.parametrize("text,claims,code", [
    ("HRV is 50,5 ms.", [], "UNCITED_NUMERIC_TEXT"),
    ("HRV is 50,6 ms.", [CLAIM], "UNCITED_NUMERIC_TEXT"),
    ("HRV is 50,5 bpm.", [CLAIM], "METRIC_BINDING_MISMATCH"),
    ("Peso è 50,5 kg.", [CLAIM], "METRIC_BINDING_MISMATCH"),
    ("Recorded value available.", [{**CLAIM, "value": 50.6}], "CLAIM_EVIDENCE_MISMATCH"),
    ("Recorded value available.", [{**CLAIM, "unit": "bpm"}], "CLAIM_EVIDENCE_MISMATCH"),
    ("Recorded value available.", [{**CLAIM, "value": True}], "CLAIM_EVIDENCE_MISMATCH"),
    ("Recorded value available.", [{**CLAIM, "evidence_id": "observation:999:1"}], "EVIDENCE_NOT_ISSUED"),
    ("Recorded value available.", [{**CLAIM, "kind": "CALCULATED"}], "UNSUPPORTED_CLAIM_KIND"),
    ("Recorded value available.", [None], "INVALID_CLAIM_SHAPE"),
])
def test_localized_numeric_and_claim_errors_still_fail_closed(text, claims, code):
    reply, receipt = loop.validate_answer(answer(text, claims), EVIDENCE)
    assert receipt["error_code"] == code and receipt["verified_claims"] == []
    assert "50" not in reply and "one metric" in reply


@pytest.mark.parametrize("text,code", [
    ("Poor sleep caused your HRV decline.", "UNSUPPORTED_CAUSAL_CERTAINTY"),
    ("Hai sicuramente una malattia.", "UNSAFE_MEDICAL_ADVICE"),
])
def test_unsafe_conclusions_stay_blocked_and_localized(text, code):
    reply, receipt = loop.validate_answer(answer(text), [], locale="it")
    assert receipt["error_code"] == code and receipt["verified_claims"] == []
    assert "rivolgiti a un medico" in reply


def test_rejection_logging_uses_only_allowlisted_reason_codes(caplog):
    with caplog.at_level("INFO", logger=loop.__name__):
        loop._log_answer_rejection({"error_code": "EVIDENCE_NOT_ISSUED", "answer": "PRIVATE_HEALTH"})
        loop._log_answer_rejection({"error_code": "TOKEN=SECRET"})
    assert len(caplog.records) == 1
    assert caplog.records[0].error_code == "EVIDENCE_NOT_ISSUED"
    assert "PRIVATE_HEALTH" not in caplog.text and "TOKEN=SECRET" not in caplog.text


@pytest.fixture
def runtime(monkeypatch):
    """Use real consent/budget guards with the existing strict memory SQL adapter."""
    store = MemoryStore(Scenario("boundary", "Help with training", (), (), {"answer": "", "claims": []}))
    settings = SimpleNamespace(ai_processing_enabled=True, ai_daily_token_limit=160000, daily_token_budget_usd=1)

    async def spend(*args):
        return Decimal(0)

    monkeypatch.setattr(loop, "get_settings", lambda: settings)
    monkeypatch.setattr(loop, "user_day_spend", spend)
    monkeypatch.setattr(ai_access, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_access, "user_day_spend", spend)
    monkeypatch.setattr(ai_access, "provider_identity", lambda: "synthetic-fixture")
    return store, settings


class ScriptedProvider:
    def __init__(self, responses, *, after_first=None):
        self.responses = list(responses)
        self.calls = []
        self.after_first = after_first

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.after_first and len(self.calls) == 1:
            self.after_first()
        content = self.responses.pop(0)
        if isinstance(content, Exception):
            raise content
        return LLMResponse(content=content, model="fixture-provider", tokens_in=120, tokens_out=60)


async def run_turn(store, provider, *, locale="en"):
    return await loop.run_agent_loop(store.sessionmaker, provider, user_id=1, session_id=1,
        text="Help with training", system="Synthetic data only", tier="cheap", today=NOW.date(),
        initial_evidence=EVIDENCE, locale=locale)


async def test_single_correction_can_recover_a_valid_answer(runtime):
    store, _ = runtime
    provider = ScriptedProvider([answer("HRV is 99 ms."), "```json\n" + answer("Recorded HRV is available.", [CLAIM]) + "\n```"])
    result = await run_turn(store, provider)
    assert result.grounding["status"] == "structured"
    assert result.grounding["correction_attempted"] is True
    assert len(provider.calls) == 2 and provider.calls[1]["tools"] is None
    assert result.grounding["verified_claims"][0]["value"] == 50.5


@pytest.mark.parametrize("locale,phrase", [("en", "one metric"), ("it", "una sola metrica")])
async def test_failed_correction_returns_safe_reduced_scope_help(runtime, locale, phrase):
    store, _ = runtime
    provider = ScriptedProvider([answer("HRV is 99 ms."), answer("HRV is 999 ms.")])
    result = await run_turn(store, provider, locale=locale)
    assert len(provider.calls) == 2 and result.grounding["correction_attempted"] is True
    assert result.grounding["verified_claims"] == [] and phrase in result.reply
    assert "99" not in result.reply and "999" not in result.reply


async def test_withdrawn_consent_prevents_provider_invocation(runtime):
    store, _ = runtime
    store.rows[AiConsent][0].active = False
    provider = ScriptedProvider([answer("Hello")])
    with pytest.raises(EvidenceError, match="Active AI consent"):
        await run_turn(store, provider)
    assert provider.calls == []


@pytest.mark.parametrize("failure,code,phrase", [
    ("consent", "POLICY_DENIED", "consent"),
    ("budget", "BUDGET_EXCEEDED", "budget"),
    ("timeout", "TIMEOUT", "time"),
])
async def test_midturn_policy_budget_and_timeout_are_distinct(runtime, failure, code, phrase):
    store, settings = runtime

    def change_access():
        if failure == "consent":
            store.rows[AiConsent][0].active = False
        elif failure == "budget":
            settings.ai_daily_token_limit = 1

    provider = ScriptedProvider([TimeoutError() if failure == "timeout" else answer("HRV is 99 ms.")],
                                after_first=change_access)
    result = await run_turn(store, provider)
    assert result.grounding["error_code"] == code and result.grounding["verified_claims"] == []
    assert len(provider.calls) == 1 and phrase in result.reply
    if failure != "timeout":
        assert "within the available time" not in result.reply
