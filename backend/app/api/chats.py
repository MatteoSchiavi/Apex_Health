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
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.entrypoint import AgentTurnResult, run_agent_turn
from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session, sessionmaker as app_sessionmaker
from app.core.embeddings import build_embedding_client
from app.core.llm import build_llm_client
from app.models.chat import AiChatMessage, AiChatSession
from app.models.user import User
from app.schemas.ui import ChatMessageOut, ChatPostIn, ChatSessionDetailOut, ChatSessionOut

logger = logging.getLogger("api.chats")

router = APIRouter(prefix="/coach/chats", tags=["chats"])

MAX_TITLE_LEN = 80


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
) -> ChatSessionDetailOut:
    chat: AiChatSession | None = None
    if payload.session_id is not None:
        chat = await session.get(AiChatSession, payload.session_id)
        if chat is None or chat.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")

    settings = get_settings()
    llm = build_llm_client()
    embeddings = build_embedding_client() if settings.openai_api_key else None

    result: AgentTurnResult = await run_agent_turn(
        app_sessionmaker,
        llm,
        user_id=user.id,
        text=payload.text,
        tier=payload.tier,
        embedding_client=embeddings,
        session_id=chat.id if chat else None,
    )
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
