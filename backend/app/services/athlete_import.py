"""Encrypted review versions; source documents never become accepted context here."""
import json
import re
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func, select
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.models.athlete_training import AthleteImportDraft, PlanDocumentDraft
from app.schemas.athlete_import import ImportProposal, WeeklyProposal
from app.schemas.athlete_training import ReviewedPlan
from app.services.evidence import canonical, digest


def source_text(document):
    return decrypt_bytes(document.excerpt_ciphertext).decode() if document.excerpt_ciphertext else ""


def category_hints(text):
    # Classification only: these labels never populate athlete facts or dates.
    text = text.casefold()
    patterns = {
        "profile": r"\b(background|experience|athlete|profilo|esperienza|sono|bio)\b",
        "weekly": r"\b(weekly|monday|tuesday|wednesday|thursday|friday|saturday|sunday|settiman\w*|luned\w*|marted\w*|mercoled\w*|gioved\w*|venerd\w*|sabato|domenica)\b",
        "dated": r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b",
        "goals": r"\b(goal\w*|event\w*|race\w*|obiettiv\w*|gara|gare|season\w*|stagion\w*)\b",
    }
    return [key for key, pattern in patterns.items() if re.search(pattern, text)] or ["notes"]


def proposal_of(row):
    return ImportProposal.model_validate_json(decrypt_bytes(row.proposal_ciphertext))


def import_out(row, document):
    text = decrypt_bytes(row.source_text_ciphertext).decode()
    return {"id": row.id, "document_id": row.document_id,
        "document_revision": row.document_revision, "version": row.version,
        "proposal": proposal_of(row).model_dump(mode="json"), "payload_hash": row.payload_hash,
        "extraction_method": row.extraction_method, "receipts": row.receipts or {},
        "source_text": text, "category_hints": category_hints(text), "created_at": row.created_at}


def template_out(row):
    return {"id": row.id, "revision": row.revision, "source_document_id": row.source_document_id,
        "source_document_revision": row.source_document_revision, "import_draft_id": row.import_draft_id,
        "structure": json.loads(decrypt_bytes(row.structure_ciphertext)), "created_at": row.created_at}


async def latest_import(session, user_id, document_id):
    return await session.scalar(select(AthleteImportDraft).where(AthleteImportDraft.user_id == user_id,
        AthleteImportDraft.document_id == document_id).order_by(AthleteImportDraft.version.desc()).limit(1))


async def new_import(session, user_id, document, proposal, method, *, force=False):
    latest = await latest_import(session, user_id, document.id)
    data = proposal.model_dump(mode="json")
    content_hash = digest(["athlete_import", user_id, document.id, document.revision, data])
    if latest and latest.payload_hash == content_hash and not force:
        return latest
    row = AthleteImportDraft(user_id=user_id, document_id=document.id, document_revision=document.revision,
        version=latest.version + 1 if latest else 1, proposal_ciphertext=encrypt_bytes(canonical(data).encode()),
        source_text_ciphertext=encrypt_bytes(source_text(document).encode()),
        payload_hash=content_hash, extraction_method=method, receipts={})
    session.add(row)
    await session.flush()
    return row


async def checked_import(session, user_id, ident, payload_hash):
    from app.api.lab_assets import owned_document
    row = await session.scalar(select(AthleteImportDraft).where(AthleteImportDraft.user_id == user_id,
        AthleteImportDraft.id == ident).with_for_update())
    if row is None:
        raise HTTPException(404, "Import draft not found")
    document = await owned_document(session, user_id, row.document_id)
    latest = await latest_import(session, user_id, row.document_id)
    if (row.payload_hash != payload_hash or latest.id != row.id or document.status != "confirmed"
            or document.revision != row.document_revision):
        raise HTTPException(409, "Source or review changed; reload the current import before saving")
    return row, document


def verify_quotes(proposal, text):
    # Unsupported citations stay visibly uncertain, never become explicit facts.
    issues = list(proposal.issues)
    for source in proposal.sources:
        if source.quote not in text:
            source.certainty = "uncertain"
            if len(issues) < 100:
                issues.append({"field": source.field, "question": "The quoted source was not found. Verify or correct this proposed information.", "required": True})
    proposal.issues = ImportProposal.model_validate({**proposal.model_dump(mode="json"), "issues": issues}).issues
    return proposal


def instantiate_weekly(weekly, starts_on, ends_on):
    weekly = WeeklyProposal.model_validate(weekly)
    sessions = []
    day = starts_on
    while day <= ends_on:
        for row in weekly.rows:
            if row.day == day.weekday():
                sessions.append({**row.model_dump(mode="json", exclude={"id", "day"}), "date": day.isoformat()})
                if len(sessions) > 500:
                    raise HTTPException(422, "This range produces more than 500 workouts; choose a shorter date range")
        day += timedelta(days=1)
    if not sessions:
        raise HTTPException(422, "No template workouts fall within the selected dates")
    return ReviewedPlan.model_validate({"title": weekly.title, "starts_on": starts_on, "ends_on": ends_on,
        "weekly_structure": weekly.notes, "sessions": sessions})


async def new_plan_draft(session, user_id, structure, *, document=None, template=None):
    data = structure.model_dump(mode="json")
    if document is not None:
        predicate = PlanDocumentDraft.document_id == document.id
        source = ["document", document.id, document.revision]
        values = {"document_id": document.id, "document_revision": document.revision}
    else:
        predicate = PlanDocumentDraft.template_id == template.id
        source = ["template", template.id, template.revision]
        values = {"template_id": template.id, "template_revision": template.revision}
    latest = await session.scalar(select(PlanDocumentDraft).where(predicate, PlanDocumentDraft.user_id == user_id)
        .order_by(PlanDocumentDraft.version.desc()).limit(1))
    content_hash = digest([user_id, *source, data])
    if latest and latest.payload_hash == content_hash:
        return latest
    row = PlanDocumentDraft(user_id=user_id, **values, version=latest.version + 1 if latest else 1,
        structure_ciphertext=encrypt_bytes(canonical(data).encode()), payload_hash=content_hash,
        status="draft", extraction_method="reviewed_weekly_template" if template else "reviewed_athlete_import")
    session.add(row)
    await session.flush()
    return row
