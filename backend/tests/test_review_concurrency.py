"""Real concurrent transactions at canonical write and erasure boundaries."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.connectors.garmin.normalize import normalize_raw_row
from app.features.engine import compute_user_day
from app.models.features import DailyFeature
from app.models.ai import AgentToolCall
from app.models.lab import DecisionRecord, Observation
from app.models.integration import RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric
from app.services.biometric_provenance import set_biometric
from app.services.evidence import scope_lock
from app.services.decisions import daily_decision


async def waiting_on_account_lock(session, pid, task):
    for _ in range(100):
        assert not task.done(), 'Writer crossed the uncommitted account boundary'
        # Clear the monitoring snapshot so successive reads observe lock changes.
        await session.execute(text('SELECT pg_stat_clear_snapshot()'))
        event = await session.scalar(text('SELECT wait_event FROM pg_stat_activity WHERE pid=:pid'), {'pid': pid})
        if event:
            assert event.lower() == 'advisory', f'Canonical row lock taken before account lock: {event}'
            return
        await asyncio.sleep(0.02)
    raise AssertionError('Concurrent writer did not reach the account lock')


async def test_provider_writer_waits_before_reading_canonical_provenance(db_session):
    user = User(name=f'concurrent-provider-{uuid4()}', timezone='UTC')
    db_session.add(user)
    await db_session.flush()
    day = date(2026, 9, 1)
    bio = DailyBiometric(user_id=user.id, date=day)
    set_biometric(bio, 'weight_kg', 72, 'whoop')
    raw = RawIngest(user_id=user.id, source='garmin', payload_type=f'stats:{day}', raw_json={'restingHeartRate': 55})
    db_session.add_all([bio, raw])
    await db_session.commit()
    user_id, raw_id = user.id, raw.id
    await scope_lock(db_session, user_id, 'changes')
    # An uncommitted HealthKit projection must survive the subsequent import.
    set_biometric(bio, 'steps', 1000, 'apple_healthkit')
    bio.source_metrics = {**bio.source_metrics, 'apple_healthkit': {'steps': {'value': 1000}}}
    await db_session.flush()
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    started = asyncio.Queue()

    async def import_garmin():
        async with maker() as session:
            pending = await session.get(RawIngest, raw_id)
            await started.put(await session.scalar(text('SELECT pg_backend_pid()')))
            await normalize_raw_row(session, pending, ZoneInfo('UTC'), {})
            await session.commit()

    task = asyncio.create_task(import_garmin())
    try:
        await waiting_on_account_lock(db_session, await started.get(), task)
    finally:
        await db_session.commit()
        await asyncio.wait_for(task, 5)
    await db_session.refresh(bio)
    assert bio.steps == 1000 and bio.resting_hr == 55
    assert bio.source_metrics['apple_healthkit']['steps']['value'] == 1000
    assert bio.source_metrics['_canonical_sources'] == {
        'weight_kg': 'whoop', 'steps': 'apple_healthkit', 'resting_hr': 'garmin'}


async def test_recomputation_cannot_restore_erased_source_snapshot(db_session):
    user = User(name=f'concurrent-erasure-{uuid4()}', timezone='UTC')
    db_session.add(user)
    await db_session.flush()
    day = date(2026, 9, 1)
    db_session.add(DailyBiometric(user_id=user.id, date=day, resting_hr=55))
    await db_session.commit()
    owner_id = user.id
    await scope_lock(db_session, owner_id, 'changes')
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    started = asyncio.Queue()

    async def recompute():
        async with maker() as session:
            owner = await session.get(User, owner_id)
            await started.put(await session.scalar(text('SELECT pg_backend_pid()')))
            return await compute_user_day(session, owner, day)

    task = asyncio.create_task(recompute())
    try:
        await waiting_on_account_lock(db_session, await started.get(), task)
        await db_session.execute(delete(DailyBiometric).where(DailyBiometric.user_id == owner_id))
        await db_session.execute(delete(DailyFeature).where(DailyFeature.user_id == owner_id))
    finally:
        await db_session.commit()
        result = await asyncio.wait_for(task, 5)
    assert result is None
    assert await db_session.scalar(select(DailyFeature).where(DailyFeature.user_id == owner_id)) is None


async def test_daily_decision_reads_after_the_erasure_boundary(db_session):
    user = User(name=f'concurrent-decision-{uuid4()}', timezone='UTC', locale='en')
    db_session.add(user)
    await db_session.flush()
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    from app.services.evidence import record_observation
    await record_observation(db_session, user_id=user.id, metric='resting_hr', value=55,
        unit='bpm', origin='manual', source_record_id='review-rhr', measured_at=now,
        timezone='UTC', fetched_at=now, acquisition='manual')
    await db_session.commit()
    owner_id = user.id
    await scope_lock(db_session, owner_id, 'changes')
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    started = asyncio.Queue()

    async def decide():
        async with maker() as session:
            owner = await session.get(User, owner_id)
            await started.put(await session.scalar(text('SELECT pg_backend_pid()')))
            result = await daily_decision(session, owner, now=now, persist=True)
            await session.commit()
            return result

    task = asyncio.create_task(decide())
    try:
        await waiting_on_account_lock(db_session, await started.get(), task)
        await db_session.execute(delete(Observation).where(Observation.user_id == owner_id))
        await db_session.execute(delete(DecisionRecord).where(DecisionRecord.user_id == owner_id))
    finally:
        await db_session.commit()
        result = await asyncio.wait_for(task, 5)
    assert result['evidence'] == []
    assert all(change['current'] is None for change in result['key_changes'])


async def test_tool_retrieval_and_audit_cannot_cross_source_erasure(db_session):
    from tests.helpers.ai import authorize_ai
    from app.agent.loop import _execute_tool_bounded
    from app.core.llm import ToolCallRequest
    from app.services.evidence import record_observation
    user = User(name=f'concurrent-tool-{uuid4()}', timezone='UTC')
    db_session.add(user)
    await db_session.flush()
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    await record_observation(db_session, user_id=user.id, metric='resting_hr', value=55,
        unit='bpm', origin='manual', source_record_id='review-tool-rhr', measured_at=now,
        timezone='UTC', fetched_at=now, acquisition='manual')
    await db_session.commit()
    await authorize_ai(db_session, user.id)
    owner_id = user.id
    await scope_lock(db_session, owner_id, 'changes')
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    started = asyncio.Queue()

    @asynccontextmanager
    async def tracked_session():
        async with maker() as session:
            await started.put(await session.scalar(text('SELECT pg_backend_pid()')))
            yield session

    call = ToolCallRequest('review', 'data_query', {'resource': 'observations', 'metric': 'resting_hr',
        'start_date': '2026-09-01', 'end_date': '2026-09-01'})
    task = asyncio.create_task(_execute_tool_bounded(tracked_session, owner_id, now.date(), None, call))
    try:
        await waiting_on_account_lock(db_session, await started.get(), task)
        await db_session.execute(delete(Observation).where(Observation.user_id == owner_id))
        await db_session.execute(delete(AgentToolCall).where(AgentToolCall.user_id == owner_id))
    finally:
        await db_session.commit()
        result, _ = await asyncio.wait_for(task, 5)
    assert result['data'] == []
    audit = await db_session.scalar(select(AgentToolCall).where(AgentToolCall.user_id == owner_id))
    assert audit.output_json['data'] == []
