"""Training plan + supplement proposal reads/writes (§8.2, §8.3, §8.5).

Write discipline: the agent's propose_* tools only ever create DRAFT rows —
a plan starts at status='draft' (§6.4 CHECK), a supplement proposal at
active=false — and Telegram inline buttons (§8.5) drive confirm/reject.
Only a 'confirmed' plan may later sync to Technogym (§11).
"""

from datetime import date, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical import SupplementProtocol
from app.models.training import PlannedSession, TrainingPlan


async def get_training_plan(
    session: AsyncSession, user_id: int, status: str | None = None
) -> dict | None:
    """§8.3 get_training_plan: with a status, the latest plan in that state;
    without, the current plan — 'active' first, else 'confirmed', else the
    newest draft. Planned sessions ride along."""
    if status is not None:
        row = (
            await session.scalars(
                select(TrainingPlan)
                .where(TrainingPlan.user_id == user_id, TrainingPlan.status == status)
                .order_by(TrainingPlan.week_start.desc(), TrainingPlan.id.desc())
                .limit(1)
            )
        ).first()
    else:
        row = None
        for candidate_status in ("active", "confirmed", "draft"):
            row = (
                await session.scalars(
                    select(TrainingPlan)
                    .where(
                        TrainingPlan.user_id == user_id,
                        TrainingPlan.status == candidate_status,
                    )
                    .order_by(TrainingPlan.week_start.desc(), TrainingPlan.id.desc())
                    .limit(1)
                )
            ).first()
            if row is not None:
                break
    if row is None:
        return None
    sessions = (
        await session.scalars(
            select(PlannedSession)
            .where(PlannedSession.training_plan_id == row.id)
            .order_by(PlannedSession.date, PlannedSession.id)
        )
    ).all()
    return {
        "plan_id": row.id,
        "status": row.status,
        "created_by": row.created_by,
        "week_start": row.week_start.isoformat(),
        "sessions": [
            {
                "id": s.id,
                "date": s.date.isoformat(),
                "discipline_id": s.discipline_id,
                "session_type": s.session_type,
                "target_duration_min": s.target_duration_min,
                "target_load": float(s.target_load) if s.target_load is not None else None,
                "description": s.description,
            }
            for s in sessions
        ],
    }


def normalize_week_start(day: date) -> date:
    """Plans are weekly: snap any date to its Monday so 'week_start' stays
    honest regardless of what the model sends."""
    return day - timedelta(days=day.weekday())


