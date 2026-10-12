"""Real API journeys: source review, selective facts, undated templates, exact approval."""
import json
from datetime import UTC, date, datetime, timedelta
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from app.core.encryption import decrypt_bytes
from app.core.llm import LLMResponse
from app.models.athlete_training import AthleteImportDraft, WeeklyTrainingTemplate, PlanDocumentDraft
from app.models.lab import ChangeAudit, LabDocument
from app.models.training import TrainingPlan, PlannedSession
from app.models.user import User
from app.schemas.athlete_import import ImportProposal, TemplatePreviewIn
from app.services.athlete_import import instantiate_weekly
from app.services.evidence import snapshot_revision
from tests.conftest import csrf_headers
from tests.test_athlete_training import authenticate
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def reset_login(db_session):
    await db_session.execute(text("UPDATE auth_credentials SET failed_login_count=0,locked_until=NULL WHERE user_id=1"))
    await db_session.commit()


SOURCE = "I have running experience. Weekly Monday running, Friday strength. Seasonal goal: a race."


async def source(client, text=SOURCE, purpose=True, filename="mixed.md"):
    upload = await client.post("/lab/documents", params={"for_athlete_import": purpose},
        headers=csrf_headers(client), files={"file": (filename, text.encode(), "text/plain")})
    assert upload.status_code == 201, upload.text
    doc = upload.json()
    confirmed = await client.post(f"/lab/documents/{doc['id']}/confirm", headers=csrf_headers(client),
        json={"content_hash": doc["content_hash"], "reviewed_text": text})
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


async def imported(client, doc):
    response = await client.post("/lab/athlete-imports", headers=csrf_headers(client),
        json={"document_id": doc["id"], "expected_document_revision": doc["revision"]})
    assert response.status_code == 201, response.text
    return response.json()


async def review(client, draft, proposal):
    response = await client.put(f"/lab/athlete-imports/{draft['id']}", headers=csrf_headers(client),
        json={"payload_hash": draft["payload_hash"], "proposal": proposal})
    assert response.status_code == 200, response.text
    return response.json()


def mixed_proposal():
    return {"profile": {"training_focus": ["running", "gym"], "context": {
        "main_goal": "Run a spring race", "focuses": {"running": {"weekly_frequency": 3}},
        "athlete_notes": "A proposal deliberately not selected"}},
        "weekly": {"title": "My weekly routine", "rows": [
            {"id": "easy-mon", "day": 0, "discipline": "running", "duration_min": 40},
            {"id": "strength-fri", "day": 4, "discipline": "strength"}]}}


async def test_mixed_manual_review_selective_profile_receipt_and_immutable_versions(client, db_session):
    await authenticate(client)
    initial = await client.put("/athlete/profile", headers=csrf_headers(client), json={"expected_revision": 0,
        "training_focus": ["running", "gym"], "context": {"athlete_notes": "Keep my notes", "focuses": {
            "running": {"level": "experienced", "constraints": "Keep weekends free"}}}})
    assert initial.status_code == 200
    doc = await source(client)
    draft = await imported(client, doc)
    assert draft["proposal"]["profile"] == {"training_focus": None, "context": {}}
    assert draft["proposal"]["weekly"] is None and {"profile", "weekly", "goals"} <= set(draft["category_hints"])
    assert (await imported(client, doc))["id"] == draft["id"]
    accepted = await review(client, draft, mixed_proposal())
    assert accepted["version"] == 2 and accepted["id"] != draft["id"]
    assert (await imported(client, doc))["id"] == accepted["id"]  # Re-upload/restart preserves edited review.
    stored = await db_session.get(AthleteImportDraft, accepted["id"])
    assert b"spring race" not in stored.proposal_ciphertext and SOURCE.encode() not in stored.source_text_ciphertext
    assert decrypt_bytes(stored.source_text_ciphertext).decode() == SOURCE
    stale = await client.put(f"/lab/athlete-imports/{draft['id']}", headers=csrf_headers(client),
        json={"payload_hash": draft["payload_hash"], "proposal": mixed_proposal()})
    assert stale.status_code == 409
    payload = {"payload_hash": accepted["payload_hash"], "expected_profile_revision": 1,
        "fields": ["training_focus", "context.main_goal", "context.focuses"]}
    result = await client.post(f"/lab/athlete-imports/{accepted['id']}/profile-confirm", headers=csrf_headers(client), json=payload)
    assert result.status_code == 200, result.text
    profile = result.json()["profile"]
    assert profile["context"]["athlete_notes"] == "Keep my notes"
    assert profile["context"]["focuses"]["running"]["constraints"] == "Keep weekends free"
    assert profile["context"]["focuses"]["running"]["weekly_frequency"] == 3
    assert profile["revision"] == 2
    retry = await client.post(f"/lab/athlete-imports/{accepted['id']}/profile-confirm", headers=csrf_headers(client), json=payload)
    assert retry.status_code == 200 and retry.json()["profile"]["revision"] == 2
    assert not await db_session.scalar(select(TrainingPlan.id))
    assert await db_session.scalar(select(ChangeAudit.id).where(ChangeAudit.action == "athlete_import_profile_confirmed"))
    assert (await client.get(f"/lab/athlete-imports/{draft['id']}")).json()["proposal"]["weekly"] is None


