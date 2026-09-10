"""Agent entrypoint (§8.4, §10.2).

Phase 3 gave the bot a real data-grounded reply; Phase 5 replaces the plain
completion INSIDE this entrypoint with the full harness (§23): the §8.4
system block (profile, feature weights, 7–14-day detail window, open
alerts) plus the §8.3 tool registry so the model can pull finer data itself.
The bot wiring and the chat-log shape stay put — ai_chat_messages still
carries referenced_data + model_tier.

Tier resolution (§9.2: per-account caps + lookup/strategic classification)
arrives with the routing module; the call site here owns that choice.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.loop import AgentLoopResult, run_agent_loop
from app.core.llm import LLMClient
from app.models.chat import AiChatMessage, AiChatSession
from app.models.features import DailyFeature
from app.models.user import User
from app.queries import (
    integrations_overview,
    latest_daily_feature,
    open_alerts,
    recent_daily_features,
)
from app.features.weights import load_weights

logger = logging.getLogger("app.agent.entrypoint")

SESSION_IDLE_MINUTES = 30  # §6.4 session boundary rule

SYSTEM_PROMPT = (
    "You are the Apex Health assistant for one athlete. Use the data in the "
    "system context and the tools provided; if something is missing from both, "
    "say so plainly instead of guessing. Be concise and concrete. For multi-part "
    "questions, call the tools you need, then answer once. "
    "Reference bands: recovery/strain/readiness 0-100, ACWR roughly 0.8-1.3 "
    "is the healthy band (>1.5 = injury risk)."
)


@dataclass
class AgentTurnResult:
    reply: str
    session_id: int
    message_id: int
    drafts: list[dict[str, Any]] = field(default_factory=list)
    loop: AgentLoopResult | None = None


async def run_agent_turn(
    sessionmaker: async_sessionmaker,
    llm: LLMClient,
    user_id: int,
    text: str,
    now: datetime | None = None,
    tier: str = "cheap",
    embedding_client: Any | None = None,
) -> AgentTurnResult:
    """One free-text turn: log user message, build the §8.4 system block, run
    the tool loop, log the assistant reply with referenced_data + model_tier."""
    now = now or datetime.now(UTC)
    async with sessionmaker() as session:
        chat_session = await _resolve_session(session, user_id, now)
        session.add(AiChatMessage(session_id=chat_session.id, role="user", content=text))
        await session.flush()
        snapshot = await _build_snapshot(session, user_id, now)
        system = _system_block(snapshot)
        await session.commit()  # persist session + user message before the loop runs

    loop_result = await run_agent_loop(
        sessionmaker,
        llm,
        user_id=user_id,
        session_id=chat_session.id,
        text=text,
        system=system,
        tier=tier,
        today=snapshot.get("_local_today") or now.date(),
        embedding_client=embedding_client,
    )

    referenced = {k: v for k, v in snapshot.items() if not k.startswith("_")}
    referenced["tool_calls"] = loop_result.tool_audit
    async with sessionmaker() as session:
        assistant = AiChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=loop_result.reply,
            model_tier=tier,
            referenced_data=referenced,
        )
        session.add(assistant)
        await session.commit()
        logger.info(
            "agent turn: user %s session %s, %s tool call(s), converged=%s",
            user_id,
            chat_session.id,
            len(loop_result.tool_audit),
            loop_result.converged,
        )
        return AgentTurnResult(
            loop_result.reply,
            chat_session.id,
            assistant.id,
            drafts=loop_result.drafts,
            loop=loop_result,
        )


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


async def _build_snapshot(session, user_id: int, now: datetime) -> dict:
    """§8.4 request data: latest day, a 14-day recent-detail window, open
    alerts, integrations, plus profile and active feature weights (the
    cacheable system-block content)."""
    feature = await latest_daily_feature(session, user_id)
    trend = await recent_daily_features(session, user_id, days=14)  # §8.4: 7–14-day window
    if feature is not None and trend and trend[0].date == feature.date:
        trend = trend[1:]  # latest lives in "latest"; the trend shows context
    alerts = await open_alerts(session, user_id)
    integrations = await integrations_overview(session, user_id)

    user = await session.get(User, user_id)
    tz = ZoneInfo(user.timezone) if user else UTC
    local_today = now.astimezone(tz).date()

    weights = {}
    for feature_name in ("recovery_score", "readiness_score"):
        weights[feature_name] = await load_weights(
            session, feature_name, datetime(local_today.year, local_today.month, local_today.day, tzinfo=tz)
        )

    return {
        "_local_today": local_today,
        "_timezone": tz.key,
        "profile": {"timezone": tz.key, "local_today": local_today.isoformat()},
        "feature_weights": weights,
        "latest": _feature_row(feature) if feature else None,
        "trend_14d": [_feature_row(f) for f in reversed(trend)],
        "open_alerts": [
            {"type": a.type, "severity": a.severity, "message": a.message} for a in alerts
        ],
        "integrations": [
            {"provider": i["provider"], "status": i["status"]} for i in integrations
        ],
    }


def _system_block(snapshot: dict) -> str:
    """§8.4 cached system block: instruction + stable context JSON. Content
    changes at most daily, so the provider's prompt caching bites."""
    context = {
        "profile": snapshot["profile"],
        "feature_weights": snapshot["feature_weights"],
        "latest": snapshot["latest"],
        "trend_14d": snapshot["trend_14d"],
        "open_alerts": snapshot["open_alerts"],
        "integrations": snapshot["integrations"],
    }
    return f"{SYSTEM_PROMPT}\n\nCurrent context (JSON):\n{json.dumps(context, ensure_ascii=False, default=str)}"
