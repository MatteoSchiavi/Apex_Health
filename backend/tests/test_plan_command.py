"""/plan command tests (§10.3, §11b fallback — Phase 6).

'/plan today' is the documented fallback delivery path: the confirmed plan
reaches the user in Telegram while prescription-push (sync_plan_to_technogym)
awaits the real Technogym access tier (§24). Draft plans must NOT show up.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.connectors.telegram.handlers import handle_update
from app.models.telegram import TelegramLink
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
)

CHAT = 42  # the recorded updates.json chat
ROME = ZoneInfo("Europe/Rome")  # owner accounts default to Europe/Rome


async def _link_chat(ctx, chat_id: int) -> int:
    async with ctx.sessionmaker() as session:
        owner = (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()
        session.add(TelegramLink(user_id=owner, chat_id=chat_id))
        await session.commit()
    return owner


async def _seed_plan(ctx, owner: int, status: str, *, today: date) -> int:
    async with ctx.sessionmaker() as session:
        plan = TrainingPlan(
            user_id=owner,
            created_by="ai",
            week_start=today - timedelta(days=today.weekday()),
            status=status,
        )
        session.add(plan)
        await session.flush()
        session.add(
            PlannedSession(
                training_plan_id=plan.id,
                date=today,
                session_type="easy aerobic",
                target_duration_min=45,
                target_load=35.0,
                description="Z2 treadmill, cadence work",
            )
        )
        await session.commit()
        return plan.id


async def test_plan_today_shows_confirmed_sessions():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)

        # the command reads "today" in the owner's local tz (§17) — match it
        real_today = datetime.now(ROME).date()
        await _seed_plan(ctx, owner, "confirmed", today=real_today)

        await handle_update(ctx, load_update("text_plan_today"))

        body = sent_texts(client)[0]
        assert f"Plan for today — {real_today.isoformat()}" in body
        assert "easy aerobic" in body
        assert "45 min" in body
        assert "Z2 treadmill, cadence work" in body
        assert "§11b" in body  # documented fallback notice
        assert "§24" in body


async def test_plan_today_ignores_draft_plans():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        real_today = datetime.now(ROME).date()
        await _seed_plan(ctx, owner, "draft", today=real_today)

        await handle_update(ctx, load_update("text_plan_today"))

        body = sent_texts(client)[0]
        assert body.startswith("No confirmed plan sessions for today.")


async def test_plan_today_without_any_plan():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        await handle_update(ctx, load_update("text_plan_today"))
        body = sent_texts(client)[0]
        assert "No confirmed plan sessions" in body
