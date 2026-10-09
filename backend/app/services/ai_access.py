"""Fail-closed account authorization at every external completion boundary.

Reservations commit before network I/O. Failed/ambiguous calls retain their full
reservation: a timeout is not proof the provider did not bill the request.
"""
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit
from sqlalchemy import func, select
from app.core.config import get_settings
from app.core.llm import resolve_llm_endpoint
from app.models.athlete import AiConsent, AiBudgetReservation
from app.models.user import AuthCredential
from app.queries.usage import estimate_llm_cost_usd, user_day_spend
from app.services.evidence import EvidenceError, scope_lock

POLICY_VERSION = "athlete-ai-consent-v1"
PURPOSE = "personalized_coaching_summaries_and_reviewable_training_proposals"
CATEGORY_LIMITS = {"onboarding_extraction": 40000, "standard_chat": 80000,
                   "strategic_coaching": 100000, "periodic_reports": 80000}


def provider_identity():
    settings = get_settings()
    identities = []
    for tier in ("cheap", "powerful", "medical"):
        if tier == "medical" and not settings.medical_tier_enabled:
            continue
        try:
            base, _, _ = resolve_llm_endpoint(settings, tier)
        except Exception:
            return "unconfigured"
        parsed = urlsplit(base)
        if not parsed.hostname or parsed.scheme not in {"http", "https"}:
            return "unconfigured"
        # Never include credentials, query parameters or tokens in this public identity.
        identities.append(f"{tier}:{parsed.scheme}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}{parsed.path}")
    if settings.openai_api_key:
        parsed = urlsplit(settings.openai_api_base)
        identities.append(f"embeddings:{parsed.scheme}://{parsed.hostname}:{parsed.port or 443}")
    return "|".join(identities)


async def effective_access(session, user_id, *, include_budget=True):
    credential = await session.get(AuthCredential, user_id, populate_existing=True)
    consent = await session.get(AiConsent, user_id, populate_existing=True)
    if (not get_settings().ai_processing_enabled or not credential or credential.disabled
        or credential.ai_access_tier not in {"cheap_only", "full"}
        or not consent or not consent.active or not consent.accepted_at
        or consent.policy_version != POLICY_VERSION or consent.purpose != PURPOSE
        or consent.provider_identity != provider_identity() or provider_identity() == "unconfigured"):
        return "disabled"
    if include_budget and (await budget_state(session, user_id))["exhausted"]:
        return "disabled"
    return "full" if credential.ai_access_tier == "full" else "basic"


async def require_access(session, user_id, category="standard_chat", tier="cheap"):
    state = await effective_access(session, user_id, include_budget=False)
    if state == "disabled" or (state != "full" and (
        category in {"strategic_coaching", "periodic_reports"} or tier in {"powerful", "medical"})):
        raise EvidenceError("POLICY_DENIED", "Active AI consent and account authorization are required")
    return state


async def budget_state(session, user_id, now=None):
    now = now or datetime.now(UTC)
    rows = (await session.scalars(select(AiBudgetReservation).where(
        AiBudgetReservation.user_id == user_id, AiBudgetReservation.day == now.date()))).all()
    spent = await user_day_spend(session, user_id, now)
    actual = sum((r.actual_usd or Decimal(0)) for r in rows if r.state == "reconciled")
    pending = sum(r.reserved_usd for r in rows if r.state != "reconciled")
    used_usd = max(spent, actual) + pending
    categories = {key: {"used_tokens": sum(
        (r.actual_tokens if r.state == "reconciled" else r.reserved_tokens) or 0
        for r in rows if r.category == key), "limit_tokens": limit}
        for key, limit in CATEGORY_LIMITS.items()}
    tokens = sum(c["used_tokens"] for c in categories.values())
    limit_usd = get_settings().daily_token_budget_usd
    return {"day": str(now.date()), "timezone": "UTC", "used_usd": float(used_usd),
        "limit_usd": limit_usd, "used_tokens": tokens, "limit_tokens": get_settings().ai_daily_token_limit,
        "categories": categories, "exhausted": tokens >= get_settings().ai_daily_token_limit
        or (limit_usd > 0 and used_usd >= Decimal(str(limit_usd)))}


async def reserve(session, user_id, category, tier, input_bytes, now=None):
    if category not in CATEGORY_LIMITS:
        raise EvidenceError("INVALID_ARGUMENTS", "Unknown AI budget category")
    now = now or datetime.now(UTC)
    await scope_lock(session, user_id, "ai_access")
    await require_access(session, user_id, category, tier)
    state = await budget_state(session, user_id, now)
    # UTF-8 bytes bound the input tokens conservatively; LiveGLMClient caps output.
    tokens = input_bytes + 4096
    cost = Decimal(input_bytes * 1.4 + 4096 * 5) / Decimal(1000000)
    category_state = state["categories"][category]
    if (state["used_tokens"] + tokens > state["limit_tokens"]
        or category_state["used_tokens"] + tokens > category_state["limit_tokens"]
        or (state["limit_usd"] > 0 and Decimal(str(state["used_usd"])) + cost > Decimal(str(state["limit_usd"])) )):
        raise EvidenceError("BUDGET_EXCEEDED", "Daily account or category AI budget reached before invocation")
    row = AiBudgetReservation(user_id=user_id, day=now.date(), category=category,
        reserved_usd=cost, reserved_tokens=tokens, state="reserved")
    session.add(row)
    await session.flush()
    return row.id


async def guarded_complete(sessionmaker, llm, user_id, category, **kwargs):
    tier = kwargs.get("tier", "cheap")
    size = len(json.dumps(kwargs, ensure_ascii=False, default=str).encode())
    async with sessionmaker() as session:
        ident = await reserve(session, user_id, category, tier, size)
        await session.commit()
    try:
        async with sessionmaker() as session:
            await require_access(session, user_id, category, tier)
        response = await asyncio.wait_for(llm.complete(**kwargs), timeout=45)
    except BaseException:
        async with sessionmaker() as session:
            row = await session.get(AiBudgetReservation, ident)
            row.state = "uncertain"
            await session.commit()
        raise
    async with sessionmaker() as session:
        await scope_lock(session, user_id, "ai_access")
        row = await session.get(AiBudgetReservation, ident)
        row.actual_tokens = response.tokens_in + response.tokens_out
        row.actual_usd = estimate_llm_cost_usd(tier, response.tokens_in, response.tokens_out,
            response.cached_tokens, model=response.model)
        row.state = "reconciled" if response.tokens_in > 0 and (response.tokens_out > 0 or not (response.content or response.tool_calls)) else "uncertain"
        await session.commit()
    return response


async def guarded_embedding(sessionmaker, client, user_id, texts):
    """The legacy optional embedding path has the same voluntary authorization."""
    from app.queries.usage import estimate_embedding_cost_usd
    async with sessionmaker() as session:
        ident = await reserve(session, user_id, "standard_chat", "cheap", sum(len(t.encode()) for t in texts))
        await session.commit()
    try:
        async with sessionmaker() as session:
            await require_access(session, user_id)
        response = await asyncio.wait_for(client.embed(texts), timeout=45)
    except BaseException:
        async with sessionmaker() as session:
            row = await session.get(AiBudgetReservation, ident)
            row.state = "uncertain"
            await session.commit()
        raise
    async with sessionmaker() as session:
        await scope_lock(session, user_id, "ai_access")
        row = await session.get(AiBudgetReservation, ident)
        row.actual_tokens, row.actual_usd, row.state = response.tokens_in, estimate_embedding_cost_usd(response.tokens_in), "reconciled" if response.tokens_in > 0 else "uncertain"
        await session.commit()
    return response
