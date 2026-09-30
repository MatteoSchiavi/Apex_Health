"""Coach API: events calendar, AI context documents, gym day plans, the
in-gym session tracker, and session feedback (owner feature batch).

Every route is `get_current_user`-scoped; foreign ids answer 404 (the
isolation law used across the whole API, §22)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.user import User
from app.queries.gym_detail import (
    NotPlanOwnerError,
    PlanNotFoundError,
    get_owned_plan,
    log_set,
    next_up,
    plan_for_date,
    session_view,
)
from app.services.gym_advisor import (
    generate_day_plan,
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


@router.get("/events")
async def list_events(
    horizon_days: int = 30,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    today = datetime.now(_tz(user)).date()
    rows = await upcoming_events(session, user.id, today, horizon_days=max(horizon_days, 1))
    past = (
        (
            await session.scalars(
                select(UserEvent)
                .where(
                    UserEvent.user_id == user.id,
                    UserEvent.starts_at < datetime.combine(today, datetime.min.time()),
                )
                .order_by(UserEvent.starts_at.desc())
                .limit(20)
            )
        )
        .all()
    )
    return [_event_dict(e, "upcoming") for e in rows] + [
        _event_dict(e, "past") for e in past
    ]


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    if payload.kind not in (
        "race", "run", "ride", "ski", "enduro", "sailing", "competition",
        "trip", "training_camp", "gym", "other",
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown event kind")
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
    event = await session.get(UserEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="event not found")
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
    event = await session.get(UserEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="event not found")
    await session.delete(event)
    await session.commit()


def _event_dict(event: UserEvent, bucket: str) -> dict:
    return {
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
        "title": plan.title,
        "source": plan.source,
        "status": plan.status,
        "adjustment_note": note,
        "exercises": rows,
    }


@router.post("/gym/plan/{day}/confirm")
async def post_confirm_gym_plan(
    day: date,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    plan = await plan_for_date(session, user.id, day)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no plan for that date")
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="plan not found") from None


class SetLogIn(BaseModel):
    gym_day_exercise_id: int
    set_number: int = Field(ge=1, le=30)
    reps_done: int = Field(ge=0, le=500)
    weight_kg: float | None = Field(default=None, ge=0, le=500)


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
        )
    except (PlanNotFoundError, NotPlanOwnerError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="plan not found") from None
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
