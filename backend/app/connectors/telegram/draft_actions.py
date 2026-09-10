"""Write-tool confirmation flow (MASTER_SPEC §8.5).

The agent's propose_* tools only ever create DRAFT rows; this module is the
Telegram side of §8.5: inline buttons under the bot's reply, and the
callback handlers that turn a tap into a confirmed plan / active protocol
(or a deleted draft). Only a `confirmed` plan can later sync to Technogym
(§11); confirming a supplement proposal activates it and ends the protocol
it replaces.

Callback data grammar mirrors the voice-draft flow: "<kind>:<action>:<id>".
"""

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.queries.plans import (
    confirm_plan_draft,
    confirm_supplement_draft,
    reject_plan_draft,
    reject_supplement_draft,
)

logger = logging.getLogger("connectors.telegram.drafts")


def plan_keyboard(plan_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm plan", "callback_data": f"plan:confirm:{plan_id}"},
                {"text": "❌ Discard", "callback_data": f"plan:reject:{plan_id}"},
            ]
        ]
    }


def supplement_keyboard(protocol_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Apply change", "callback_data": f"supp:confirm:{protocol_id}"},
                {"text": "❌ Discard", "callback_data": f"supp:reject:{protocol_id}"},
            ]
        ]
    }


def keyboard_for_drafts(drafts: list[dict]) -> dict | None:
    """One keyboard for the first actionable draft of the turn (multi-draft
    turns are rare; each confirm message links its own draft anyway)."""
    for draft in drafts:
        if draft["type"] == "training_plan":
            return plan_keyboard(draft["id"])
        if draft["type"] == "supplement":
            return supplement_keyboard(draft["id"])
    return None


_OUTCOMES = {
    "confirmed": "Confirmed.",
    "rejected": "Discarded.",
    "not_found": "That draft doesn't exist.",
    "not_draft": "That draft was already handled.",
}


async def handle_plan_callback(
    sessionmaker: async_sessionmaker, user_id: int, action: str, plan_id: int
) -> tuple[str, str | None]:
    """✅/❌ on a training-plan draft. Returns (callback_answer, follow_up)."""
    outcome = "not_found"
    async with sessionmaker() as session:
        if action == "confirm":
            outcome = await confirm_plan_draft(session, user_id, plan_id)
        elif action == "reject":
            outcome = await reject_plan_draft(session, user_id, plan_id)
        await session.commit()
    logger.info("plan %s %s by user %s", plan_id, outcome, user_id)
    return _OUTCOMES.get(outcome, "Unknown outcome."), (
        f"Training plan #{plan_id} confirmed — it can now sync to Technogym once "
        "access is available (§11b)."
        if outcome == "confirmed"
        else None
    )


async def handle_supplement_callback(
    sessionmaker: async_sessionmaker, user_id: int, action: str, protocol_id: int
) -> tuple[str, str | None]:
    """✅/❌ on a supplement-change draft."""
    outcome = "not_found"
    async with sessionmaker() as session:
        if action == "confirm":
            outcome = await confirm_supplement_draft(session, user_id, protocol_id)
        elif action == "reject":
            outcome = await reject_supplement_draft(session, user_id, protocol_id)
        await session.commit()
    logger.info("supplement proposal %s %s by user %s", protocol_id, outcome, user_id)
    return _OUTCOMES.get(outcome, "Unknown outcome."), (
        f"Supplement change #{protocol_id} applied."
        if outcome == "confirmed"
        else None
    )
