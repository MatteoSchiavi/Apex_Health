"""Alert push tests (§10.3, §21): committed alerts reach the linked chat;
users without a linked chat are a no-op, never a crash."""

from sqlalchemy import select

from app.connectors.telegram.alerts import notify_user, push_alert
from app.models.alert import Alert
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
)


async def _owner_id(ctx) -> int:
    async with ctx.sessionmaker() as session:
        return (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()


async def _link(ctx, user_id: int, chat_id: int) -> None:
    async with ctx.sessionmaker() as session:
        session.add(TelegramLink(user_id=user_id, chat_id=chat_id))
        await session.commit()


def _alert(user_id: int) -> Alert:
    return Alert(
        user_id=user_id,
        type="high_acwr",
        severity="warning",
        message="ACWR 1.62 — injury risk elevated",
    )


async def test_push_alert_reaches_linked_chat():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        await _link(ctx, owner, 555)
        alert = _alert(owner)
        async with ctx.sessionmaker() as session:
            session.add(alert)
            await session.commit()

        notified = await push_alert(ctx.sessionmaker, client, alert)

        assert notified == 1
        (msg,) = client.sent_messages
        assert msg["chat_id"] == 555
        assert msg["text"] == "⚠️ Alert [high_acwr] — ACWR 1.62 — injury risk elevated"


async def test_push_alert_without_linked_chat_is_noop():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        alert = _alert(owner)
        notified = await push_alert(ctx.sessionmaker, client, alert)
    assert notified == 0
    assert client.sent_messages == []


async def test_notify_user_plain_message():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        # §6.4: telegram_links PK is user_id — exactly one chat per user.
        await _link(ctx, owner, 555)
        notified = await notify_user(ctx.sessionmaker, client, owner, "Forecast looks great for Saturday.")
    assert notified == 1
    assert [m["chat_id"] for m in client.sent_messages] == [555]
