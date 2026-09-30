"""Web AI-coach chat: resumable sessions (owner ask — "AI chats saved locally
to let the user resume past questions").

- GET    /coach/chats           — session list (sidebar); newest first
- GET    /coach/chats/{id}      — full transcript of one session (resume)
- POST   /coach/chats           — send a message: {text, session_id?}; when
                                  session_id is null a NEW session starts
                                  (the web UI owns session boundaries —
                                  unlike the bot's 30-min idle rule) and the
                                  session title is generated from the first
                                  user message
- DELETE /coach/chats/{id}      — forget a conversation

Sessions and messages live in ai_chat_sessions / ai_chat_messages (server
side, per-user scoped); the SPA additionally mirrors the active transcript
into localStorage so a reload never loses an unsent draft or recent view.

F-01 audit: ``run_agent_turn`` is wrapped in ``asyncio.wait_for`` with a
hard wall-clock cap and gated by a per-user Redis semaphore so a single
user cannot pin worker sockets indefinitely. The turn itself is unchanged
— it still runs inline (acceptable for an 8 GB home server with <10 users);
the audit's recommended full move to Celery is documented in the audit
roadmap (Phase 2 item 4) but the wait_for+semaphore combo closes the
self-DoS / runaway-bill hole immediately.
"""

import asyncio
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.entrypoint import AgentTurnResult, run_agent_turn
from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session, sessionmaker as app_sessionmaker
from app.core.embeddings import build_embedding_client
from app.core.llm import build_llm_client
from app.core.redis import get_redis
from app.models.chat import AiChatMessage, AiChatSession
from app.models.user import User
from app.queries.usage import user_day_spend
from app.schemas.ui import ChatMessageOut, ChatPostIn, ChatSessionDetailOut, ChatSessionOut

logger = logging.getLogger("api.chats")

router = APIRouter(prefix="/coach/chats", tags=["chats"])

MAX_TITLE_LEN = 80

# F-01 audit: hard wall-clock cap on a single agent turn. The agent loop's
# own MAX_ITERATIONS bounds LLM CALLS (8 × 120 s = 960 s worst case); this
# cap bounds WALL CLOCK so a stuck provider cannot hold a worker socket
# forever. 200s is below typical proxy timeouts and above the 8-iteration
# expected case (~30-60s).
AGENT_TURN_TIMEOUT_S = 200

# Per-user concurrency: only ONE agent turn per user at a time. The Redis
# semaphore key holds the user_id; acquire-with-TTL auto-expires stale locks
# (a worker crash mid-turn would otherwise leave the user locked out).
_AGENT_LOCK_KEY = "agent_turn_lock:user:{user_id}"
_AGENT_LOCK_TTL_S = AGENT_TURN_TIMEOUT_S + 30  # auto-expire after the wall cap


def _title_from(text: str) -> str:
    """Local, zero-token fallback title: first line, trimmed."""
    line = text.strip().splitlines()[0].strip()
    if len(line) > MAX_TITLE_LEN:
        line = line[: MAX_TITLE_LEN - 1].rstrip() + "…"
    return line or "New conversation"


def _session_out(row, message_count: int = 0) -> ChatSessionOut:
    return ChatSessionOut(
        id=row.id,
        title=row.title,
        started_at=row.started_at,
        last_activity_at=row.last_activity_at,
        message_count=message_count,
    )


@router.get("", response_model=list[ChatSessionOut])
async def list_chats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
) -> list[ChatSessionOut]:
    rows = (
        await session.scalars(
            select(AiChatSession)
            .where(AiChatSession.user_id == user.id)
            .order_by(AiChatSession.last_activity_at.desc())
            .limit(limit)
        )
    ).all()
    count_map = dict(
        (
            await session.execute(
                select(AiChatMessage.session_id, func.count())
                .where(AiChatMessage.session_id.in_([r.id for r in rows] or [0]))
                .group_by(AiChatMessage.session_id)
            )
        ).all()
    )
    return [_session_out(r, count_map.get(r.id, 0)) for r in rows]


