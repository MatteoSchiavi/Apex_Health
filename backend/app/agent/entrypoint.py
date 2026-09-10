"""Agent entrypoint — Phase 3 scope (§23).

Phase 3 gives the bot a REAL, data-grounded agent response (§23 Phase 3 AC):
each turn is logged to ai_chat_sessions / ai_chat_messages (with the §6.4
30-minute session boundary) and the model receives a compact health snapshot
built from the shared query layer (§8.2), so answers reference the athlete's
actual numbers instead of hallucinating them.

The full harness — tool registry, tool loop, per-account tier routing,
token_usage accounting (§8.3–8.6, §9) — is Phase 5. It replaces the plain
completion INSIDE this entrypoint; the bot wiring and the chat-log shape
stay put.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.llm import LLMClient
from app.models.chat import AiChatMessage, AiChatSession
from app.queries import (
    integrations_overview,
    latest_daily_feature,
    open_alerts,
    recent_daily_features,
)

logger = logging.getLogger("app.agent.entrypoint")

SESSION_IDLE_MINUTES = 30  # §6.4 session boundary rule

SYSTEM_PROMPT = (
    "You are the Apex Health assistant for one athlete. Answer using ONLY the "
    "data snapshot provided with each message; if something is missing from "
    "it, say so plainly instead of guessing. Be concise and concrete. "
    "Reference bands: recovery/strain/readiness 0-100, ACWR roughly 0.8-1.3 "
    "is the healthy band (>1.5 = injury risk)."
)


@dataclass
class AgentTurnResult:
    reply: str
    session_id: int
    message_id: int


async def run_agent_turn(
    sessionmaker: async_sessionmaker,
    llm: LLMClient,
    user_id: int,
    text: str,
    now: datetime | None = None,
) -> AgentTurnResult:
    """One free-text turn: log user message, snapshot data, complete, log
    the assistant reply with the snapshot as referenced_data (§8.4 shape)."""
    now = now or datetime.now(UTC)
    async with sessionmaker() as session:
        chat_session = await _resolve_session(session, user_id, now)
        session.add(AiChatMessage(session_id=chat_session.id, role="user", content=text))
        await session.flush()
        snapshot = await _build_snapshot(session, user_id)

        response = await llm.complete(
            messages=[
                {
                    "role": "user",
                    "content": f"{text}\n\nData snapshot (JSON):\n{json.dumps(snapshot, ensure_ascii=False)}",
                }
            ],
            system=SYSTEM_PROMPT,
            # §9.2: chat lookups are cheap-tier. Per-account tier caps
            # (ai_access_tier) and lookup/strategic classification arrive
            # with the Phase 5 routing; the owner defaults to cheap_only.
            tier="cheap",
        )
        assistant = AiChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=response.content,
            model_tier="cheap",
            referenced_data=snapshot,
        )
        session.add(assistant)
        await session.commit()
        logger.info(
            "agent turn: user %s session %s, snapshot with latest=%s",
            user_id,
            chat_session.id,
            snapshot["latest"] is not None,
        )
        return AgentTurnResult(response.content, chat_session.id, assistant.id)


async def _resolve_session(session, user_id: int, now: datetime) -> AiChatSession:
    """§6.4: new row when the user messages after >30 idle minutes."""
    chat_session = (
        await session.scalars(
            select(AiChatSession)
            .where(AiChatSession.user_id == user_id)
            .order_by(AiChatSession.last_activity_at.desc())
            .limit(1)
        )
    ).first()
    idle = (now - chat_session.last_activity_at).total_seconds() / 60 if chat_session else None
    if chat_session is not None and idle <= SESSION_IDLE_MINUTES:
        chat_session.last_activity_at = now
        await session.flush()
        return chat_session
    fresh = AiChatSession(user_id=user_id, started_at=now, last_activity_at=now)
    session.add(fresh)
    await session.flush()
    return fresh


def _feature_row(f: Any) -> dict:
    return {
        "date": f.date.isoformat(),
        "readiness": _f(f.readiness_score),
        "recovery": _f(f.recovery_score),
        "strain": _f(f.strain_score),
        "acwr": _f(f.acwr),
        "sleep_architecture": _f(f.sleep_architecture_score),
        "hrv_deviation_pct": _f(f.hrv_deviation_from_baseline),
        "illness_risk": _f(f.illness_risk_score),
        "injury_risk": _f(f.injury_risk_score),
        "iron_status_flag": f.iron_status_flag,
        "data_completeness": f.data_completeness,
    }


def _f(value: Any) -> float | None:
    return float(value) if value is not None else None


async def _build_snapshot(session, user_id: int) -> dict:
    feature = await latest_daily_feature(session, user_id)
    trend = await recent_daily_features(session, user_id, days=7)
    if feature is not None and trend and trend[0].date == feature.date:
        trend = trend[1:]  # latest lives in "latest"; the trend shows context
    alerts = await open_alerts(session, user_id)
    integrations = await integrations_overview(session, user_id)
    return {
        "latest": _feature_row(feature) if feature else None,
        "trend_7d": [_feature_row(f) for f in reversed(trend)],
        "open_alerts": [
            {"type": a.type, "severity": a.severity, "message": a.message} for a in alerts
        ],
        "integrations": [
            {"provider": i["provider"], "status": i["status"]} for i in integrations
        ],
    }
