"""AI harness v2: per-user context documents + budgeted snapshot assembly.

Owner requirement (2026-09): "different documents where user data is stored
to give AI as much context as possible while still keeping it lightweight
to not waste tokens."

Design: the user's context docs (profile, goals, injuries, equipment,
preferences, season_plan) are self-contained markdown the user (or the
agent, via the update_context_doc tool) maintains. They are NOT re-derived
per request — they persist, and the snapshot embeds them with a hard
character budget. Live quantities (metrics, events, today's gym plan) stay
compact and structured. Everything that changes at most daily stays in the
cached system block; the tools cover anything finer.

Budget law: the total system-block context stays ~2-4k chars at friends
scale. Docs are truncated last-first with an explicit marker so the model
knows it saw a tail-truncated doc.
"""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach import UserContextDoc, UserEvent
from app.models.gym_detail import GymDayPlan
from app.models.user import User

logger = logging.getLogger("app.agent.context")

# --- token budget knobs (documented judgment calls, not spec constants) ----
_DOC_CHAR_BUDGET = 3500  # all docs together
_DOC_KIND_ORDER = (
    "profile", "injuries", "goals", "season_plan", "equipment", "preferences",
)
_DOC_KIND_CHAR_BUDGET = 1200  # single-doc cap

_EVENT_HORIZON_DAYS = 14

_GYM_NOTE_CHARS = 300


def _truncate(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + " …[truncated]"


async def context_docs_compact(
    session: AsyncSession, user_id: int
) -> list[dict]:
    """Context docs under a shared char budget; priority order first."""
    rows = (
        await session.scalars(
            select(UserContextDoc).where(UserContextDoc.user_id == user_id)
        )
    ).all()
    by_kind = {r.doc_kind: r for r in rows}
    out: list[dict] = []
    remaining = _DOC_CHAR_BUDGET
    for kind in _DOC_KIND_ORDER:
        doc = by_kind.get(kind)
        if doc is None or not doc.content.strip():
            continue
        budget = min(_DOC_KIND_CHAR_BUDGET, remaining)
        if budget <= 200:
            out.append(
                {"kind": kind, "content": "…[omitted: context budget spent]"}
            )
            continue
        out.append(
            {
                "kind": kind,
                "content": _truncate(doc.content.strip(), budget),
                "updated_by": doc.updated_by,
            }
        )
        remaining -= min(len(doc.content), budget)
    return out


async def upcoming_events_compact(
    session: AsyncSession, user_id: int, today: date, tz: ZoneInfo
) -> list[dict]:
    """Next 14 days of calendar events — compact enough for every turn."""
    horizon_start = datetime.combine(today, datetime.min.time())
    horizon_end = datetime.combine(
        today + timedelta(days=_EVENT_HORIZON_DAYS), datetime.min.time()
    )
    rows = (
        await session.scalars(
            select(UserEvent)
            .where(
                UserEvent.user_id == user_id,
                UserEvent.starts_at >= horizon_start,
                UserEvent.starts_at < horizon_end,
            )
            .order_by(UserEvent.starts_at)
        )
    ).all()
    return [
        {
            "title": r.title,
            "kind": r.kind,
            "date": r.starts_at.astimezone(tz).date().isoformat(),
            "priority": r.priority,
            "taper_days": r.taper_days,
        }
        for r in rows
    ]


async def today_gym_compact(
    session: AsyncSession, user_id: int, today: date
) -> dict | None:
    """Today's concrete gym plan (title + advisor note) — exercises live in
    the get_gym_day tool, not in every turn's context."""
    plan = await session.scalar(
        select(GymDayPlan).where(
            GymDayPlan.user_id == user_id, GymDayPlan.date == today
        )
    )
    if plan is None:
        return None
    return {
        "title": plan.title,
        "status": plan.status,
        "adjustment_note": _truncate(plan.adjustment_note or "", _GYM_NOTE_CHARS),
    }


async def coach_context(
    session: AsyncSession, user_id: int, now: datetime
) -> dict:
    """The coach layer of the snapshot: docs + events + today's gym plan."""
    user = await session.get(User, user_id)
    tz = ZoneInfo(user.timezone) if user else ZoneInfo("UTC")
    local_today = now.astimezone(tz).date()
    return {
        "context_docs": await context_docs_compact(session, user_id),
        "upcoming_events": await upcoming_events_compact(session, user_id, local_today, tz),
        "gym_today": await today_gym_compact(session, user_id, local_today),
    }
