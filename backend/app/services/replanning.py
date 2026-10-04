"""Minimal deterministic alternative: preserve the session focus and edit one session."""

from sqlalchemy import select
from app.models.lab import AthleteEntry
from app.services.decisions import daily_decision
from app.services.evidence import EvidenceError
from app.services.changes import propose
from app.schemas.changes import ProposeIn


async def minimal_replan(session, user, target_id=None):
    decision = await daily_decision(session, user, for_ai=True)
    candidates = decision["constraints"]["sessions"]
    target = (
        next((s for s in candidates if s["id"] == target_id), None)
        if target_id
        else next((s for s in candidates if s["date"] == decision["date"]), None)
    )
    if target is None:
        raise EvidenceError("NOT_FOUND", "Choose an owned upcoming planned session")
    action = decision["action"]
    old = target["duration_min"]
    if action in ("train_normally", "collect_more_data"):
        return {
            "state": "no_change",
            "decision": decision,
            "reason": "No supported session adjustment; preserve the existing plan.",
        }
    if old is None:
        raise EvidenceError(
            "INSUFFICIENT_DATA",
            "A recorded target duration is required to preview the change",
        )
    availability = decision["constraints"]["availability"]
    cap = (
        availability[-1]["minutes"]
        if availability and target["date"] == decision["date"]
        else old
    )
    change = {
        "kind": "session_patch",
        "target_id": target["id"],
        "target_duration_min": max(5, min(cap, round(old * 0.7))),
    }
    if action == "recover" and target["date"] == decision["date"]:
        change.update(
            target_duration_min=0,
            session_type="rest",
            description="Rest day; reassess symptoms and current evidence before returning to training.",
        )
    elif action == "swap_session":
        change.update(
            session_type="easy",
            description="Easy technical session; preserve freshness for the configured priority event.",
        )
    if change["target_duration_min"] == old and "session_type" not in change:
        return {"state": "no_change", "decision": decision}
    draft = await propose(
        session,
        user.id,
        ProposeIn.model_validate(
            {
                "change": change,
                "reason": " ".join(decision["reasons"]),
                "evidence_ids": [o["id"] for o in decision["evidence"]],
            }
        ),
    )
    return {
        "state": "draft",
        "draft": draft,
        "decision": decision,
        "limitations": "Exact duration/type diff only; no calibrated physiological prediction.",
    }


async def enforce_session_constraints(session, user_id, after):
    # Applies to both previews and execution. User approval cannot silently
    # substitute a model-written payload that violates declared availability.
    from datetime import date

    day = date.fromisoformat(after["date"])
    rows = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user_id,
                AthleteEntry.date == day,
                AthleteEntry.kind.in_(("availability", "daily_checkin")),
            )
            .order_by(AthleteEntry.id)
        )
    ).all()
    latest = {r.kind: r for r in rows}
    duration = after.get("target_duration_min")
    available = latest.get("availability")
    other_minutes = 0
    if available and duration is not None:
        from sqlalchemy import func
        from app.models.training import PlannedSession, TrainingPlan

        query = (
            select(func.coalesce(func.sum(PlannedSession.target_duration_min), 0))
            .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(
                TrainingPlan.user_id == user_id,
                TrainingPlan.status.in_(("confirmed", "active")),
                PlannedSession.date == day,
            )
        )
        if after.get("target_id"):
            query = query.where(PlannedSession.id != after["target_id"])
        other_minutes = await session.scalar(query)
    if (
        available
        and duration is not None
        and duration + other_minutes > available.payload["minutes"]
    ):
        raise EvidenceError(
            "CONFLICT",
            "Session exceeds declared availability; update the availability or preview a smaller session",
        )
    subjective = latest.get("daily_checkin")
    if (
        subjective
        and (subjective.payload.get("pain") or subjective.payload.get("felt_unwell"))
        and after["session_type"] != "rest"
    ):
        raise EvidenceError(
            "POLICY_DENIED",
            "A pain/illness check-in requires a rest alternative or an updated check-in before training changes",
        )
