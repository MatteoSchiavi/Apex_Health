"""Authenticated performance-lab surfaces and independent approval boundary."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import Activity
from app.models.lab import (
    AnalysisResult,
    AthleteEntry,
    ChangeAudit,
    ChangeDraft,
    DecisionRecord,
    LabJob,
    LabNotification,
    Observation,
)
from app.models.user import User
from app.schemas.changes import ApproveIn, ProposeIn
from app.schemas.lab import EntryIn, NotificationAction, ObservationIn, OutcomeIn
from app.agent.tools import AnalyticsIn, PreviewIn, RepairIn
from app.services import analytics, changes, evidence
from app.services.decisions import daily_decision
from app.services.alpha_events import record_event
from app.services.jobs import job_dict, request_job
from app.services.notifications import notification_dict, refresh_notifications

router = APIRouter(prefix="/lab", tags=["performance-lab"])


@router.get("/coverage")
async def get_coverage(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    return await evidence.coverage(session, user)


@router.get("/decision")
async def get_decision(
    day: date | None = None,
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    today = datetime.now(ZoneInfo(user.timezone)).date()
    if day is not None and day != today:
        if day > today:
            raise HTTPException(422, "Decision date cannot be in the future")
        row = await session.scalar(
            select(DecisionRecord).where(DecisionRecord.user_id == user.id, DecisionRecord.date == day)
            .order_by(DecisionRecord.id.desc()).limit(1)
        )
        return {**row.output, "id": row.id, "outcome": row.outcome} if row else None
    result = await daily_decision(session, user, for_ai=True, persist=True)
    await session.commit()
    return result


@router.post("/decision/{ident}/outcome")
async def decision_outcome(
    ident: int,
    payload: OutcomeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(DecisionRecord)
        .where(DecisionRecord.id == ident, DecisionRecord.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Decision not found")
    if payload.activity_id and not await session.scalar(
        select(Activity.id).where(
            Activity.id == payload.activity_id, Activity.user_id == user.id
        )
    ):
        raise HTTPException(404, "Activity not found")
    row.outcome = {
        **payload.model_dump(mode="json"),
        "recorded_at": datetime.now(UTC).isoformat(),
        "interpretation": "Execution/adherence is not proof of physiological benefit.",
    }
    await session.commit()
    return {"id": row.id, "outcome": row.outcome}


@router.get("/decisions")
async def list_decisions(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(DecisionRecord)
            .where(DecisionRecord.user_id == user.id)
            .distinct(DecisionRecord.date)
            .order_by(DecisionRecord.date.desc(), DecisionRecord.id.desc())
            .limit(90)
        )
    ).all()
    return [
        {"id": r.id, "date": str(r.date), "output": r.output, "outcome": r.outcome}
        for r in rows
    ]


@router.post("/analytics")
async def analyze(
    payload: AnalyticsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    result = await analytics.run_recipe(
        session,
        user,
        data.pop("recipe"),
        metric=data["metric"],
        start=data["start_date"],
        end=data["end_date"],
        origin=data["origin"],
        activity_id=data["activity_id"],
        experiment_id=data["experiment_id"],
        for_ai=True,
    )
    await session.commit()
    return result


@router.get("/analyses")
async def analyses(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(AnalysisResult)
            .where(AnalysisResult.user_id == user.id)
            .order_by(AnalysisResult.id.desc())
            .limit(50)
        )
    ).all()
    return [
        {
            "id": r.id,
            "recipe": r.recipe,
            "formula_version": r.formula_version,
            "data": r.result,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/constraints")
async def constraints(
    day: date | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return await analytics.constraints(
        session, user, day or datetime.now(ZoneInfo(user.timezone)).date()
    )


@router.post("/preview")
async def preview(
    payload: PreviewIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    before, after = await changes._preview(session, user.id, payload.change)
    return {
        "before": before,
        "after": after,
        "constraints": await analytics.constraints(
            session,
            user,
            getattr(payload.change, "date", None)
            or datetime.now(ZoneInfo(user.timezone)).date(),
        ),
        "projected_load": None,
        "limitations": "Exact plan diff; physiological consequences have not been calibrated.",
    }


@router.post("/changes", status_code=201)
async def propose(
    payload: ProposeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await changes.propose(session, user.id, payload)
    await session.commit()
    return result


@router.get("/changes")
async def drafts(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(ChangeDraft)
            .where(ChangeDraft.user_id == user.id)
            .order_by(ChangeDraft.id.desc())
            .limit(50)
        )
    ).all()
    return [changes.draft_dict(r) for r in rows]


@router.post("/changes/{ident}/approve")
async def approve(
    ident: int,
    payload: ApproveIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await changes.apply(session, user.id, ident, payload.payload_hash)
    await session.commit()
    return result


@router.post("/changes/{ident}/reject")
async def reject(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await changes.reject(session, user.id, ident)
    await session.commit()
    return result


@router.post("/changes/{ident}/undo")
async def undo(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await changes.undo(session, user.id, ident)
    await session.commit()
    return result


@router.get("/audit")
async def audit(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(ChangeAudit)
            .where(ChangeAudit.user_id == user.id)
            .order_by(ChangeAudit.id.desc())
            .limit(200)
        )
    ).all()
    return [
        {
            "id": r.id,
            "draft_id": r.draft_id,
            "action": r.action,
            "payload": r.payload,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def entry_dict(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "date": str(row.date),
        "payload": row.payload,
        "revision": row.revision,
    }


@router.get("/entries")
async def entries(
    kind: str | None = None,
    days: int = Query(90, ge=1, le=366),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    day = datetime.now(ZoneInfo(user.timezone)).date()
    query = select(AthleteEntry).where(AthleteEntry.user_id == user.id)
    if kind not in {
        "privacy_preferences",
        "notification_preferences",
        "metric_settings",
    }:
        query = query.where(AthleteEntry.date >= day - timedelta(days=days - 1))
    if kind:
        query = query.where(AthleteEntry.kind == kind)
    rows = (
        await session.scalars(query.order_by(AthleteEntry.id.desc()).limit(500))
    ).all()
    return [entry_dict(r) for r in rows]


@router.post("/entries", status_code=201)
async def create_entry(
    payload: EntryIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    await evidence.scope_lock(session, user.id, "changes")
    item = payload.entry
    if item.kind == "observation_annotation" and not await session.scalar(
        select(Observation.id).where(
            Observation.user_id == user.id, Observation.id == item.observation_id
        )
    ):
        raise HTTPException(404, "Observation not found")
    if item.kind == "experiment":
        if item.end_date < item.date or (item.end_date - item.date).days > 300:
            raise evidence.EvidenceError(
                "INVALID_ARGUMENTS",
                "Experiment must cover a closed period of at most 301 days",
            )
    if (
        item.kind == "device_change"
        and not set(item.metrics) <= evidence.METRICS.keys()
    ):
        raise evidence.EvidenceError(
            "INVALID_ARGUMENTS", "Choose recognized affected metrics"
        )
    if item.kind == "experiment_checkin":
        experiment = await session.scalar(
            select(AthleteEntry).where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.id == item.experiment_id,
                AthleteEntry.kind == "experiment",
            )
        )
        if experiment is None:
            raise HTTPException(404, "Experiment not found")
        if (
            not experiment.date
            <= item.date
            <= date.fromisoformat(experiment.payload["end_date"])
        ):
            raise evidence.EvidenceError(
                "INVALID_ARGUMENTS", "Check-in is outside the experiment period"
            )
    data = item.model_dump(mode="json")
    data.pop("kind")
    data.pop("date")
    row = AthleteEntry(user_id=user.id, kind=item.kind, date=item.date, payload=data)
    session.add(row)
    await session.flush()
    session.add(
        ChangeAudit(
            user_id=user.id,
            action="user_assertion_created",
            payload={"entry_id": row.id, "kind": row.kind},
        )
    )
    if row.kind == "experiment":
        record_event(session, user.id, "experiment_created", {"experiment_id": row.id})
    await session.commit()
    return entry_dict(row)


@router.delete("/entries/{ident}", status_code=204)
async def remove_entry(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(AthleteEntry).where(
            AthleteEntry.id == ident, AthleteEntry.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(404, "Entry not found")
    if row.kind == "experiment":
        logs = (
            await session.scalars(
                select(AthleteEntry).where(
                    AthleteEntry.user_id == user.id,
                    AthleteEntry.kind == "experiment_checkin",
                )
            )
        ).all()
        for log in logs:
            if log.payload.get("experiment_id") == ident:
                await session.delete(log)
    await session.delete(row)
    session.add(
        ChangeAudit(
            user_id=user.id,
            action="user_assertion_deleted",
            payload={"entry_id": ident},
        )
    )
    await session.commit()


@router.post("/observations", status_code=201)
async def manual_observation(
    payload: ObservationIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if payload.metric not in evidence.METRICS or payload.measured_at.tzinfo is None:
        raise evidence.EvidenceError(
            "INVALID_ARGUMENTS",
            "Choose a supported metric and timezone-aware timestamp",
        )
    bounds = {
        "hrv_overnight_rmssd": (1, 500),
        "resting_hr": (20, 220),
        "sleep_duration": (0, 24),
        "sleep_score": (0, 100),
        "spo2": (50, 100),
        "stress": (0, 100),
        "body_battery": (0, 100),
        "training_readiness": (0, 100),
        "respiration": (1, 60),
        "steps": (0, 200000),
        "weight": (20, 500),
        "body_fat": (1, 70),
    }
    if (
        payload.metric == "training_status"
        or not bounds.get(payload.metric, (0, 100000))[0]
        <= payload.value
        <= bounds.get(payload.metric, (0, 100000))[1]
    ):
        raise evidence.EvidenceError(
            "INVALID_ARGUMENTS",
            "Measurement is outside the supported plausibility bounds",
        )
    if payload.measured_at > datetime.now(UTC) + timedelta(minutes=5):
        raise evidence.EvidenceError(
            "INVALID_ARGUMENTS", "A measurement cannot be in the future"
        )
    row = await evidence.record_observation(
        session,
        user_id=user.id,
        metric=payload.metric,
        value=payload.value,
        unit=evidence.METRICS[payload.metric],
        origin="manual",
        source_record_id=f"manual:{payload.metric}:{payload.measured_at.isoformat()}",
        measured_at=payload.measured_at,
        fetched_at=datetime.now(UTC),
        timezone=user.timezone,
        acquisition="user_assertion",
        metadata={"notes": payload.notes, "reading_context": "manual"},
    )
    await session.commit()
    return evidence.observation_dict(row, datetime.now(UTC))


@router.get("/observations")
async def observations(
    metric: str,
    start: date,
    end: date,
    origin: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rows = await evidence.query_observations(
        session, user.id, metric, start, end, origin=origin
    )
    return [evidence.observation_dict(r, datetime.now(UTC)) for r in rows]


@router.get("/evidence/{ident}")
async def provenance(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(Observation).where(
            Observation.id == ident, Observation.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(404, "Evidence not found")
    annotations = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind == "observation_annotation",
                AthleteEntry.payload["observation_id"].as_integer() == ident,
            )
            .order_by(AthleteEntry.id)
        )
    ).all()
    return {
        **evidence.observation_dict(row, datetime.now(UTC)),
        "raw_ingest_id": row.raw_ingest_id,
        "current": row.current,
        "annotations": [entry_dict(a) for a in annotations],
    }


@router.post("/jobs", status_code=202)
async def enqueue(
    payload: RepairIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await request_job(
        session, user, payload.kind, payload.start_date, payload.end_date
    )
    await session.commit()
    return result


@router.get("/jobs")
async def jobs(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(LabJob)
            .where(LabJob.user_id == user.id)
            .order_by(LabJob.id.desc())
            .limit(50)
        )
    ).all()
    return [job_dict(r) for r in rows]


@router.post("/jobs/{ident}/cancel")
async def cancel_job(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(LabJob)
        .where(LabJob.id == ident, LabJob.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Job not found")
    row.cancel_requested = True
    if row.state == "queued":
        row.state = "cancelled"
    await session.commit()
    return job_dict(row)


@router.get("/notifications")
async def notifications(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    metadata = await refresh_notifications(session, user)
    rows = (
        await session.scalars(
            select(LabNotification)
            .where(LabNotification.user_id == user.id)
            .order_by(LabNotification.id.desc())
            .limit(100)
        )
    ).all()
    await session.commit()
    return {**metadata, "items": [notification_dict(r, user.locale) for r in rows]}


@router.post("/notifications/{ident}")
async def update_notification(
    ident: int,
    payload: NotificationAction,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(LabNotification)
        .where(LabNotification.id == ident, LabNotification.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Notification not found")
    row.state = payload.state
    row.updated_at = datetime.now(UTC)
    row.snoozed_until = (
        datetime.now(UTC) + timedelta(hours=payload.snooze_hours)
        if payload.state == "snoozed"
        else None
    )
    await session.commit()
    return notification_dict(row, user.locale)


@router.get("/capabilities")
async def capabilities(user: User = Depends(get_current_user)):
    return {
        "canonical_runtime": "FastAPI/PostgreSQL + bundled Vite SPA",
        "harness": "apex-harness-v4",
        "garmin": {
            "active_adapter": "unofficial_replaceable",
            "official_program": "approval_required",
            "training_api_delivery": "not_configured",
            "file_import": "original_FIT",
        },
        "ai_restricted_origins": ["strava"],
        "notifications": {"channels": ["in_app"], "external_consent": "not_requested"},
    }


@router.post("/jobs/{ident}/retry")
async def retry_job(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    await evidence.scope_lock(session, user.id, "maintenance_jobs")
    row = await session.scalar(
        select(LabJob)
        .where(LabJob.id == ident, LabJob.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Job not found")
    if row.state not in ("failed", "auth_required", "cancelled"):
        raise HTTPException(409, "Job is already pending or complete")
    if await session.scalar(
        select(LabJob.id).where(
            LabJob.user_id == user.id, LabJob.state.in_(("queued", "running"))
        )
    ):
        raise HTTPException(409, "A maintenance job is already active")
    row.state = "queued"
    row.cancel_requested = False
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return job_dict(row)


@router.get("/reports")
async def reports(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    from app.models.ai import AiReport

    rows = (
        await session.scalars(
            select(AiReport)
            .where(AiReport.user_id == user.id)
            .order_by(AiReport.generated_at.desc())
            .limit(50)
        )
    ).all()
    return [
        {
            "id": r.id,
            "type": r.report_type,
            "start": str(r.period_start),
            "end": str(r.period_end),
            "content": r.content_md,
            "source_policy": "ai_eligible_v1"
            if "policy:ai_eligible_v1" in (r.source_feature_ids or [])
            else "legacy_unverified",
        }
        for r in rows
    ]


from app.schemas.changes import Strict
from pydantic import Field


class ReplanIn(Strict):
    target_id: int | None = Field(default=None, gt=0)


@router.post("/replan")
async def replan(
    payload: ReplanIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    from app.services.replanning import minimal_replan

    await evidence.scope_lock(session, user.id, "changes")
    result = await minimal_replan(session, user, payload.target_id)
    await session.commit()
    return result


@router.post("/analysis-jobs", status_code=202)
async def analysis_job(
    payload: AnalyticsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    from app.services.jobs import request_analysis

    result = await request_analysis(
        session, user, payload.model_dump(mode="json", exclude_none=True)
    )
    await session.commit()
    return result
