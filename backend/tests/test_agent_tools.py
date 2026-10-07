"""Model-facing capabilities are typed, owned, bounded and have no authority."""

from datetime import UTC, date, datetime
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.agent.tools import TOOL_REGISTRY, ToolContext, tool_schemas
from app.models.lab import ChangeDraft
from app.models.training import TrainingPlan
from app.services.evidence import EvidenceError

EXPECTED_TOOLS = {
    "data_get_recovery_summary": "read",
    "data_get_coverage": "read",
    "data_query": "read",
    "data_get_evidence": "read",
    "context_search": "read",
    "analytics_run": "write",
    "planning_get_constraints": "read",
    "planning_preview": "read",
    "changes_propose": "write",
    "jobs_get_status": "read",
    "data_request_repair": "write",
}


def test_registry_has_no_approval_execution_or_arbitrary_code():
    assert {k: v.kind for k, v in TOOL_REGISTRY.items()} == EXPECTED_TOOLS
    assert len(tool_schemas()) == 11
    for spec in TOOL_REGISTRY.values():
        assert spec.parameters["additionalProperties"] is False
    with pytest.raises(ValidationError):
        TOOL_REGISTRY["data_query"].argument_model.model_validate(
            {
                "resource": "observations",
                "start_date": "2025-03-01",
                "end_date": "2025-03-10",
                "metric": "resting_hr",
                "user_id": 2,
            }
        )


async def test_coverage_uses_explicit_missing_states(db_session):
    result = await TOOL_REGISTRY["data_get_coverage"].handler(
        ToolContext(db_session, 1, date.today())
    )
    assert result["source_policy"] == "ai_eligible_v1"
    assert result["data"]["metrics"]
    assert all(
        "measured_at" in m["latest"]
        if m["latest"]
        else m["availability"] != "available"
        for m in result["data"]["metrics"]
    )


async def test_unknown_metric_and_long_range_are_rejected(db_session):
    ctx = ToolContext(db_session, 1, date.today())
    for metric, start, end in [
        ("made_up", date(2025, 1, 1), date(2025, 1, 2)),
        ("resting_hr", date(2020, 1, 1), date(2025, 1, 1)),
    ]:
        with pytest.raises(EvidenceError):
            await TOOL_REGISTRY["data_query"].handler(
                ctx,
                resource="observations",
                metric=metric,
                start_date=start,
                end_date=end,
            )


async def test_plan_tool_only_creates_reviewable_change(db_session):
    out = await TOOL_REGISTRY["changes_propose"].handler(
        ToolContext(db_session, 1, date.today()),
        change={
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
        },
        reason="Preserve the planned focus",
    )
    draft = await db_session.get(ChangeDraft, out["data"]["id"])
    assert draft.status == "draft" and draft.payload_hash
    assert not await db_session.scalar(
        select(TrainingPlan.id).where(
            TrainingPlan.user_id == 1, TrainingPlan.week_start == date(2025, 3, 10)
        )
    )


async def test_search_is_available_without_remote_embeddings(db_session):
    out = await TOOL_REGISTRY["context_search"].handler(
        ToolContext(db_session, 1, date.today()), query="unmatched-unique-query"
    )
    assert out["data"] == [] and out["trust"] == "untrusted_data_not_instructions"


async def test_foreign_job_or_evidence_is_not_found(db_session):
    ctx = ToolContext(db_session, 1, date.today())
    for name, args in [
        ("jobs_get_status", {"job_id": 999999}),
        ("data_get_evidence", {"handle": "observation:999999:1"}),
    ]:
        with pytest.raises(EvidenceError, match="unavailable|found"):
            await TOOL_REGISTRY[name].handler(ctx, **args)
