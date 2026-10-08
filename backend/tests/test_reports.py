"""Report tests (§9.2, §19, Phase 5): templated daily summaries persist as
ai_reports with model_used=NULL (no LLM); weekly/monthly reports run the
POWERFUL tier over a §8.2 data pack (query calls audited with session_id
NULL), and are idempotent per period."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.db import sessionmaker as app_sessionmaker
from app.core.llm import LLMResponse
from app.core.config import get_settings
from app.models.activity import Activity, Discipline
from app.models.ai import AgentToolCall, AiReport, Embedding
from app.models.features import DailyFeature
from app.models.user import AuthCredential
from app.reports.daily import build_daily_summary, upsert_daily_report
from app.reports.periodic import upsert_periodic_report
from app.tasks.ai_reports import _dispatch_daily, _dispatch_periodic
from tests.helpers.ai import FixtureAgentLLMClient, FixtureEmbeddingClient
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def _isolate_report_tables():
    """Report/audit tables persist across tests in this session-scoped DB —
    start each report test clean."""
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE lab_observations, lab_feed_states, ai_reports, agent_tool_calls, token_usage "
                "RESTART IDENTITY CASCADE"
            )
        )
    await engine.dispose()




async def _owner_id(db_session) -> int:
    return (
        await db_session.scalars(
            select(AuthCredential.user_id).where(AuthCredential.role == "owner")
        )
    ).first()


async def _seed_user_and_data(db_session, owner: int) -> None:
    """Idempotent: the (user, date) PK makes a double seed impossible."""
    existing = await db_session.scalar(
        select(func.count()).select_from(DailyFeature).where(
            DailyFeature.user_id == owner, DailyFeature.date == datetime(2025, 3, 9).date()
        )
    )
    from app.services.evidence import record_observation
    await record_observation(db_session,user_id=owner,metric="resting_hr",value=52,unit="bpm",origin="garmin",source_record_id="report-test",measured_at=datetime(2025,3,9,6,tzinfo=UTC),fetched_at=datetime(2025,3,9,8,tzinfo=UTC),timezone="Europe/Rome")
    if existing:
        await db_session.commit()
        return
    db_session.add_all(
        [
            DailyFeature(
                user_id=owner,
                date=datetime(2025, 3, 9).date(),
                readiness_score=71.0,
                recovery_score=78.0,
                strain_score=12.4,
                training_load_acute=812.0,
                training_load_chronic=670.0,
                acwr=1.21,
                sleep_architecture_score=64.0,
                hrv_deviation_from_baseline=-3.2,
                data_completeness="full",
            )
        ]
    )
    await db_session.commit()


async def _user(db_session, user_id: int):
    from app.models.user import User

    return await db_session.get(User, user_id)


async def test_daily_summary_is_templated_and_persisted(db_session):
    """Templated daily summary: ai_reports row with model_used NULL (§6.4:
    NULL = non-LLM), metric audit ids, idempotent upsert."""
    owner = await _owner_id(db_session)
    await _seed_user_and_data(db_session, owner)
    user = await _user(db_session, owner)
    # An earlier profile test can select Italian for this shared owner.
    # This scenario explicitly verifies the English template.
    user.locale = "en"
    await db_session.commit()
    day = datetime(2025, 3, 9).date()

    summary = await build_daily_summary(db_session, user, day)
    assert summary is not None
    assert "Readiness 71" in summary.content_md
    assert "ACWR 1.21" in summary.content_md
    assert "readiness@2025-03-09" in summary.source_feature_ids

    row = await upsert_daily_report(app_sessionmaker, user, day)
    assert row.model_used is None  # §6.4: templated rows are non-LLM
    assert row.report_type == "daily"
    refreshed = await upsert_daily_report(app_sessionmaker, user, day)  # re-run
    assert refreshed.id == row.id  # §17: refreshed, not duplicated
    count = await db_session.scalar(
        select(func.count()).select_from(AiReport).where(AiReport.report_type == "daily")
    )
    assert count == 1


async def test_italian_daily_summary_keeps_measurements_and_translates_template(db_session):
    owner = await _owner_id(db_session)
    await _seed_user_and_data(db_session, owner)
    user = await _user(db_session, owner)
    user.locale = "it"
    summary = await build_daily_summary(db_session, user, datetime(2025, 3, 9).date())
    assert "Report giornaliero" in summary.content_md
    assert "Prontezza 71" in summary.content_md and "Recupero" in summary.content_md
    assert "ACWR 1.21" in summary.content_md
    assert "Training:" not in summary.content_md


async def test_daily_summary_without_features_returns_none(db_session):
    owner = await _owner_id(db_session)
    user = await _user(db_session, owner)
    assert await build_daily_summary(db_session, user, datetime(2030, 1, 1).date()) is None


async def test_daily_summary_task_dispatch(db_session):
    owner = await _owner_id(db_session)
    await _seed_user_and_data(db_session, owner)
    # 03:45 Rome on 2025-03-10 → summarizes the prior local day 2025-03-09
    result = await _dispatch_daily(now_iso="2025-03-10T02:45:00+00:00")
    assert result[str(owner)].startswith("daily:2025-03-09")
    rows = (await db_session.scalars(select(AiReport))).all()
    assert len(rows) == 1 and rows[0].model_used is None


async def test_weekly_report_powerful_tier_and_audit(db_session, monkeypatch):
    """§23: reports are batch artifacts — powerful tier, audited data pack,
    one token_usage row, and idempotent persistence."""
    owner = await _owner_id(db_session)
    await _seed_user_and_data(db_session, owner)

    discipline_id = await db_session.scalar(
        select(Discipline.id).where(Discipline.name == "road_cycling")
    )  # seeded by migration 0002
    db_session.add(
        Activity(
            user_id=owner,
            discipline_id=discipline_id,
            start_time=datetime(2025, 3, 5, 8, 0, tzinfo=UTC),
            start_tz_offset_minutes=60,
            local_date=datetime(2025, 3, 5).date(),
            duration_s=7200,
            distance_m=48000,
            training_load=310,
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        "app.core.llm.get_settings",
        lambda: SimpleNamespace(glm_api_key="fixture", glm_api_base="http://x", llm_provider_cheap="c", llm_provider_powerful="p"),
    )
    llm = FixtureAgentLLMClient(
        [LLMResponse(content=json.dumps({"answer": "The recorded observations were reviewed.", "claims": [], "limitations": ["No causal assessment."]}), model="glm-5.2", tokens_in=4000, tokens_out=900)]
    )

    start = datetime(2025, 3, 3).date()
    end = datetime(2025, 3, 9).date()
    row = await upsert_periodic_report(app_sessionmaker, llm, await _user(db_session, owner), "weekly", start, end)

    assert row is not None and row.model_used == "glm-5.2"
    assert row.content_md == "The recorded observations were reviewed."
    assert row.source_feature_ids  # actual evidence and snapshot ids recorded
    assert llm.calls[0]["tier"] == "powerful"  # §9.2: hardcoded, never classified

    tool_calls = (await db_session.scalars(select(AgentToolCall))).all()
    assert {t.tool_name for t in tool_calls} == {"data_query"}
    assert all(t.session_id is None for t in tool_calls)  # §6.4: non-chat callers

    usage = (
        await db_session.scalars(select(AiReport).where(AiReport.report_type == "weekly"))
    ).one()
    assert usage.model_used == "glm-5.2"

    # idempotent re-run: no second row, no second LLM call
    before = len(llm.calls)
    again = await upsert_periodic_report(app_sessionmaker, llm, await _user(db_session, owner), "weekly", start, end)
    assert again.id == row.id and len(llm.calls) == before


async def test_weekly_task_dispatch_persists_report(db_session, monkeypatch):
    """The §19 weekly dispatch (Monday 06:00 local) persists a report."""
    owner = await _owner_id(db_session)
    await _seed_user_and_data(db_session, owner)

    embeddings = FixtureEmbeddingClient()
    task_settings = get_settings().model_copy(update={"glm_api_key": "", "deepseek_api_key": "fixture", "llm_provider_powerful": "", "llm_api_base_powerful": "", "llm_api_key_powerful": ""})
    monkeypatch.setattr(
        "app.tasks.ai_reports.get_settings",
        lambda: task_settings,
    )
    monkeypatch.setattr("app.core.embeddings.build_embedding_client", lambda: embeddings)
    await db_session.commit()

    # inject the fixture LLM as the production client for the task
    llm = FixtureAgentLLMClient(
        [LLMResponse(content=json.dumps({"answer": "The recorded observations were reviewed.", "claims": [], "limitations": []}), model="glm-5.2", tokens_in=3000, tokens_out=700)]
    )
    monkeypatch.setattr(
        "app.core.llm.build_llm_client", lambda: llm
    )

    # Monday 2025-03-10 06:00 Rome = 05:00 UTC; period = Mon 03-03 .. Sun 03-09
    result = await _dispatch_periodic("weekly", now_iso="2025-03-10T05:00:00+00:00")
    assert result[str(owner)] == "weekly:2025-03-03"
    assert llm.closed

    # the report content was embedded into the search corpus (§6.2/§8.3)
    report_rows = (await db_session.scalars(select(Embedding))).all()
    assert report_rows == []  # Private lexical context search does not need remote embeddings.

    # monthly on the 1st: 2025-04-01 06:00 Rome = 04:00 UTC → March
    llm2 = FixtureAgentLLMClient(
        [LLMResponse(content=json.dumps({"answer": "The recorded observations were reviewed.", "claims": [], "limitations": []}), model="glm-5.2", tokens_in=6000, tokens_out=1200)]
    )
    monkeypatch.setattr("app.core.llm.build_llm_client", lambda: llm2)
    result = await _dispatch_periodic("monthly", now_iso="2025-04-01T04:00:00+00:00")
    assert result[str(owner)] == "monthly:2025-03-01"
    rows = (
        await db_session.scalars(select(AiReport).where(AiReport.report_type == "monthly"))
    ).all()
    assert len(rows) == 1
    assert rows[0].period_end == datetime(2025, 3, 31).date()