async def test_template_stays_undated_preview_then_exact_confirmation_and_protection(client, db_session):
    await authenticate(client)
    draft = await review(client, await imported(client, await source(client)), mixed_proposal())
    saved = await client.post(f"/lab/athlete-imports/{draft['id']}/template-confirm", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"]})
    assert saved.status_code == 200, saved.text
    template = saved.json()["template"]
    assert template["structure"]["rows"][0]["id"] == "easy-mon" and "date" not in template["structure"]["rows"][0]
    assert not await db_session.scalar(select(TrainingPlan.id))
    assert not await db_session.scalar(select(PlanDocumentDraft.id))
    again = await client.post(f"/lab/athlete-imports/{draft['id']}/template-confirm", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"]})
    assert again.json()["template"]["id"] == template["id"]
    start = datetime.now(UTC).date() + timedelta(days=7)
    start += timedelta(days=(0-start.weekday()) % 7)
    params = {"expected_revision": 1, "starts_on": str(start), "ends_on": str(start+timedelta(days=6))}
    preview = await client.post(f"/athlete/templates/{template['id']}/preview", headers=csrf_headers(client), json=params)
    assert preview.status_code == 200, preview.text
    plan_draft = preview.json()
    assert plan_draft["document_id"] is None and plan_draft["template_id"] == template["id"]
    assert [r["date"] for r in plan_draft["structure"]["sessions"]] == [str(start), str(start+timedelta(days=4))]
    assert plan_draft["structure"]["sessions"][1]["duration_min"] is None
    assert not await db_session.scalar(select(TrainingPlan.id))
    bad = await client.post(f"/lab/plan-drafts/{plan_draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": "0"*64})
    assert bad.status_code == 409
    confirmed = await client.post(f"/lab/plan-drafts/{plan_draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": plan_draft["payload_hash"]})
    assert confirmed.status_code == 200, confirmed.text
    plan = await db_session.get(TrainingPlan, confirmed.json()["plan_id"])
    assert plan.source_template_id == template["id"] and plan.source_document_id is None
    plan.protected = True
    await db_session.commit()
    params["ends_on"] = str(start+timedelta(days=13))
    newer = (await client.post(f"/athlete/templates/{template['id']}/preview", headers=csrf_headers(client), json=params)).json()
    assert newer["version"] == 2
    stale = await client.post(f"/lab/plan-drafts/{plan_draft['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": plan_draft["payload_hash"]})
    assert stale.status_code == 409
    protected = await client.post(f"/lab/plan-drafts/{newer['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": newer["payload_hash"]})
    assert protected.status_code == 409
    await db_session.refresh(plan)
    assert plan.status == "active"
    plan.protected = False
    await db_session.commit()
    active = await client.post(f"/lab/plan-drafts/{newer['id']}/confirm", headers=csrf_headers(client), json={"payload_hash": newer["payload_hash"]})
    assert active.status_code == 200, active.text
    await db_session.refresh(plan)
    assert plan.status == "completed"
    assert len((await db_session.scalars(select(PlannedSession).where(PlannedSession.training_plan_id == plan.id))).all()) == 2


