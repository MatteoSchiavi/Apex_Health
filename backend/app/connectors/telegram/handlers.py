"""Update routing (§10.2, §10.3).

Every update passes the unlinked guard FIRST — an unlinked chat is told how
to link before anything else happens (§23 Phase 3 acceptance), except for
the /link and /confirm commands that perform the linking themselves.

Handlers grow with the phase: voice + callback handlers land with the voice
pipeline, command set expands with /status /donate /report /gear, and free
text routes to the agent entrypoint. Message kinds nobody handles are logged
and dropped — never crash the polling loop.
"""

import logging

from app.connectors.telegram.link_flow import (
    confirm_link_code,
    get_linked_user_id,
    issue_link_code,
)

logger = logging.getLogger("connectors.telegram.handlers")

LINK_INSTRUCTIONS = (
    "This chat isn't linked to an account yet.\n\n"
    "1. Send /link to get a one-time code\n"
    "2. Send /confirm <code> here to finish\n\n"
    "The code expires after 15 minutes and is also printed in the server "
    "log, so it can be verified outside Telegram."
)

ALREADY_LINKED = "This chat is already linked. Nothing to do — send /status for a snapshot."

CONFIRM_USAGE = "Send /confirm <code> with the code you got from /link."

LINK_FAILED_NO_OWNER = "No owner account exists yet — bootstrap the platform first."

UNKNOWN_CODE = "That code is unknown or expired. Send /link for a fresh one."

WRONG_CHAT_CODE = "That code was issued to a different chat. Request a new one with /link here."

LINK_SUCCESS = "Linked. I'll use this chat for journal drafts, reports and alerts."

UNKNOWN_COMMAND = (
    "Unknown command. Available:\n"
    "/link — link this chat\n"
    "/confirm <code> — finish linking\n"
    "/status — integration & daily snapshot"
)

WELCOME = (
    "Apex Health bot.\n"
    "/link — link this chat to your account\n"
    "/status — integration & daily snapshot"
)


async def handle_update(ctx, update: dict) -> None:
    """Route one Telegram update. Never raises — the polling loop outlives
    any single bad update."""
    message = update.get("message")
    if message is None:
        logger.debug("update %s: no message — nothing routed", update.get("update_id"))
        return

    chat_id = message["chat"]["id"]
    text = message.get("text") or ""
    command = _command_of(text)

    # --- unlinked guard (§23 Phase 3 AC) ---
    async with ctx.sessionmaker() as session:
        linked_user_id = await get_linked_user_id(session, chat_id)
    if linked_user_id is None and command not in ("/link", "/confirm"):
        await ctx.telegram.send_message(chat_id, LINK_INSTRUCTIONS)
        return

    if "voice" in message:
        await _handle_voice(ctx, message, chat_id, linked_user_id)
        return
    if command is not None:
        await _handle_command(ctx, message, chat_id, text, linked_user_id)
        return
    if text:
        await _handle_free_text(ctx, message, chat_id, text, linked_user_id)
        return
    logger.debug("message %s: no text/voice — nothing routed", message.get("message_id"))


def _command_of(text: str) -> str | None:
    """/link@BotName extra → /link; non-commands → None."""
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lower()


async def _handle_command(ctx, message: dict, chat_id: int, text: str, user_id: int | None) -> None:
    command = _command_of(text)
    assert command is not None  # router guarantees
    arg = text.split(" ", 1)[1].strip() if " " in text else ""

    if command == "/link":
        if user_id is not None:
            await ctx.telegram.send_message(chat_id, ALREADY_LINKED)
            return
        async with ctx.sessionmaker() as session:
            code = await issue_link_code(session, ctx.redis, chat_id)
        if code is None:
            await ctx.telegram.send_message(chat_id, LINK_FAILED_NO_OWNER)
            return
        await ctx.telegram.send_message(
            chat_id,
            f"One-time code: {code}\n\nSend /confirm {code} here within 15 minutes "
            "to link this chat. The same code is printed in the server log.",
        )
        return

    if command == "/confirm":
        if user_id is not None:
            await ctx.telegram.send_message(chat_id, ALREADY_LINKED)
            return
        if not arg:
            await ctx.telegram.send_message(chat_id, CONFIRM_USAGE)
            return
        async with ctx.sessionmaker() as session:
            ok, outcome = await confirm_link_code(session, ctx.redis, chat_id, arg)
        replies = {
            "linked": LINK_SUCCESS,
            "already_linked": ALREADY_LINKED,
            "unknown_or_expired": UNKNOWN_CODE,
            "wrong_chat": WRONG_CHAT_CODE,
            "no_owner": LINK_FAILED_NO_OWNER,
        }
        await ctx.telegram.send_message(chat_id, replies[outcome])
        return

    if command == "/start":
        await ctx.telegram.send_message(chat_id, WELCOME)
        return

    await ctx.telegram.send_message(chat_id, UNKNOWN_COMMAND)


async def _handle_voice(ctx, message: dict, chat_id: int, user_id: int | None) -> None:
    """Voice pipeline hand-off — lands with the voice-pipeline commit."""
    logger.info(
        "chat %s: voice message %s received — pipeline pending",
        chat_id,
        message.get("message_id"),
    )


async def _handle_free_text(ctx, message: dict, chat_id: int, text: str, user_id: int | None) -> None:
    """Free text → agent harness — lands with the agent commit."""
    logger.info("chat %s: free text received — agent pending", chat_id)
