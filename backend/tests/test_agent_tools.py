"""Tool registry tests (§8.3): all 11 tools exist with schemas, read tools
return data through the shared query layer, write tools create DRAFTS only
(§8.5), and sync_plan_to_technogym enforces its preconditions (§11)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.agent.tools import TOOL_REGISTRY, ToolContext, tool_schemas

from app.models.features import DailyFeature
from app.models.gear import Gear
from app.models.medical import SupplementProtocol
from app.models.training import PlannedSession, TrainingPlan
from app.queries.plans import confirm_plan_draft


EXPECTED_TOOLS = {
    "get_metric_trend": "read",
    "get_lab_trend": "read",
    "get_activity_summary": "read",
    "get_journal_entries": "read",
    "search_context": "read",
    "get_training_plan": "read",
    "get_donation_status": "read",
    "get_gear_status": "read",
    "propose_training_plan": "write",
    "propose_supplement_change": "write",
    "sync_plan_to_technogym": "write",
    # coach tools (owner feature batch, 2026-09)
    "get_upcoming_events": "read",
    "update_context_doc": "write",
    "get_gym_day": "read",
}


def test_registry_matches_section_8_3():
    assert set(TOOL_REGISTRY) == set(EXPECTED_TOOLS)
    for name, kind in EXPECTED_TOOLS.items():
        assert TOOL_REGISTRY[name].kind == kind
    schemas = tool_schemas()
    assert len(schemas) == 14
    by_name = {s["function"]["name"]: s for s in schemas}
    assert by_name["get_metric_trend"]["function"]["parameters"]["required"] == [
        "metric",
        "start_date",
        "end_date",
    ]


async def _ctx(db_session, user_id=1, today=None) -> ToolContext:
    return ToolContext(session=db_session, user_id=user_id, today=today or datetime.now(UTC).date())


async def test_get_metric_trend_returns_rows(db_session):
    db_session.add(
        DailyFeature(
            user_id=1,
            date=datetime(2025, 3, 9).date(),
            readiness_score=71.0,
            acwr=1.21,
            data_completeness="full",
        )
    )
    await db_session.flush()
    ctx = await _ctx(db_session)
    out = await TOOL_REGISTRY["get_metric_trend"].handler(
        ctx, metric="acwr", start_date="2025-03-01", end_date="2025-03-10"
    )
    assert out["rows"] == [{"date": "2025-03-09", "metric": "acwr", "value": 1.21}]

    with pytest.raises(ValueError, match="unknown metric"):
        await TOOL_REGISTRY["get_metric_trend"].handler(
            ctx, metric="nonsense", start_date="2025-03-01", end_date="2025-03-10"
        )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await TOOL_REGISTRY["get_metric_trend"].handler(
            ctx, metric="acwr", start_date="03/01/2025", end_date="2025-03-10"
        )


async def test_get_gear_status_filters_by_id(db_session):
    db_session.add_all(
        [
            Gear(user_id=1, name="Bike A", gear_type="bike", active=True, km_since_service=900),
            Gear(user_id=1, name="Bike B", gear_type="bike", active=True, km_since_service=100),
        ]
    )
    await db_session.flush()
    ctx = await _ctx(db_session)
    everything = await TOOL_REGISTRY["get_gear_status"].handler(ctx)
    assert len(everything["items"]) == 2
    one = await TOOL_REGISTRY["get_gear_status"].handler(ctx, gear_id=everything["items"][0]["gear_id"])
    assert one["items"][0]["name"] == "Bike A"


async def test_propose_training_plan_creates_draft_with_resolved_discipline(db_session):
    # 'road_cycling' comes from the migration-0002 seed — no insert needed.
    ctx = await _ctx(db_session)
    out = await TOOL_REGISTRY["propose_training_plan"].handler(
        ctx,
        week_start="2025-03-12",  # Wednesday — snaps to Monday 2025-03-10
        sessions=[
            {"date": "2025-03-11", "discipline": "road_cycling", "session_type": "endurance",
             "target_duration_min": 90, "target_load": 450},
            {"date": "2025-03-13", "session_type": "rest"},
        ],
    )
    assert out["status"] == "draft"
    plan = await db_session.get(TrainingPlan, out["plan_id"])
    assert plan.created_by == "ai"
    assert plan.week_start == datetime(2025, 3, 10).date()  # Monday snap
    sessions = (
        await db_session.scalars(
            select(PlannedSession).where(PlannedSession.training_plan_id == plan.id)
        )
    ).all()
    assert sessions[0].discipline_id is not None
    assert sessions[1].discipline_id is None

    with pytest.raises(ValueError, match="unknown discipline slug"):
        await TOOL_REGISTRY["propose_training_plan"].handler(
            ctx, week_start="2025-03-10", sessions=[{"date": "2025-03-11", "discipline": "quidditch"}]
        )


async def test_propose_supplement_change_is_inactive_draft(db_session):
    ctx = await _ctx(db_session)
    out = await TOOL_REGISTRY["propose_supplement_change"].handler(
        ctx, supplement_name="Iron", dose="25 mg", reason="ferritin 22"
    )
    row = await db_session.get(SupplementProtocol, out["protocol_id"])
    assert row.active is False  # the draft marker (§8.5)
    assert row.reason == "ferritin 22"


async def test_sync_plan_to_technogym_preconditions(db_session):
    ctx = await _ctx(db_session)
    # foreign/missing plan
    assert (await TOOL_REGISTRY["sync_plan_to_technogym"].handler(ctx, training_plan_id=999))[
        "error"
    ] == "plan not found for this account"
    # draft plan refuses
    plan = TrainingPlan(user_id=1, created_by="ai", week_start=datetime(2025, 3, 10).date())
    db_session.add(plan)
    await db_session.flush()
    assert "draft" in (
        await TOOL_REGISTRY["sync_plan_to_technogym"].handler(ctx, training_plan_id=plan.id)
    )["error"]
    # confirmed plan → §11b fallback (access tier unconfirmed, §24)
    await confirm_plan_draft(db_session, user_id=1, plan_id=plan.id)
    out = await TOOL_REGISTRY["sync_plan_to_technogym"].handler(ctx, training_plan_id=plan.id)
    assert out["status"] == "pending_technogym_access"