async def get_plan_sessions_for_day(
    session: AsyncSession, user_id: int, day: date
) -> list[dict]:
    """Sessions scheduled for `day` under the account's CONFIRMED/ACTIVE plans
    (§11b fallback: '/plan today' in Telegram is how the plan reaches the user
    while prescription-push awaits the real Technogym access tier, §24).
    Latest plan wins per plan id ordering; sessions ordered by id."""
    rows = (
        await session.execute(
            select(TrainingPlan, PlannedSession)
            .join(PlannedSession, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(
                TrainingPlan.user_id == user_id,
                TrainingPlan.status.in_(("confirmed", "active")),
                PlannedSession.date == day,
            )
            .order_by(TrainingPlan.week_start.desc(), PlannedSession.id)
        )
    ).all()
    return [
        {
            "plan_id": plan.id,
            "plan_status": plan.status,
            "session_id": ps.id,
            "discipline_id": ps.discipline_id,
            "session_type": ps.session_type,
            "target_duration_min": ps.target_duration_min,
            "target_load": float(ps.target_load) if ps.target_load is not None else None,
            "description": ps.description,
        }
        for plan, ps in rows
    ]


async def create_plan_draft(
    session: AsyncSession,
    user_id: int,
    week_start: date,
    sessions: list[dict],
    *,
    created_by: str = "ai",
    source_ai_report_id: int | None = None,
    discipline_ids: dict[int, int] | None = None,
) -> dict:
    """§8.5 draft path for propose_training_plan: plan + planned_sessions in
    one transaction step; caller commits. discipline_ids maps per-session
    index → resolved discipline id (slugs resolved by the tool handler)."""
    plan = TrainingPlan(
        user_id=user_id,
        created_by=created_by,
        week_start=normalize_week_start(week_start),
        status="draft",
        source_ai_report_id=source_ai_report_id,
    )
    session.add(plan)
    await session.flush()
    for index, spec in enumerate(sessions):
        resolved = (discipline_ids or {}).get(index)
        session.add(
            PlannedSession(
                training_plan_id=plan.id,
                date=date.fromisoformat(spec["date"]) if isinstance(spec.get("date"), str) else spec["date"],
                discipline_id=resolved if resolved is not None else spec.get("discipline_id"),
                session_type=spec.get("session_type"),
                target_duration_min=spec.get("target_duration_min"),
                target_load=spec.get("target_load"),
                description=spec.get("description"),
            )
        )
    return {"plan_id": plan.id, "status": plan.status, "week_start": plan.week_start.isoformat()}


async def confirm_plan_draft(session: AsyncSession, user_id: int, plan_id: int) -> str:
    """✅ Confirm (Telegram inline button, §8.5): draft → confirmed. Scoped to
    the linked user — a foreign plan id is just 'not found'."""
    plan = await session.get(TrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        return "not_found"
    if plan.status != "draft":
        return "not_draft"
    plan.status = "confirmed"
    return "confirmed"


async def reject_plan_draft(session: AsyncSession, user_id: int, plan_id: int) -> str:
    """❌ Reject (§8.5): the draft has no 'rejected' status in §6.4's CHECK,
    so rejection deletes the draft and its sessions."""
    plan = await session.get(TrainingPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        return "not_found"
    if plan.status != "draft":
        return "not_draft"
    await session.execute(delete(PlannedSession).where(PlannedSession.training_plan_id == plan.id))
    await session.delete(plan)
    return "rejected"


async def create_supplement_draft(
    session: AsyncSession,
    user_id: int,
    supplement_name: str,
    dose: str | None,
    schedule_cron: str | None,
    reason: str | None,
) -> dict:
    """§8.5 draft path for propose_supplement_change: the proposal is an
    inactive protocol row — active=false IS the draft marker (§6.4 has no
    draft status on supplement_protocols)."""
    protocol = SupplementProtocol(
        user_id=user_id,
        supplement_name=supplement_name,
        dose=dose,
        schedule_cron=schedule_cron,
        active=False,
        reason=reason,
    )
    session.add(protocol)
    await session.flush()
    return {"protocol_id": protocol.id, "status": "draft", "supplement_name": supplement_name}


async def confirm_supplement_draft(session: AsyncSession, user_id: int, protocol_id: int) -> str:
    """✅ Confirm: activate the proposed protocol and end any same-name active
    protocol the day before (replacement semantics)."""
    protocol = await session.get(SupplementProtocol, protocol_id)
    if protocol is None or protocol.user_id != user_id:
        return "not_found"
    if protocol.active:
        return "not_draft"
    superseded = (
        await session.scalars(
            select(SupplementProtocol).where(
                SupplementProtocol.user_id == user_id,
                SupplementProtocol.supplement_name == protocol.supplement_name,
                SupplementProtocol.active.is_(True),
                SupplementProtocol.id != protocol.id,
            )
        )
    ).all()
    for old in superseded:
        old.active = False
        old.end_date = protocol.start_date or date.today() - timedelta(days=1)
    protocol.active = True
    if protocol.start_date is None:
        protocol.start_date = date.today()
    return "confirmed"


async def reject_supplement_draft(session: AsyncSession, user_id: int, protocol_id: int) -> str:
    protocol = await session.get(SupplementProtocol, protocol_id)
    if protocol is None or protocol.user_id != user_id:
        return "not_found"
    if protocol.active:
        return "not_draft"
    await session.delete(protocol)
    return "rejected"
