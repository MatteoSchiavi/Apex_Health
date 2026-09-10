"""Phase 5 foundations (§6.4 ai tables, §8.1 tools, §8.6 accounting):
ORM mapping of ai_reports/token_usage/agent_tool_calls/embeddings and
training_plans/planned_sessions; LLM tool-call parsing; token_usage cost math.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.llm import LLMError, parse_completion
from app.models.ai import AgentToolCall, AiReport, Embedding, TokenUsage
from app.models.training import PlannedSession, TrainingPlan
from app.queries.usage import (
    day_spend,
    estimate_embedding_cost_usd,
    estimate_llm_cost_usd,
    log_embedding_usage,
    log_llm_usage,
)


async def test_ai_and_training_models_round_trip(db_session):
    """All six Phase 5 tables accept and return rows (mapping matches the
    migration-0001 DDL — this is the §23-style schema guard)."""
    report = AiReport(
        user_id=1,
        report_type="daily",
        period_start=datetime(2025, 3, 9).date(),
        period_end=datetime(2025, 3, 9).date(),
        content_md=" templated summary ",
        model_used=None,  # templated daily summaries are non-LLM
        source_feature_ids=["readiness@2025-03-09", "acwr@2025-03-09"],
    )
    usage = TokenUsage(
        user_id=1,
        call_type="chat",
        tier="cheap",
        model="glm-4.7-flash",
        tokens_in=900,
        tokens_out=120,
        cached_tokens=0,
        cost_estimate_usd=Decimal("0.0015"),
    )
    tool_call = AgentToolCall(
        session_id=None,  # scheduled/report-originated calls log NULL
        tool_name="get_metric_trend",
        input_json={"metric": "acwr"},
        output_json={"rows": []},
        error=None,
        latency_ms=12,
    )
    embedding = Embedding(
        source_table="journal_entries",
        source_id=7,
        embedding=[0.1] * 1536,
        content_snippet="felt strong",
    )
    plan = TrainingPlan(user_id=1, created_by="ai", week_start=datetime(2025, 3, 10).date())
    db_session.add_all([report, usage, tool_call, embedding, plan])
    await db_session.flush()

    session_row = PlannedSession(
        training_plan_id=plan.id,
        date=datetime(2025, 3, 11).date(),
        session_type="endurance",
        target_duration_min=90,
        target_load=450,
        description="Z2",
    )
    db_session.add(session_row)
    await db_session.flush()

    loaded_plan = await db_session.get(TrainingPlan, plan.id)
    assert loaded_plan.status == "draft"  # §8.5: write tools start as drafts
    assert loaded_plan.source_ai_report_id is None
    rows = (await db_session.scalars(select(Embedding))).all()
    assert len(rows[0].embedding) == 1536
    assert (
        await db_session.scalar(select(AiReport).where(AiReport.model_used.is_(None)))
    ) is not None
    assert (await db_session.scalar(select(AgentToolCall))).session_id is None


def test_parse_completion_plain_and_tools():
    plain = parse_completion(
        {
            "model": "glm-4.7-flash",
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        fallback_model="x",
    )
    assert plain.content == "hello"
    assert not plain.wants_tools
    assert plain.cached_tokens == 0

    toolful = parse_completion(
        {
            "model": "glm-5.2",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "get_metric_trend",
                                    "arguments": '{"metric": "acwr", "start_date": "2025-03-01"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 64},
            },
        },
        fallback_model="x",
    )
    assert toolful.wants_tools
    call = toolful.tool_calls[0]
    assert call.name == "get_metric_trend"
    assert call.arguments["metric"] == "acwr"
    assert toolful.cached_tokens == 64
    assert toolful.content is None


def test_parse_completion_bad_tool_arguments_raise_llmerror():
    """Unparsable arguments surface as LLMError — the agent loop turns that
    into a tool-error result instead of crashing (§8.4)."""
    with pytest.raises(LLMError):
        parse_completion(
            {
                "model": "m",
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "c1", "function": {"name": "t", "arguments": "{not json"}}
                            ]
                        }
                    }
                ],
            },
            fallback_model="m",
        )


def test_cost_estimates_match_section_9_1_rates():
    # cheap: $1/M in, $5/M out
    assert estimate_llm_cost_usd("cheap", 1_000_000, 0) == Decimal("1.000000")
    assert estimate_llm_cost_usd("cheap", 0, 200_000) == Decimal("1.000000")
    # powerful: $1.40/$4.40, cached at $0.26
    assert estimate_llm_cost_usd("powerful", 1_000_000, 1_000_000) == Decimal("5.800000")
    cached = estimate_llm_cost_usd("powerful", 1_000_000, 0, cached_tokens=900_000)
    assert cached == Decimal(str(round(0.1 * 1.40 + 0.9 * 0.26, 6)))
    # free tier is free
    assert estimate_llm_cost_usd("free", 999_999, 999_999) == Decimal("0.000000")
    # embeddings: $0.02/M on the pinned model
    assert estimate_embedding_cost_usd(1_000_000) == Decimal("0.020000")
    # unknown tier fails closed at zero cost
    assert estimate_llm_cost_usd("mystery", 5_000_000, 5_000_000) == Decimal("0.000000")


async def test_usage_rows_and_day_spend(db_session):
    await log_llm_usage(
        db_session,
        user_id=1,
        call_type="chat",
        tier="cheap",
        model="glm-4.7-flash",
        tokens_in=1_000_000,
        tokens_out=100_000,
    )
    await log_embedding_usage(db_session, user_id=1, model="text-embedding-3-small", tokens_in=500_000)
    await db_session.flush()

    rows = (await db_session.scalars(select(TokenUsage).order_by(TokenUsage.id))).all()
    assert rows[0].call_type == "chat"
    assert rows[0].cost_estimate_usd == Decimal("1.500000")
    assert rows[1].call_type == "embedding"
    assert rows[1].tier == "free"
    assert rows[1].cost_estimate_usd == Decimal("0.010000")

    # created_at is server now(), so the rows land in "today's" UTC bucket
    now = datetime.now(UTC)
    spend = await day_spend(db_session, now)
    assert spend == Decimal("1.510000")
    # a day in the past is untouched
    assert await day_spend(db_session, datetime(2020, 1, 2, 12, 0, tzinfo=UTC)) == Decimal("0")
