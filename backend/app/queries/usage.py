"""Cost accounting (MASTER_SPEC §8.6): every LLM/embedding call writes a
token_usage row; a daily task sums the day's cost and fires a budget_warning
alert when it crosses DAILY_TOKEN_BUDGET_USD (informational, not a hard stop).

Rates come from §9.1's published per-1M-token prices, keyed by tier. The
powerful tier has a distinct cached-token price (GLM prompt caching); free is
$0 by design — that is the whole point of the tier. Embeddings bill at the
pinned model's own price regardless of tier (they log tier='free' as the
closest utility bucket, but their cost is real money).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import TokenUsage

# §9.1 rates, USD per 1M tokens: (input, output, cached_input).
TIER_RATES_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "free": (0.0, 0.0, 0.0),
    "cheap": (1.00, 5.00, 1.00),  # no separate cached price published — in-rate
    "powerful": (1.40, 4.40, 0.26),
}
# OpenAI text-embedding-3-small published price (§6.2 pinned model).
EMBEDDING_USD_PER_MTOK = 0.02


def estimate_llm_cost_usd(
    tier: str, tokens_in: int, tokens_out: int, cached_tokens: int = 0
) -> Decimal:
    """§9.1 rate table → estimated cost. Unknown tiers cost 0 — a surprise
    tier is a routing bug, not a billing event."""
    in_rate, out_rate, cached_rate = TIER_RATES_PER_MTOK.get(tier, (0.0, 0.0, 0.0))
    billable_in = max(tokens_in - cached_tokens, 0)
    cost = (
        billable_in / 1_000_000 * in_rate
        + tokens_out / 1_000_000 * out_rate
        + cached_tokens / 1_000_000 * cached_rate
    )
    return Decimal(str(round(cost, 6)))


def estimate_embedding_cost_usd(tokens_in: int) -> Decimal:
    return Decimal(str(round(tokens_in / 1_000_000 * EMBEDDING_USD_PER_MTOK, 6)))


async def log_llm_usage(
    session: AsyncSession,
    *,
    user_id: int | None,
    call_type: str,
    tier: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cached_tokens: int = 0,
) -> None:
    """One LLM completion → one token_usage row (§8.6). Flushes with the
    caller's transaction — never commits; call sites own the unit of work."""
    session.add(
        TokenUsage(
            user_id=user_id,
            call_type=call_type,
            tier=tier,
            model=model,
            tokens_in=tokens_in or None,
            tokens_out=tokens_out or None,
            cached_tokens=cached_tokens or None,
            cost_estimate_usd=estimate_llm_cost_usd(tier, tokens_in, tokens_out, cached_tokens),
        )
    )


async def log_embedding_usage(
    session: AsyncSession,
    *,
    user_id: int | None,
    model: str,
    tokens_in: int,
) -> None:
    session.add(
        TokenUsage(
            user_id=user_id,
            call_type="embedding",
            tier="free",
            model=model,
            tokens_in=tokens_in or None,
            cost_estimate_usd=estimate_embedding_cost_usd(tokens_in),
        )
    )


async def day_spend(session: AsyncSession, moment_utc: datetime) -> Decimal:
    """Platform-wide estimated cost for the UTC calendar day of moment_utc
    (§8.6 daily budget task)."""
    start, end = _utc_day_bounds(moment_utc)
    total = await session.scalar(
        select(func.coalesce(func.sum(TokenUsage.cost_estimate_usd), 0)).where(
            TokenUsage.created_at >= start, TokenUsage.created_at < end
        )
    )
    return Decimal(total or 0)


async def day_spend_by_user(
    session: AsyncSession, moment_utc: datetime
) -> dict[int, Decimal]:
    """Per-user estimated cost for the UTC day of moment_utc — the daily
    budget check (§8.6) attributes spend to the account that caused it, so
    each account's cost valve (§9.2/§15) reads its own number."""
    start, end = _utc_day_bounds(moment_utc)
    rows = await session.execute(
        select(
            TokenUsage.user_id,
            func.coalesce(func.sum(TokenUsage.cost_estimate_usd), 0),
        )
        .where(
            TokenUsage.user_id.is_not(None),
            TokenUsage.created_at >= start,
            TokenUsage.created_at < end,
        )
        .group_by(TokenUsage.user_id)
    )
    return {user_id: Decimal(total or 0) for user_id, total in rows.fetchall()}


async def user_day_spend(
    session: AsyncSession, user_id: int, moment_utc: datetime
) -> Decimal:
    """F-18 audit: one user's estimated spend for the UTC day of moment_utc.

    Used by the pre-turn cost gate (api/chats.post_message) to hard-stop a
    user who has already crossed 2× the daily_token_budget_usd threshold —
    the budget task at 23:45 UTC is informational-only and a scripted user
    could drive unlimited spend between checks.
    """
    start, end = _utc_day_bounds(moment_utc)
    total = await session.scalar(
        select(func.coalesce(func.sum(TokenUsage.cost_estimate_usd), 0)).where(
            TokenUsage.user_id == user_id,
            TokenUsage.created_at >= start,
            TokenUsage.created_at < end,
        )
    )
    return Decimal(total or 0)


def _utc_day_bounds(moment_utc: datetime) -> tuple[datetime, datetime]:
    start = datetime(moment_utc.year, moment_utc.month, moment_utc.day, tzinfo=UTC)
    return start, start + timedelta(days=1)