async def test_source_revision_conflict_retains_exact_original_review_and_profile_revision(client, db_session):
    await authenticate(client)
    doc = await source(client)
    draft = await review(client, await imported(client, doc), mixed_proposal())
    confirmation = await client.post(f"/lab/athlete-imports/{draft['id']}/profile-confirm", headers=csrf_headers(client),
        json={"payload_hash": draft["payload_hash"], "expected_profile_revision": 7, "fields": ["context.main_goal"]})
    assert confirmation.status_code == 409
    revised = await client.post(f"/lab/documents/{doc['id']}/confirm", headers=csrf_headers(client),
        json={"content_hash": doc["content_hash"], "reviewed_text": "Different source information"})
    assert revised.status_code == 200
    assert (await client.get(f"/lab/athlete-imports/{draft['id']}")).json()["source_text"] == SOURCE
    for action in ["template-confirm", "dated-plan"]:
        response = await client.post(f"/lab/athlete-imports/{draft['id']}/{action}", headers=csrf_headers(client), json={"payload_hash": draft["payload_hash"]})
        assert response.status_code == 409
    assert not await db_session.scalar(select(WeeklyTrainingTemplate.id))


async def test_import_only_source_is_not_coach_context_dedupe_purpose_or_evidence_revision(client, db_session):
    await authenticate(client)
    user = await db_session.get(User, 1)
    before = await snapshot_revision(db_session, user.id)
    doc = await source(client)
    after = await snapshot_revision(db_session, user.id)
    assert doc["coach_eligible"] is False and before == after
    # Same bytes with distinct intent must be separate encrypted records.
    general = await source(client, purpose=False)
    assert general["id"] != doc["id"] and general["coach_eligible"] is True
    duplicate = await source(client)
    assert duplicate["id"] == doc["id"]
    from app.agent.tools import ToolContext, _search
    result = await _search(ToolContext(session=db_session, user_id=user.id, today=date.today()), query="running", limit=10)
    rows = result["data"]
    document_ids = {row.get("document_id") for row in rows if row.get("kind") == "reviewed_document"}
    assert doc["id"] not in document_ids and general["id"] in document_ids


async def test_pdf_honest_paste_fallback_and_large_text_not_silently_truncated(client):
    await authenticate(client)
    pdf = await client.post("/lab/documents?for_athlete_import=true", headers=csrf_headers(client),
        files={"file": ("scan.pdf", b"%PDF-1.7\nfixture", "application/pdf")})
    assert pdf.status_code == 201
    assert pdf.json()["excerpt"] is None and pdf.json()["extraction_state"] == "manual_paste_required"
    denied = await client.post("/lab/athlete-imports", headers=csrf_headers(client), json={
        "document_id": pdf.json()["id"], "expected_document_revision": 1})
    assert denied.status_code == 409
    oversized = await client.post("/lab/documents", headers=csrf_headers(client), files={"file": ("long.txt", b"a"*16001, "text/plain")})
    assert oversized.status_code == 422 and "No text was imported" in oversized.json()["detail"]


async def test_import_and_template_ownership_and_required_issues(client, db_session):
    await authenticate(client)
    draft = await imported(client, await source(client))
    proposal = mixed_proposal()
    proposal["issues"] = [{"field": "profile.context.main_goal", "question": "Which event?", "required": True}]
    draft = await review(client, draft, proposal)
    blocked = await client.post(f"/lab/athlete-imports/{draft['id']}/profile-confirm", headers=csrf_headers(client), json={
        "payload_hash": draft["payload_hash"], "expected_profile_revision": 0, "fields": ["context.main_goal"]})
    assert blocked.status_code == 422
    template = (await client.post(f"/lab/athlete-imports/{draft['id']}/template-confirm", headers=csrf_headers(client),
        json={"payload_hash": draft["payload_hash"]})).json()["template"]
    other = User(name="Private athlete", timezone="UTC")
    db_session.add(other)
    await db_session.flush()
    stored = await db_session.get(AthleteImportDraft, draft["id"])
    stored.user_id = other.id
    saved = await db_session.get(WeeklyTrainingTemplate, template["id"])
    saved.user_id = other.id
    await db_session.commit()
    assert (await client.get(f"/lab/athlete-imports/{draft['id']}")).status_code == 404
    assert (await client.post(f"/lab/athlete-imports/{draft['id']}/template-confirm", headers=csrf_headers(client),
        json={"payload_hash": draft["payload_hash"]})).status_code == 404
    assert (await client.post(f"/athlete/templates/{template['id']}/preview", headers=csrf_headers(client),
        json={"expected_revision": 1, "starts_on": "2026-10-12", "ends_on": "2026-10-18"})).status_code == 404


