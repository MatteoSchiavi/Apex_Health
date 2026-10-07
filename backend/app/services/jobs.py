"""Durable outbox for bounded maintenance jobs; workers revalidate account scope."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import func, select
from app.models.lab import LabJob
from app.models.integration import Integration
from app.services.evidence import EvidenceError, scope_lock
from app.services.alpha_events import record_event


def job_dict(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "state": row.state,
        "parameters": row.parameters,
        "progress": row.progress,
        "cancel_requested": row.cancel_requested,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def request_job(session, user, kind, start, end):
    if (
        kind not in ("repair", "reindex")
        or start > end
        or (end - start).days > (29 if kind == "repair" else 365)
    ):
        raise EvidenceError(
            "INVALID_ARGUMENTS",
            "Repairs cover at most 30 days; reindex covers at most 366 days",
        )
    now = datetime.now(UTC)
    await scope_lock(session, user.id, "maintenance_jobs")
    current = await session.scalar(
        select(LabJob)
        .where(LabJob.user_id == user.id, LabJob.state.in_(("queued", "running")))
        .order_by(LabJob.id.desc())
        .limit(1)
    )
    params = {"start": str(start), "end": str(end), "provider": "garmin"}
    if current:
        if current.kind == kind and current.parameters == params:
            return job_dict(current)
        raise EvidenceError("CONFLICT", "A maintenance job is already active")
    count = await session.scalar(
        select(func.count())
        .select_from(LabJob)
        .where(
            LabJob.user_id == user.id, LabJob.created_at > now - timedelta(minutes=10)
        )
    )
    if count >= 2:
        raise EvidenceError(
            "RATE_LIMITED", "At most two maintenance requests per ten minutes"
        )
    if kind == "repair" and not await session.scalar(
        select(Integration.id).where(
            Integration.user_id == user.id,
            Integration.provider == "garmin",
            Integration.status == "active",
        )
    ):
        raise EvidenceError(
            "AUTH_REQUIRED", "Reconnect Garmin before requesting a repair"
        )
    row = LabJob(
        user_id=user.id,
        kind=kind,
        state="queued",
        parameters=params,
        progress={"completed": 0, "cursor": 0},
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    # No remote call inside this transaction. The dispatcher delivers the
    # committed outbox record and reconciles duplicates via the worker lock.
    return job_dict(row)


async def request_analysis(session, user, parameters):
    from app.agent.tools import AnalyticsIn

    data = AnalyticsIn.model_validate(parameters).model_dump(
        mode="json", exclude_none=True
    )
    # Background is orchestration metadata, not a recursive analysis request.
    data.pop("background", None)
    from datetime import date

    if data.get("start_date") and data.get("end_date"):
        start, end = (
            date.fromisoformat(data["start_date"]),
            date.fromisoformat(data["end_date"]),
        )
        if start > end or (end - start).days > 365:
            raise EvidenceError(
                "INVALID_ARGUMENTS", "Analysis range is capped at 366 days"
            )
    now = datetime.now(UTC)
    await scope_lock(session, user.id, "maintenance_jobs")
    existing = await session.scalar(
        select(LabJob).where(
            LabJob.user_id == user.id, LabJob.state.in_(("queued", "running"))
        )
    )
    if existing:
        if existing.kind == "analysis" and existing.parameters == data:
            return job_dict(existing)
        raise EvidenceError(
            "CONFLICT", "An analysis or maintenance job is already active"
        )
    row = LabJob(
        user_id=user.id,
        kind="analysis",
        state="queued",
        parameters=data,
        progress={"completed": 0, "total": 1},
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    record_event(session, user.id, "analysis_started", {"job_id": row.id})
    return job_dict(row)
