"""Per-account AI routing (MASTER_SPEC §9.2).

§9.2 routing order:
1. `auth_credentials.ai_access_tier` — if `cheap_only`, the request is
   capped at free/cheap regardless of what the message looks like; the
   powerful tier is simply unreachable for that account (the per-friend
   cost-control valve, §15).
2. If `full`: a free-tier classification call tags the message `lookup`
   (→ cheap) or `strategic` (→ powerful).

Hardcoded elsewhere (§9.2): daily summaries are templated (no LLM);
weekly/monthly reports always run powerful — those never pass through here.

Fail-closed everywhere: unknown/missing account rows cap at cheap_only;
a classification error or unparsable reply defaults to lookup (cheap) —
surprises must cost less, never more.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMError, LLMClient, extract_json_object
from app.models.user import AuthCredential
from app.queries.usage import log_llm_usage

logger = logging.getLogger("app.agent.routing")

CLASSIFY_SYSTEM_PROMPT = (
    "You classify one message from an athlete for routing. Reply with ONLY a "
    "JSON object, no prose: {\"category\": \"lookup\"} or "
    "{\"category\": \"strategic\"}.\n"
    "\"lookup\" = simple data questions answerable from stored metrics or "
    "tools (statuses, trends, facts, schedules).\n"
    "\"strategic\" = planning, periodization, plan generation, multi-step "
    "analysis, open-ended coaching advice."
)


@dataclass
class RoutingDecision:
    tier: str  # the tier this turn runs at: 'cheap' or 'powerful'
    classification: str | None  # 'lookup' | 'strategic' — None when capped
    cap: str  # the account's ai_access_tier


async def resolve_tier(
    session: AsyncSession, user_id: int, text: str, llm: LLMClient
) -> RoutingDecision:
    """§9.2 routing rule for one chat turn. The classification call (when it
    happens) logs its own token_usage row as tier='free' (§9.1: the router
    itself is free-tier)."""
    credential = await session.get(AuthCredential, user_id)
    cap = credential.ai_access_tier if credential is not None else "cheap_only"
    if cap not in ("cheap_only", "full"):
        # unknown value → fail closed (cheap)
        logger.warning("unknown ai_access_tier %r for user %s — capping", cap, user_id)
        cap = "cheap_only"

    if cap == "cheap_only":
        return RoutingDecision(tier="cheap", classification=None, cap=cap)

    classification = await _classify(session, user_id, text, llm)
    tier = "cheap" if classification == "lookup" else "powerful"
    return RoutingDecision(tier=tier, classification=classification, cap=cap)


async def _classify(session: AsyncSession, user_id: int, text: str, llm: LLMClient) -> str:
    """Free-tier classification (§9.2 step 2). Any failure → 'lookup'."""
    try:
        response = await llm.complete(
            messages=[{"role": "user", "content": text}],
            system=CLASSIFY_SYSTEM_PROMPT,
            tier="free",
        )
    except LLMError as exc:
        logger.warning("classification call failed — defaulting to lookup: %s", exc)
        return "lookup"
    await log_llm_usage(
        session,
        user_id=user_id,
        call_type="routing_classification",
        tier="free",
        model=response.model,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cached_tokens=response.cached_tokens,
    )
    try:
        category = extract_json_object(response.content).get("category")
    except (LLMError, ValueError) as exc:
        logger.warning("unparsable classification %r — defaulting to lookup", response.content)
        return "lookup"
    if category not in ("lookup", "strategic"):
        return "lookup"
    return category
