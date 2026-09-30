"""Cost governance tests (§8.6): the daily budget check fires an
informational budget_warning (once per user per day) with a Telegram push,
stays quiet under budget, and honours the disable switch. The voice pipeline
logs its extraction call as tier='free'."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.alert import Alert
from app.models.ai import TokenUsage
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from app.queries.usage import log_llm_usage
from app.tasks.budget import _daily_check
from tests.helpers.telegram import FixtureTelegramClient

NOW = datetime(2025, 3, 10, 23, 45, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _isolate_budget_tables():
    """Alerts persist across tests in this session-scoped DB — start each
    budget test with clean alert/token_usage tables."""
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE alerts, token_usage RESTART IDENTITY CASCADE"))
    await engine.dispose()


async def _owner_id(db_session) -> int:
    return (
        await db_session.scalars(
            select(AuthCredential.user_id).where(AuthCredential.role == "owner")
        )
    ).first()


async def _spend(db_session, user_id: int, usd: str) -> None:
    """One synthetic token_usage row worth `usd`, stamped inside the UTC day
    the budget check will scan."""
    db_session.add(
        TokenUsage(
            user_id=user_id,
            call_type="chat",
            tier="cheap",
            model="glm-4.7-flash",
            tokens_in=1000,
            tokens_out=100,
            cost_estimate_usd=usd,
            created_at=NOW,
        )
    )
    await db_session.commit()


async def test_budget_breach_fires_alert_and_pushes(db_session, monkeypatch):
    owner = await _owner_id(db_session)
    await _spend(db_session, owner, "0.90")  # over the 0.25 default

    client = FixtureTelegramClient()
    monkeypatch.setattr(
        "app.tasks.budget.get_settings",
        lambda: SimpleNamespace(daily_token_budget_usd=0.25, telegram_bot_token="fixture-token"),
    )
    monkeypatch.setattr(
        "app.connectors.telegram.client.LiveTelegramClient", lambda bot_token: client
    )
    db_session.add(TelegramLink(user_id=owner, chat_id=555))
    await db_session.commit()

    result = await _daily_check(now_iso=NOW.isoformat())

    assert result["warnings_fired"] and result["warnings_fired"][0]["spend"] == "$0.90"
    alerts = (
        await db_session.scalars(select(Alert).where(Alert.type == "budget_warning"))
    ).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "info"  # §8.6: informational, not a hard stop
    assert [(m["chat_id"], "budget_warning" in m["text"]) for m in client.sent_messages] == [
        (555, True)
    ]

    # §17-style idempotency: same-day re-run stays quiet
    client.sent_messages.clear()
    result = await _daily_check(now_iso=NOW.isoformat())
    assert result["warnings_fired"] == []
    assert client.sent_messages == []
    assert (
        await db_session.scalar(select(func.count()).select_from(Alert).where(Alert.type == "budget_warning"))
        == 1
    )


async def test_under_budget_and_disabled_stay_quiet(db_session, monkeypatch):
    owner = await _owner_id(db_session)
    await _spend(db_session, owner, "0.10")

    client = FixtureTelegramClient()
    monkeypatch.setattr(
        "app.tasks.budget.get_settings",
        lambda: SimpleNamespace(daily_token_budget_usd=0.25, telegram_bot_token="fixture-token"),
    )
    monkeypatch.setattr(
        "app.connectors.telegram.client.LiveTelegramClient", lambda bot_token: client
    )

    result = await _daily_check(now_iso=NOW.isoformat())
    assert result["warnings_fired"] == []

    # disabled (<=0) → no check at all
    monkeypatch.setattr(
        "app.tasks.budget.get_settings",
        lambda: SimpleNamespace(daily_token_budget_usd=0.0, telegram_bot_token="fixture-token"),
    )
    result = await _daily_check(now_iso=NOW.isoformat())
    assert result == {"status": "disabled"}
    assert (await db_session.scalars(select(Alert))).all() == []


async def test_voice_extraction_logs_free_tier_usage(db_session):
    """§8.6 via the voice pipeline: extraction is an LLM call → token_usage."""
    owner = await _owner_id(db_session)
    await log_llm_usage(
        db_session,
        user_id=owner,
        call_type="voice_extraction",
        tier="free",
        model="glm-4.7-flash",
        tokens_in=420,
        tokens_out=80,
    )
    await db_session.commit()
    row = (
        await db_session.scalars(
            select(TokenUsage).where(TokenUsage.call_type == "voice_extraction")
        )
    ).one()
    assert row.tier == "free"
    assert row.cost_estimate_usd == 0  # §9.1: the free tier costs nothing