async def test_ai_import_consent_quotes_and_unknowns(client, db_session, monkeypatch):
    await authenticate(client)
    doc = await source(client)
    await db_session.execute(text("DELETE FROM ai_consents WHERE user_id=1"))
    await db_session.commit()
    calls = []
    class Provider:
        async def complete(self, **kwargs):
            calls.append(kwargs)
            return LLMResponse(content=json.dumps({"profile": {"context": {"main_goal": "Run a race"}},
                "weekly": {"rows": [{"id": "mon", "day": 0, "discipline": "running"}]},
                "sources": [{"field": "profile.context.main_goal", "quote": "a nonexistent quote", "certainty": "explicit"}]}),
                model="fixture", tokens_in=10, tokens_out=10)
    monkeypatch.setattr("app.api.athlete_import.build_llm_client", lambda: Provider())
    request = {"document_id": doc["id"], "expected_document_revision": doc["revision"], "use_ai": True}
    denied = await client.post("/lab/athlete-imports", headers=csrf_headers(client), json=request)
    assert denied.status_code == 403 and not calls
    from tests.helpers.ai import authorize_ai
    await authorize_ai(db_session)
    result = await client.post("/lab/athlete-imports", headers=csrf_headers(client), json=request)
    assert result.status_code == 201, result.text
    proposal = result.json()["proposal"]
    assert proposal["weekly"]["rows"][0]["duration_min"] is None
    assert proposal["sources"][0]["certainty"] == "uncertain" and proposal["issues"][0]["required"] is True
    assert "UNTRUSTED_DOCUMENT" in calls[0]["messages"][0]["content"]
    assert not await db_session.scalar(select(TrainingPlan.id))


@pytest.mark.parametrize("blocked", ["ftp", "hr_zones", "power_zones"])
def test_ai_profile_cannot_propose_thresholds(blocked):
    with pytest.raises(ValueError):
        ImportProposal.model_validate({"profile": {"context": {blocked: None}}})


def test_template_explicit_date_range_and_no_silent_workout_truncation():
    with pytest.raises(ValueError):
        TemplatePreviewIn.model_validate({"expected_revision": 1, "starts_on": "2026-01-01", "ends_on": "2027-01-03"})
    weekly = {"rows": [{"id": str(i), "day": 0, "discipline": "running"} for i in range(100)]}
    from fastapi import HTTPException
    with pytest.raises(HTTPException, match="500 workouts"):
        instantiate_weekly(weekly, date(2026, 1, 1), date(2026, 12, 31))


def text_pdf(text="Running weekly Monday"):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(("BT /F1 12 Tf 20 20 Td (" + text + ") Tj ET").encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


async def test_real_pdf_text_extracts_without_fabrication_and_limit_is_explicit(client):
    await authenticate(client)
    pdf = await client.post("/lab/documents?for_athlete_import=true", headers=csrf_headers(client),
        files={"file": ("weekly.pdf", text_pdf(), "application/pdf")})
    assert pdf.status_code == 201, pdf.text
    assert pdf.json()["extraction_state"] == "text_ready"
    assert "Running weekly Monday" in pdf.json()["excerpt"]
    long_pdf = await client.post("/lab/documents?for_athlete_import=true", headers=csrf_headers(client),
        files={"file": ("too-long.pdf", text_pdf("a"*16001), "application/pdf")})
    assert long_pdf.status_code == 422
    assert "No text was imported" in long_pdf.json()["detail"]
