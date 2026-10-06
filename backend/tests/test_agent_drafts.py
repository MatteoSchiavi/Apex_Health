"""End-to-end agent proposals never become approval or device delivery."""

from sqlalchemy import select
from datetime import UTC, datetime
from app.agent.entrypoint import run_agent_turn
from app.core.llm import LLMResponse, ToolCallRequest
from app.models.lab import ChangeDraft
from app.models.training import TrainingPlan
from app.services.changes import apply, reject, undo
from tests.helpers.ai import FixtureAgentLLMClient
from contextlib import asynccontextmanager
from types import SimpleNamespace
from app.core.db import sessionmaker
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401

NOW = datetime(2025, 3, 10, 8, tzinfo=UTC)


@asynccontextmanager
async def _test_context(ctx):
    yield ctx


def proposal(kind="plan_create"):
    change = (
        {
            "kind": "plan_create",
            "week_start": "2025-03-10",
            "sessions": [
                {
                    "date": "2025-03-11",
                    "discipline": "road_cycling",
                    "session_type": "easy",
                    "target_duration_min": 30,
                    "description": "Easy ride",
                }
            ],
        }
        if kind == "plan_create"
        else {
            "kind": "journal_create",
            "date": "2025-03-10",
            "notes": "Reported fatigue",
            "tags": [],
        }
    )
    return LLMResponse(
        content=None,
        model="fixture",
        tool_calls=[
            ToolCallRequest(
                id="c1",
                name="changes_propose",
                arguments={
                    "change": change,
                    "reason": "Review a small adjustment",
                    "evidence_ids": [],
                },
            )
        ],
    )


async def draft_turn(ctx, kind="plan_create"):
    llm = FixtureAgentLLMClient(
        [
            proposal(kind),
            LLMResponse(
                model="fixture",
                content="A draft is ready for review in the application.",
            ),
        ]
    )
    from app.models.user import AuthCredential

    async with ctx.sessionmaker() as session:
        owner = await session.scalar(
            select(AuthCredential.user_id).where(AuthCredential.role == "owner")
        )
    result = await run_agent_turn(
        ctx.sessionmaker, llm, owner, "draft a change", now=NOW, tier="cheap"
    )
    assert result.drafts
    return owner, result


async def test_plan_is_reviewed_in_app_then_applied_once():
    ctx = SimpleNamespace(sessionmaker=sessionmaker)
    async with _test_context(ctx):
        owner, result = await draft_turn(ctx)
        async with ctx.sessionmaker() as session:
            row = await session.get(ChangeDraft, result.drafts[0]["id"])
            assert row.status == "draft"
            assert not await session.scalar(
                select(TrainingPlan.id).where(TrainingPlan.user_id == owner)
            )
            first = await apply(session, owner, row.id, row.payload_hash, now=NOW)
            await session.commit()
            second = await apply(session, owner, row.id, row.payload_hash, now=NOW)
            assert first["receipt"] == second["receipt"]
            assert first["receipt"]["external_delivery"] == "not_requested"
            assert (
                await session.get(TrainingPlan, first["receipt"]["target_id"])
            ).status == "confirmed"


async def test_rejected_model_proposal_never_creates_plan():
    ctx = SimpleNamespace(sessionmaker=sessionmaker)
    async with _test_context(ctx):
        owner, result = await draft_turn(ctx)
        async with ctx.sessionmaker() as session:
            ident = result.drafts[0]["id"]
            await reject(session, owner, ident)
            await session.commit()
            assert (await session.get(ChangeDraft, ident)).status == "rejected"
            assert not await session.scalar(
                select(TrainingPlan.id).where(TrainingPlan.user_id == owner)
            )


async def test_journal_proposal_waits_for_exact_approval_and_can_undo():
    ctx = SimpleNamespace(sessionmaker=sessionmaker)
    async with _test_context(ctx):
        owner, result = await draft_turn(ctx, "journal_create")
        async with ctx.sessionmaker() as session:
            row = await session.get(ChangeDraft, result.drafts[0]["id"])
            applied = await apply(session, owner, row.id, row.payload_hash, now=NOW)
            await session.commit()
            from app.models.journal import JournalEntry

            assert (
                await session.get(JournalEntry, applied["receipt"]["target_id"])
            ).free_text_notes == "Reported fatigue"
            await undo(session, owner, row.id)
            await session.commit()
            assert not await session.get(JournalEntry, applied["receipt"]["target_id"])
