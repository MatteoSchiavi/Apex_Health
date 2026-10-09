"""Independent transactional executor. It is never a model-facing tool."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from app.models.coach import UserContextDoc
from app.models.journal import JournalEntry
from app.models.lab import ChangeAudit, ChangeDraft, Observation
from app.models.training import PlannedSession, TrainingPlan
from app.models.activity import Discipline
from app.schemas.changes import CHANGE_ADAPTER, ProposeIn
from app.services.evidence import (
    EvidenceError,
    digest,
    eligible,
    scope_lock,
    snapshot_revision,
)


def draft_dict(row):
    return {
        "adaptation": {"original_session": row.before, "proposed_session": row.after,
            "objective_status": "deferred" if row.after.get("session_type") == "rest" else "uncertain",
            "data_gaps": ["No supporting observations attached"] if not row.evidence_ids else [],
            "evidence_ids": row.evidence_ids} if row.kind == "session_patch" else None,
        "id": row.id,
        "kind": row.kind,
        "status": row.status,
        "before": row.before,
        "after": row.after,
        "payload_hash": row.payload_hash,
        "snapshot_revision": row.snapshot_revision,
        "evidence_ids": row.evidence_ids,
        "reason": row.reason,
        "risk": row.risk,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat(),
        "receipt": row.receipt,
    }


async def _preview(session, user_id, change):
    data = change.model_dump(mode="json", exclude_none=True)
    if change.kind == "context_patch":
        row = await session.scalar(
            select(UserContextDoc)
            .where(
                UserContextDoc.user_id == user_id,
                UserContextDoc.doc_kind == change.doc_kind,
            )
            .with_for_update()
        )
        before = {
            "exists": row is not None,
            "doc_kind": change.doc_kind,
            "content": row.content if row else "",
        }
        content = before["content"]
        if change.operation == "append":
            if not change.text.strip():
                raise EvidenceError("INVALID_ARGUMENTS", "Append requires text")
            content = (content.rstrip() + "\n\n" + change.text.strip()).strip()
        else:
            if not change.fragment or content.count(change.fragment) != 1:
                raise EvidenceError(
                    "CONFLICT", "Fragment must match exactly once; refresh the context"
                )
            content = content.replace(
                change.fragment,
                change.text if change.operation == "replace_fragment" else "",
                1,
            )
        if len(content) > 8000:
            raise EvidenceError("INVALID_ARGUMENTS", "Context exceeds 8000 characters")
        return before, {"exists": True, "doc_kind": change.doc_kind, "content": content}
    if change.kind == "session_patch":
        row = await session.scalar(
            select(PlannedSession)
            .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(
                TrainingPlan.user_id == user_id,
                PlannedSession.id == change.target_id,
                TrainingPlan.status.in_(("confirmed", "active")),
            )
            .with_for_update(of=PlannedSession)
        )
        if row is None:
            raise EvidenceError("NOT_FOUND", "Session not found")
        plan = await session.get(TrainingPlan, row.training_plan_id)
        if row.protected or plan.protected:
            raise EvidenceError("PROTECTED_SESSION", "Protected workout: discuss alternatives or explicitly remove protection before proposing edits")
        before = {
            "target_id": row.id,
            "date": str(row.date),
            "target_duration_min": row.target_duration_min,
            "description": row.description,
            "session_type": row.session_type,
        }
        after = {
            **before,
            **{k: v for k, v in data.items() if k not in ("kind", "target_id")},
        }
        if after["target_duration_min"] == 0 and after["session_type"] != "rest":
            raise EvidenceError(
                "INVALID_ARGUMENTS", "A zero-duration session must be labelled rest"
            )
        from app.services.replanning import enforce_session_constraints

        await enforce_session_constraints(session, user_id, after)
        if before == after:
            raise EvidenceError("INVALID_ARGUMENTS", "The change has no effect")
        return before, after
    if change.kind == "journal_create":
        return {}, {
            "date": str(change.date),
            "notes": change.notes,
            "tags": change.tags,
        }
    if change.kind == "plan_create":
        from app.services.replanning import enforce_session_constraints

        totals, week_totals = {}, {}
        for item in change.sessions:
            monday = item.date - timedelta(days=item.date.weekday())
            week_totals[monday] = week_totals.get(monday, 0) + item.target_duration_min
            totals[item.date] = totals.get(item.date, 0) + item.target_duration_min
        for day, minutes in totals.items():
            day_session = next(
                item for item in change.sessions if item.date == day
            ).model_dump(mode="json")
            day_session["target_duration_min"] = minutes
            monday = day - timedelta(days=day.weekday())
            await enforce_session_constraints(session, user_id, day_session,
                additional_week_minutes=week_totals[monday] - minutes)
        for item in change.sessions:
            await enforce_session_constraints(
                session, user_id, item.model_dump(mode="json")
            )
            if (
                not change.week_start
                <= item.date
                <= change.week_start + timedelta(days=6)
            ):
                raise EvidenceError(
                    "INVALID_ARGUMENTS", "Sessions must lie within the proposed week"
                )
            if not await session.scalar(
                select(Discipline.id).where(Discipline.name == item.discipline)
            ):
                raise EvidenceError("INVALID_ARGUMENTS", "Unknown discipline")
        return {}, data
    raise EvidenceError("INVALID_ARGUMENTS", "Unknown change")


async def propose(session, user_id, payload: ProposeIn, *, now=None):
    now = now or datetime.now(UTC)
    await scope_lock(session, user_id, "changes")
    before, after = await _preview(session, user_id, payload.change)
    for handle in payload.evidence_ids:
        try:
            prefix, ident, revision = handle.split(":")
            ident, revision = int(ident), int(revision)
        except (ValueError, AttributeError):
            raise EvidenceError(
                "INVALID_ARGUMENTS", "Invalid evidence handle"
            ) from None
        row = await session.scalar(
            select(Observation).where(
                Observation.user_id == user_id,
                Observation.id == ident,
                Observation.revision == revision,
                Observation.current.is_(True),
            )
        )
        if (
            prefix != "observation"
            or row is None
            or not eligible(row.origin, row.metadata_json)
        ):
            raise EvidenceError("POLICY_DENIED", "Evidence unavailable")
    from app.services.evidence import excluded_observations

    excluded = await excluded_observations(session, user_id)
    if any(int(h.split(":")[1]) in excluded for h in payload.evidence_ids):
        raise EvidenceError(
            "POLICY_DENIED", "Evidence was excluded by an athlete annotation"
        )
    revision = await snapshot_revision(session, user_id)
    normalized = payload.change.model_dump(mode="json", exclude_none=True)
    envelope = {
        "user_id": user_id,
        "change": normalized,
        "before": before,
        "after": after,
        "snapshot_revision": revision,
        "evidence_ids": payload.evidence_ids,
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "reason": payload.reason,
    }
    row = ChangeDraft(
        user_id=user_id,
        kind=payload.change.kind,
        status="draft",
        payload=normalized,
        before=before,
        after=after,
        payload_hash=digest(envelope),
        snapshot_revision=revision,
        evidence_ids=payload.evidence_ids,
        reason=payload.reason,
        expires_at=now + timedelta(hours=24),
        created_at=now,
        risk="local_reversible",
    )
    session.add(row)
    await session.flush()
    from app.services.alpha_events import record_event
    record_event(session, user_id, "change_proposed", {"draft_id": row.id})
    session.add(
        ChangeAudit(
            user_id=user_id,
            draft_id=row.id,
            action="drafted",
            payload={"payload_hash": row.payload_hash},
        )
    )
    return draft_dict(row)


async def owned_draft(session, user_id, ident):
    row = await session.scalar(
        select(ChangeDraft)
        .where(ChangeDraft.id == ident, ChangeDraft.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise EvidenceError("NOT_FOUND", "Draft not found")
    return row


async def apply(session, user_id, ident, payload_hash, *, now=None):
    now = now or datetime.now(UTC)
    await scope_lock(session, user_id, "changes")
    row = await owned_draft(session, user_id, ident)
    envelope = {
        "user_id": user_id,
        "change": row.payload,
        "before": row.before,
        "after": row.after,
        "snapshot_revision": row.snapshot_revision,
        "evidence_ids": row.evidence_ids,
        "expires_at": row.expires_at.isoformat(),
        "reason": row.reason,
    }
    if row.payload_hash != payload_hash or digest(envelope) != row.payload_hash:
        raise EvidenceError("CONFLICT", "Approval does not match the displayed change")
    if row.status == "applied_locally":
        return draft_dict(row)  # immutable receipt = idempotency key (draft id + hash)
    if row.status != "draft" or row.expires_at <= now:
        raise EvidenceError("CONFLICT", "Draft was rejected, used or expired")
    if row.snapshot_revision != await snapshot_revision(session, user_id):
        raise EvidenceError(
            "CONFLICT", "Data or constraints changed; request a fresh preview"
        )
    before, after = await _preview(
        session, user_id, CHANGE_ADAPTER.validate_python(row.payload)
    )
    if before != row.before or after != row.after:
        raise EvidenceError("CONFLICT", "Target changed; request a fresh preview")
    row.approved_at = now
    target = None
    if row.kind == "context_patch":
        doc = await session.scalar(
            select(UserContextDoc).where(
                UserContextDoc.user_id == user_id,
                UserContextDoc.doc_kind == row.after["doc_kind"],
            )
        )
        if doc is None:
            doc = UserContextDoc(
                user_id=user_id,
                doc_kind=row.after["doc_kind"],
                content=row.after["content"],
                updated_by="user_approved_ai",
            )
            session.add(doc)
        else:
            doc.content, doc.updated_by, doc.updated_at = (
                row.after["content"],
                "user_approved_ai",
                now,
            )
        await session.flush()
        target = doc.id
    elif row.kind == "session_patch":
        target = row.after["target_id"]
        item = await session.get(PlannedSession, target)
        from datetime import date

        for key, value in row.after.items():
            if key != "target_id":
                setattr(
                    item, key, date.fromisoformat(value) if key == "date" else value
                )
    elif row.kind == "journal_create":
        from datetime import date

        entry = JournalEntry(
            user_id=user_id,
            date=date.fromisoformat(row.after["date"]),
            free_text_notes=row.after["notes"],
            tags=row.after["tags"],
            source="web",
        )
        session.add(entry)
        await session.flush()
        target = entry.id
    elif row.kind == "plan_create":
        from datetime import date

        plan = TrainingPlan(
            user_id=user_id,
            created_by="ai",
            week_start=date.fromisoformat(row.after["week_start"]),
            status="confirmed",
        )
        session.add(plan)
        await session.flush()
        target = plan.id
        for item in row.after["sessions"]:
            session.add(
                PlannedSession(
                    training_plan_id=plan.id,
                    date=date.fromisoformat(item["date"]),
                    discipline_id=await session.scalar(
                        select(Discipline.id).where(
                            Discipline.name == item["discipline"]
                        )
                    ),
                    session_type=item["session_type"],
                    target_duration_min=item["target_duration_min"],
                    description=item["description"],
                )
            )
    row.status = "applied_locally"
    from app.services.alpha_events import record_event
    record_event(session, user_id, "change_accepted", {"draft_id": row.id})
    row.receipt = {
        "state": "applied_locally",
        "target_id": target,
        "applied_at": now.isoformat(),
        "payload_hash": row.payload_hash,
        "undo_available": True,
        "external_delivery": "not_requested",
    }
    session.add(
        ChangeAudit(
            user_id=user_id,
            draft_id=row.id,
            action="applied_locally",
            payload=row.receipt,
        )
    )
    await session.flush()
    return draft_dict(row)


async def reject(session, user_id, ident):
    await scope_lock(session, user_id, "changes")
    row = await owned_draft(session, user_id, ident)
    if row.status == "rejected":
        return draft_dict(row)
    if row.status != "draft":
        raise EvidenceError("CONFLICT", "This draft has already been applied")
    row.status = "rejected"
    from app.services.alpha_events import record_event
    record_event(session, user_id, "change_rejected", {"draft_id": row.id})
    session.add(
        ChangeAudit(user_id=user_id, draft_id=row.id, action="rejected", payload={})
    )
    return draft_dict(row)


async def undo(session, user_id, ident):
    await scope_lock(session, user_id, "changes")
    row = await owned_draft(session, user_id, ident)
    if row.status == "undone":
        return draft_dict(row)
    if row.status != "applied_locally":
        raise EvidenceError("CONFLICT", "Only applied local changes can be undone")
    target = row.receipt["target_id"]
    if row.kind == "context_patch":
        doc = await session.scalar(
            select(UserContextDoc)
            .where(UserContextDoc.id == target, UserContextDoc.user_id == user_id)
            .with_for_update()
        )
        if doc is None or doc.content != row.after["content"]:
            raise EvidenceError(
                "CONFLICT", "Context changed after execution; undo would overwrite it"
            )
        if row.before["exists"]:
            doc.content, doc.updated_by, doc.updated_at = (
                row.before["content"],
                "user_undo",
                datetime.now(UTC),
            )
        else:
            await session.delete(doc)
    elif row.kind == "session_patch":
        change = CHANGE_ADAPTER.validate_python(row.payload)
        current, _ = await _preview_for_undo(session, user_id, change)
        if current != row.after:
            raise EvidenceError("CONFLICT", "Session changed after execution")
        item = await session.get(PlannedSession, target)
        from datetime import date

        for key, value in row.before.items():
            if key != "target_id":
                setattr(
                    item, key, date.fromisoformat(value) if key == "date" else value
                )
    elif row.kind == "journal_create":
        entry = await session.scalar(
            select(JournalEntry)
            .where(JournalEntry.id == target, JournalEntry.user_id == user_id)
            .with_for_update()
        )
        if (
            entry is None
            or entry.free_text_notes != row.after["notes"]
            or str(entry.date) != row.after["date"]
            or (entry.tags or []) != row.after["tags"]
        ):
            raise EvidenceError("CONFLICT", "Journal entry changed after execution")
        await session.delete(entry)
    else:
        # Plan undo is safe only before execution/edits; check exact session content.
        plan = await session.scalar(
            select(TrainingPlan)
            .where(TrainingPlan.id == target, TrainingPlan.user_id == user_id)
            .with_for_update()
        )
        if plan is None or plan.status != "confirmed":
            raise EvidenceError("CONFLICT", "Plan is no longer in its approved state")
        items = (
            await session.scalars(
                select(PlannedSession)
                .where(PlannedSession.training_plan_id == target)
                .order_by(PlannedSession.id)
            )
        ).all()
        for item, spec in zip(items, row.after["sessions"]):
            discipline = await session.scalar(
                select(Discipline.name).where(Discipline.id == item.discipline_id)
            )
            current = {
                "date": str(item.date),
                "discipline": discipline,
                "session_type": item.session_type,
                "target_duration_min": item.target_duration_min,
                "description": item.description or "",
            }
            if current != spec or item.technogym_program_id is not None:
                raise EvidenceError(
                    "CONFLICT", "Plan changed or was externally delivered"
                )
        if len(items) != len(row.after["sessions"]):
            raise EvidenceError("CONFLICT", "Plan sessions changed")
        for item in items:
            await session.delete(item)
        await session.delete(plan)
    row.status = "undone"
    row.receipt = {
        **row.receipt,
        "state": "undone",
        "undo_available": False,
        "undone_at": datetime.now(UTC).isoformat(),
    }
    session.add(
        ChangeAudit(
            user_id=user_id, draft_id=row.id, action="undone", payload=row.receipt
        )
    )
    return draft_dict(row)


async def _preview_for_undo(session, user_id, change):
    # Reading target state must not reject a no-op patch during undo.
    item = await session.scalar(
        select(PlannedSession)
        .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
        .where(TrainingPlan.user_id == user_id, PlannedSession.id == change.target_id)
        .with_for_update(of=PlannedSession)
    )
    if item is None:
        raise EvidenceError("NOT_FOUND", "Session not found")
    return {
        "target_id": item.id,
        "date": str(item.date),
        "target_duration_min": item.target_duration_min,
        "description": item.description,
        "session_type": item.session_type,
    }, None
