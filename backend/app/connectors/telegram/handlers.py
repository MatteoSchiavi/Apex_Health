"""Update routing (§10.2, §10.3).

Every update passes the unlinked guard FIRST — an unlinked chat is told how
to link before anything else happens (§23 Phase 3 acceptance), except for
the /link and /confirm commands that perform the linking themselves.

Free text is checked against the voice-draft edit state (✏️ Edit flow)
before falling through to the agent entrypoint. Message kinds nobody
handles are logged and dropped — the polling loop outlives any update.
"""

import logging

from app.agent.entrypoint import run_agent_turn
from app.connectors.telegram.commands import (
    cmd_donate,
    cmd_gear,
    cmd_plan,
    cmd_report,
    cmd_status,
)
from app.connectors.telegram.draft_actions import (
    handle_plan_callback,
    handle_supplement_callback,
    keyboard_for_drafts,
)
from app.connectors.telegram.link_flow import (
    confirm_link_code,
    get_linked_user_id,
    issue_link_code,
)
from app.connectors.telegram.voice import (
    apply_edit_corrections,
    confirm_draft,
    request_edit,
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
    "/status — integrations & daily snapshot\n"
    "/donate — donation & iron status\n"
    "/report — templated daily report\n"
    "/gear — gear usage vs service intervals\n"
    "/plan — today's confirmed plan sessions"
)

WELCOME = (
    "Apex Health bot.\n"
    "/link — link this chat to your account\n"
    "/status — integrations & daily snapshot"
)

# Data commands: linked chats only, read via the shared query layer (§8.2).
DATA_COMMANDS = {
    "/status": cmd_status,
    "/donate": cmd_donate,
    "/report": cmd_report,
    "/gear": cmd_gear,
    "/plan": cmd_plan,
}


async def handle_update(ctx, update: dict) -> None:
    """Route one Telegram update."""
    callback = update.get("callback_query")
    if callback is not None:
        await _handle_callback(ctx, callback)
        return

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
        await _handle_voice(ctx, message, chat_id)
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

    data_command = DATA_COMMANDS.get(command)
    if data_command is not None:
        await ctx.telegram.send_message(chat_id, await data_command(ctx, chat_id, user_id))
        return

    await ctx.telegram.send_message(chat_id, UNKNOWN_COMMAND)


async def _handle_voice(ctx, message: dict, chat_id: int) -> None:
    """Acknowledge, then hand off to background processing (§10.2)."""
    voice = message["voice"]
    logger.info(
        "chat %s: voice message %s (%ss) — dispatching pipeline",
        chat_id,
        message["message_id"],
        voice.get("duration"),
    )
    await ctx.telegram.send_message(chat_id, "Got your voice note — structuring it now…")
    await ctx.dispatch_voice(
        chat_id=chat_id,
        message_id=message["message_id"],
        voice_file_id=voice["file_id"],
        message_ts=message["date"],
    )


async def _handle_callback(ctx, callback: dict) -> None:
    """Inline button presses: voice draft ✅ Save / ✏️ Edit (§10.2) and the
    §8.5 write-tool confirmations (plan/supplement drafts)."""
    chat_id = callback["message"]["chat"]["id"]
    async with ctx.sessionmaker() as session:
        linked_user_id = await get_linked_user_id(session, chat_id)
    if linked_user_id is None:
        await ctx.telegram.send_message(chat_id, LINK_INSTRUCTIONS)
        return

    parts = (callback.get("data") or "").split(":")
    if len(parts) == 3 and parts[0] == "voice" and parts[2].isdigit():
        action, row_id = parts[1], int(parts[2])
        if action == "confirm":
            answer, follow_up = await confirm_draft(
                ctx.sessionmaker, chat_id, row_id, embeddings_client=ctx.embeddings_client()
            )
            await ctx.telegram.answer_callback_query(callback["id"], answer)
            if follow_up:
                await ctx.telegram.send_message(chat_id, follow_up)
            return
        if action == "edit":
            answer = await request_edit(ctx.redis, chat_id, row_id)
            await ctx.telegram.answer_callback_query(callback["id"], answer)
            await ctx.telegram.send_message(chat_id, answer)
            return

    if len(parts) == 3 and parts[0] in ("plan", "supp") and parts[2].isdigit():
        action, draft_id = parts[1], int(parts[2])
        if parts[0] == "plan":
            answer, follow_up = await handle_plan_callback(
                ctx.sessionmaker, linked_user_id, action, draft_id
            )
        else:
            answer, follow_up = await handle_supplement_callback(
                ctx.sessionmaker, linked_user_id, action, draft_id
            )
        await ctx.telegram.answer_callback_query(callback["id"], answer)
        if follow_up:
            await ctx.telegram.send_message(chat_id, follow_up)
        return

    await ctx.telegram.answer_callback_query(callback["id"], "Unknown action.")


async def _handle_free_text(ctx, message: dict, chat_id: int, text: str, user_id: int) -> None:
    """✏️ Edit corrections first (draft flow); everything else goes to the
    agent harness — the full §8.4 loop with tools, §9.2 routing and, when a
    write tool produced a draft this turn, the §8.5 confirm keyboard."""
    handled = await apply_edit_corrections(
        ctx.sessionmaker, ctx.redis, ctx.telegram, ctx.llm_factory, chat_id, text
    )
    if handled:
        return
    result = await run_agent_turn(
        ctx.sessionmaker,
        ctx.llm_factory(),
        user_id,
        text,
        embedding_client=ctx.embeddings_client(),
    )
    keyboard = keyboard_for_drafts(result.drafts)
    await ctx.telegram.send_message(chat_id, result.reply, reply_markup=keyboard)
