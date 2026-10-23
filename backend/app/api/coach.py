"""Coach API: events calendar, AI context documents, gym day plans, the
in-gym session tracker, and session feedback (owner feature batch).

Every route is `get_current_user`-scoped; foreign ids answer 404 (the
isolation law used across the whole API, §22)."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.user import User
from app.queries.gym_detail import (
    NotPlanOwnerError,
    PlanNotFoundError,
    SetLogConflictError,
    log_set,
    next_up,
    plan_for_date,
    plan_revision,
    session_view,
)
from app.services.gym_advisor import (
    generate_day_plan,
    current_input_fingerprint,
    recent_feedback,
    upcoming_events,
)

router = APIRouter(tags=["coach"])

_DOC_KINDS = ("profile", "goals", "injuries", "equipment", "preferences", "season_plan")


def _tz(user: User) -> ZoneInfo:
    return ZoneInfo(user.timezone)


# ------------------------------------------------------------------ events


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str
    starts_at: datetime
    ends_at: datetime | None = None
    priority: int = Field(default=2, ge=1, le=3)
    taper_days: int = Field(default=3, ge=0, le=21)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_event(self):
        if self.kind not in (
            "race",
            "run",
            "ride",
            "ski",
            "enduro",
            "sailing",
            "competition",
            "trip",
            "training_camp",
            "gym",
            "other",
        ):
            raise ValueError("Unknown event kind")
        if self.starts_at.tzinfo is None or (
            self.ends_at and self.ends_at.tzinfo is None
        ):
            raise ValueError("Event timestamps require a timezone")
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("Event end must follow its start")
        return self


@router.get("/events")
async def list_events(
    horizon_days: int = 30,
    start: date | None = None,
    end: date | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    today = datetime.now(_tz(user)).date()
    if start is not None or end is not None:
        if start is None or end is None or start > end or (end - start).days > 365:
            raise HTTPException(422, "Choose start and end spanning at most 366 days")
        tz = _tz(user)
        range_start = datetime.combine(start, datetime.min.time(), tzinfo=tz)
        range_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        rows = (await session.scalars(select(UserEvent).where(
            UserEvent.user_id == user.id,
            UserEvent.starts_at < range_end,
            # Include multi-day events overlapping this range.
            (UserEvent.ends_at >= range_start) | ((UserEvent.ends_at.is_(None)) & (UserEvent.starts_at >= range_start)),
        ).order_by(UserEvent.starts_at, UserEvent.id))).all()
        return [_event_dict(e, "past" if e.starts_at < datetime.combine(today, datetime.min.time(), tzinfo=tz) else "upcoming") for e in rows]
    rows = await upcoming_events(
        session, user.id, today, horizon_days=min(max(horizon_days, 1), 366)
    )
    past = (
        await session.scalars(
            select(UserEvent)
            .where(
                UserEvent.user_id == user.id,
                UserEvent.starts_at
                < datetime.combine(today, datetime.min.time(), tzinfo=_tz(user)),
            )
            .order_by(UserEvent.starts_at.desc())
            .limit(20)
        )
    ).all()
    return [_event_dict(e, "upcoming") for e in rows] + [
        _event_dict(e, "past") for e in past
    ]


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.evidence import scope_lock

    await scope_lock(session, user.id, "changes")
    if payload.kind not in (
        "race",
        "run",
        "ride",
        "ski",
        "enduro",
        "sailing",
        "competition",
        "trip",
        "training_camp",
        "gym",
        "other",
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown event kind"
        )
    event = UserEvent(user_id=user.id, **payload.model_dump())
    session.add(event)
    await session.commit()
    return _event_dict(event, "upcoming")


@router.patch("/events/{event_id}")
async def update_event(
    event_id: int,
    payload: EventIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.evidence import scope_lock

    await scope_lock(session, user.id, "changes")
    event = await session.get(UserEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="event not found")
    if event.profile_focus:
        raise HTTPException(409, "Edit this target event in the athlete profile")
    for key, value in payload.model_dump().items():
        setattr(event, key, value)
    await session.commit()
    return _event_dict(event, "upcoming")


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    from app.services.evidence import scope_lock

    await scope_lock(session, user.id, "changes")
    event = await session.get(UserEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="event not found")
    if event.profile_focus:
        raise HTTPException(409, "Remove this target event in the athlete profile")
    await session.delete(event)
    await session.commit()


def _event_dict(event: UserEvent, bucket: str) -> dict:
    return {
        "profile_focus": event.profile_focus,
        "date_only": event.date_only,
        "id": event.id,
        "title": event.title,
        "kind": event.kind,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "priority": event.priority,
        "taper_days": event.taper_days,
        "notes": event.notes,
        "bucket": bucket,
    }


# ----------------------------------------------------------- context docs


class ContextDocIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.get("/context-docs")
async def list_context_docs(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(UserContextDoc).where(UserContextDoc.user_id == user.id)
        )
    ).all()
    return [
        {
            "doc_kind": r.doc_kind,
            "content": r.content,
            "updated_by": r.updated_by,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.put("/context-docs/{kind}")
async def put_context_doc(
    kind: str,
    payload: ContextDocIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.evidence import scope_lock

    await scope_lock(session, user.id, "changes")
    if kind not in _DOC_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"doc_kind must be one of {', '.join(_DOC_KINDS)}",
        )
    doc = await session.scalar(
        select(UserContextDoc).where(
            UserContextDoc.user_id == user.id, UserContextDoc.doc_kind == kind
        )
    )
    if doc is None:
        doc = UserContextDoc(user_id=user.id, doc_kind=kind, content=payload.content)
        session.add(doc)
    else:
        doc.content = payload.content
        doc.updated_by = "user"
    doc.updated_at = datetime.now(UTC)
    await session.commit()
    return {"doc_kind": kind, "content": doc.content, "updated_by": doc.updated_by}


# -------------------------------------------------------------- gym plans


@router.get("/gym/plan/{day}")
async def get_gym_plan(
    day: date,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    plan = await plan_for_date(session, user.id, day)
    if plan is None:
        # template preview: what the recurring slot says, no concrete plan yet
        from app.queries.gym import resolve_day

        template = await resolve_day(session, user.id, day)
        return {
            "date": day.isoformat(),
            "plan": None,
            "template": template,
            "hint": "POST /gym/plan/{date}/generate to create the concrete day plan",
        }
    return {
        "date": day.isoformat(),
        "plan": await session_view(session, user.id, plan.id),
        "template": None,
    }


@router.post("/gym/plan/{day}/generate")
async def post_generate_gym_plan(
    day: date,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    plan, rows, note = await generate_day_plan(session, user, day)
    await session.commit()
    return {
        "plan_id": plan.id,
        "date": plan.date.isoformat(),
        "revision": await plan_revision(session, user.id, plan.id),
        "title": plan.title,
        "source": plan.source,
        "status": plan.status,
        "adjustment_note": note,
        "exercises": rows,
    }


class GymConfirmationIn(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)


@router.post("/gym/plan/{day}/confirm")
async def post_confirm_gym_plan(
    day: date,
    payload: GymConfirmationIn | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.evidence import scope_lock
    from app.models.lab import ChangeAudit

    await scope_lock(session, user.id, "changes")
    await scope_lock(session, user.id, f"gym-plan:{day}")
    plan = await plan_for_date(session, user.id, day)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no plan for that date")
    revision = await plan_revision(session, user.id, plan.id)
    if plan.status in {"done", "completed"}:
        raise HTTPException(409, "Completed sessions cannot be confirmed again")
    audited = await session.scalar(select(ChangeAudit).where(ChangeAudit.user_id == user.id,
        ChangeAudit.action.in_(("gym_draft_generated", "gym_draft_refreshed")),
        ChangeAudit.payload["plan_id"].astext == str(plan.id)).order_by(ChangeAudit.id.desc()).limit(1))
    if plan.status == "draft" and audited and (payload is None or payload.expected_revision != revision):
        raise HTTPException(409, "Suggestion changed; review the latest revision before confirming")
    if payload and payload.expected_revision is not None and payload.expected_revision != revision:
        raise HTTPException(409, "Suggestion changed; review the latest revision before confirming")
    if plan.status == "draft" and audited:
        current_fingerprint = await current_input_fingerprint(session, user, day)
        if audited.payload.get("input_fingerprint") != current_fingerprint:
            raise HTTPException(409, "Training context changed; refresh the suggestion and review it before confirming")
    if plan.status == "draft":
        session.add(ChangeAudit(user_id=user.id, action="gym_draft_confirmed",
            payload={"plan_id": plan.id, "revision": revision}))
    if plan.status == "draft":
        plan.status = "confirmed"
    await session.commit()
    return {"plan_id": plan.id, "status": plan.status}


@router.get("/gym/session/{plan_id}/next")
async def get_next_exercise(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return await next_up(session, user.id, plan_id)
    except (PlanNotFoundError, NotPlanOwnerError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="plan not found"
        ) from None


class SetLogIn(BaseModel):
    gym_day_exercise_id: int
    set_number: int = Field(ge=1, le=30)
    reps_done: int | None = Field(default=None, ge=1, le=500)
    duration_s: int | None = Field(default=None, ge=1, le=86400)
    weight_kg: float | None = Field(default=None, ge=0, le=500, allow_inf_nan=False)

    @model_validator(mode="after")
    def measurement(self):
        if (self.reps_done is None) == (self.duration_s is None):
            raise ValueError("Record either repetitions or duration, matching the exercise target")
        return self


@router.post("/gym/session/{plan_id}/log")
async def post_log_set(
    plan_id: int,
    payload: SetLogIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        result = await log_set(
            session,
            user.id,
            plan_id,
            payload.gym_day_exercise_id,
            payload.set_number,
            payload.reps_done,
            payload.weight_kg,
            duration_s=payload.duration_s,
        )
    except SetLogConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except (PlanNotFoundError, NotPlanOwnerError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="plan not found"
        ) from None
    await session.commit()
    return result


# --------------------------------------------------------------- feedback


class FeedbackIn(BaseModel):
    date: date
    activity_kind: str = Field(min_length=1, max_length=40)
    rpe: int | None = Field(default=None, ge=1, le=10)
    soreness: list[str] | None = None
    injury_flag: bool = False
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/gym/feedback", status_code=status.HTTP_201_CREATED)
async def post_feedback(
    payload: FeedbackIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.evidence import scope_lock

    await scope_lock(session, user.id, "changes")
    fb = SessionFeedback(user_id=user.id, **payload.model_dump())
    session.add(fb)
    await session.commit()
    return {
        "id": fb.id,
        "date": fb.date.isoformat(),
        "activity_kind": fb.activity_kind,
        "rpe": fb.rpe,
        "soreness": fb.soreness,
        "injury_flag": fb.injury_flag,
    }


@router.get("/gym/feedback")
async def get_feedback(
    days: int = 14,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    today = datetime.now(_tz(user)).date()
    rows = await recent_feedback(session, user.id, today, days=max(days, 1))
    return [
        {
            "id": r.id,
            "date": r.date.isoformat(),
            "activity_kind": r.activity_kind,
            "rpe": r.rpe,
            "soreness": r.soreness,
            "injury_flag": r.injury_flag,
            "notes": r.notes,
        }
        for r in rows
    ]