@router.get("/{session_id}", response_model=ChatSessionDetailOut)
async def chat_detail(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatSessionDetailOut:
    chat = await session.get(AiChatSession, session_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")
    messages = (
        await session.scalars(
            select(AiChatMessage)
            .where(AiChatMessage.session_id == chat.id)
            .order_by(AiChatMessage.id)
        )
    ).all()
    return ChatSessionDetailOut(
        id=chat.id,
        title=chat.title,
        started_at=chat.started_at,
        last_activity_at=chat.last_activity_at,
        message_count=len(messages),
        messages=[
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                model_tier=m.model_tier,
                referenced_data=m.referenced_data,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.post("", response_model=ChatSessionDetailOut, status_code=status.HTTP_201_CREATED)
async def post_message(
    payload: ChatPostIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ChatSessionDetailOut:
    chat: AiChatSession | None = None
    if payload.session_id is not None:
        chat = await session.get(AiChatSession, payload.session_id)
        if chat is None or chat.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")

    settings = get_settings()
    llm = build_llm_client()
    embeddings = build_embedding_client() if settings.openai_api_key else None

    # F-18 audit: pre-turn cost gate — hard-stop a user who has already
    # crossed 2× the daily_token_budget_usd threshold TODAY. The nightly
    # budget task at 23:45 UTC is informational-only; without this gate a
    # scripted user could drive unlimited spend between checks.
    if settings.daily_token_budget_usd > 0:
        from datetime import UTC, datetime
        async with app_sessionmaker() as cost_session:
            spent = await user_day_spend(cost_session, user.id, datetime.now(UTC))
        if spent > Decimal(str(settings.daily_token_budget_usd)) * 2:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Daily AI budget exceeded (${spent:.2f} spent today, limit "
                f"${settings.daily_token_budget_usd:.2f}). Try again tomorrow.",
            )

    # F-01 audit: per-user Redis lock so a single user cannot drive
    # concurrent agent turns (and runaway spend). The SET NX EX pattern is
    # the single-flight primitive: only the first acquirer wins; subsequent
    # attempts get a 429 until the lock expires or is released.
    lock_key = _AGENT_LOCK_KEY.format(user_id=user.id)
    acquired = await redis.set(lock_key, "1", ex=_AGENT_LOCK_TTL_S, nx=True)
    if not acquired:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "An agent turn is already running for your account — wait for it "
            "to finish before sending another message.",
        )
    try:
        # F-01 audit: hard wall-clock cap. asyncio.wait_for cancels the
        # underlying task on timeout — the LLM client's httpx call is
        # cancellation-aware (any in-flight HTTP request is aborted).
        try:
            result: AgentTurnResult = await asyncio.wait_for(
                run_agent_turn(
                    app_sessionmaker,
                    llm,
                    user_id=user.id,
                    text=payload.text,
                    tier=payload.tier,
                    embedding_client=embeddings,
                    session_id=chat.id if chat else None,
                ),
                timeout=AGENT_TURN_TIMEOUT_S,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "agent turn timed out for user %s after %ss",
                user.id, AGENT_TURN_TIMEOUT_S,
            )
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "The agent turn exceeded the time budget — try a narrower question.",
            ) from exc
    finally:
        # Always release the lock — a crash between acquire and release
        # still auto-expires via the TTL.
        await redis.delete(lock_key)

    # Title: the first exchange names the conversation (local truncation —
    # no extra LLM call; the cheap model budget goes to the answer).
    async with app_sessionmaker() as s2:
        row = await s2.get(AiChatSession, result.session_id)
        if row.title is None:
            row.title = _title_from(payload.text)
            await s2.commit()
        messages = (
            await s2.scalars(
                select(AiChatMessage)
                .where(AiChatMessage.session_id == row.id)
                .order_by(AiChatMessage.id)
            )
        ).all()
        return ChatSessionDetailOut(
            id=row.id,
            title=row.title,
            started_at=row.started_at,
            last_activity_at=row.last_activity_at,
            message_count=len(messages),
            messages=[
                ChatMessageOut(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    model_tier=m.model_tier,
                    referenced_data=m.referenced_data,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    chat = await session.get(AiChatSession, session_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")
    await session.execute(
        delete(AiChatMessage).where(AiChatMessage.session_id == chat.id)
    )
    await session.delete(chat)
    await session.commit()
