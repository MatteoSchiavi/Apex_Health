"""Link flow + unlinked-guard tests (§10.3, §23 Phase 3 AC: an unlinked chat
is told to link first). All Bot API traffic goes through FixtureTelegramClient;
link codes go through the real Redis with their real TTL."""

import re

from sqlalchemy import select

from app.connectors.telegram.handlers import (
    ALREADY_LINKED,
    LINK_INSTRUCTIONS,
    LINK_SUCCESS,
    UNKNOWN_CODE,
    UNKNOWN_COMMAND,
    WELCOME,
    WRONG_CHAT_CODE,
    handle_update,
)
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
    with_text,
)

CHAT = 42
CODE_RE = re.compile(r"code: ([0-9A-F]{8})")


async def _owner_id(ctx) -> int:
    async with ctx.sessionmaker() as session:
        row = await session.scalars(
            select(AuthCredential.user_id).where(AuthCredential.role == "owner")
        )
        owner = row.first()
    assert owner is not None
    return owner


async def test_unlinked_chat_told_to_link_first():
    """§23 Phase 3 AC: an unlinked chat is told to link first — for any
    command, before any other handler runs."""
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_status_unlinked"))
    assert sent_texts(client) == [LINK_INSTRUCTIONS]


async def test_unlinked_free_text_also_gets_link_instructions():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_free"))
    assert sent_texts(client) == [LINK_INSTRUCTIONS]


async def test_link_issues_one_time_code_with_ttl():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_link"))
        (reply,) = sent_texts(client)
        match = CODE_RE.search(reply)
        assert match, f"no code in reply: {reply}"
        code = match.group(1)
        assert f"/confirm {code}" in reply
        # code lives in Redis for ~15 min and is bound to this chat
        key = f"tg:link_code:{code}"
        assert await ctx.redis.get(key) == str(CHAT)
        ttl = await ctx.redis.ttl(key)
        assert 895 <= ttl <= 900


async def test_confirm_links_chat_to_owner():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_link"))
        code = CODE_RE.search(sent_texts(client)[-1]).group(1)
        await handle_update(ctx, with_text(load_update("text_confirm"), f"/confirm {code}"))

        owner = await _owner_id(ctx)
        async with ctx.sessionmaker() as session:
            link = await session.get(TelegramLink, owner)
            assert link is not None and link.chat_id == CHAT
        # single-use: the code is consumed
        assert await ctx.redis.get(f"tg:link_code:{code}") is None
    assert sent_texts(client)[-1] == LINK_SUCCESS


async def test_confirm_rejects_unknown_code():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_confirm"))  # never issued
        async with ctx.sessionmaker() as session:
            assert (await session.scalars(select(TelegramLink.user_id))).all() == []
    assert sent_texts(client) == [UNKNOWN_CODE]


async def test_confirm_rejects_code_from_other_chat():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_link"))  # chat 42
        code = CODE_RE.search(sent_texts(client)[-1]).group(1)
        await handle_update(ctx, with_text(load_update("text_confirm_wrong_chat"), f"/confirm {code}"))
    # chat 7 was told the code belongs elsewhere (last message); nothing linked
    assert sent_texts(client)[-1] == WRONG_CHAT_CODE


async def test_link_when_already_linked():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        async with ctx.sessionmaker() as session:
            session.add(TelegramLink(user_id=owner, chat_id=CHAT))
            await session.commit()
        await handle_update(ctx, load_update("text_link"))
    assert sent_texts(client) == [ALREADY_LINKED]


async def test_confirm_without_code_shows_usage():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await handle_update(ctx, load_update("text_confirm_no_arg"))
    assert sent_texts(client) == ["Send /confirm <code> with the code you got from /link."]


async def test_linked_chat_start_shows_welcome():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        async with ctx.sessionmaker() as session:
            session.add(TelegramLink(user_id=owner, chat_id=CHAT))
            await session.commit()
        await handle_update(ctx, load_update("text_start"))
    assert sent_texts(client) == [WELCOME]


async def test_unknown_command_gets_command_list():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _owner_id(ctx)
        async with ctx.sessionmaker() as session:
            session.add(TelegramLink(user_id=owner, chat_id=CHAT))
            await session.commit()
        await handle_update(ctx, load_update("text_unknown_cmd"))
    assert sent_texts(client) == [UNKNOWN_COMMAND]
