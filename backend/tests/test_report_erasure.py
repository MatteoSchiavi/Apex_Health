"""An in-flight report must not resurrect erased source evidence."""
from tests.helpers.ai import authorized_ai_account  # noqa: F401

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.lab_assets import erase_source, source_preview
from app.core.llm import LLMResponse
from app.models.ai import AiReport
from app.models.lab import Observation
from app.models.user import User
from app.reports.periodic import upsert_periodic_report
from app.schemas.changes import ApproveIn
from app.services.evidence import record_observation
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def test_inflight_report_is_discarded_after_completed_source_erasure(db_session):
    user = User(name=f'completion-probe-{uuid4()}', timezone='UTC', locale='en')
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    await record_observation(db_session, user_id=user.id, metric='resting_hr',
        value=55, unit='bpm', origin='garmin', source_record_id='completion-probe',
        measured_at=now, fetched_at=now, timezone='UTC')
    await db_session.commit()
    from tests.helpers.ai import authorize_ai
    await authorize_ai(db_session, user.id)
    owner_id = user.id
    ready, release = asyncio.Event(), asyncio.Event()
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)

    class BlockedModel:
        async def complete(self, **kwargs):
            pack = json.loads(kwargs['messages'][0]['content'].split('Data pack (JSON):\n', 1)[1])
            observation = pack['metric_trends']['resting_hr'][0]
            ready.set()
            await release.wait()
            content = {'answer': 'Resting HR is 55 bpm.', 'claims': [{
                'evidence_id': observation['id'], 'metric': 'resting_hr', 'value': 55,
                'unit': 'bpm'}], 'limitations': []}
            return LLMResponse(content=json.dumps(content), model='fixture', tokens_in=1, tokens_out=1)

    task = asyncio.create_task(upsert_periodic_report(maker, BlockedModel(), user,
        'weekly', now.date(), now.date()))
    try:
        await asyncio.wait_for(ready.wait(), 10)
        async with maker() as session:
            principal = await session.get(User, owner_id)
            preview = await source_preview(session, owner_id, 'garmin')
            await erase_source('garmin', ApproveIn(payload_hash=preview['payload_hash']),
                session=session, user=principal)
        async with maker() as session:
            assert await session.scalar(select(Observation).where(Observation.user_id == owner_id)) is None
            assert await session.scalar(select(AiReport).where(AiReport.user_id == owner_id)) is None
    finally:
        release.set()
        await asyncio.wait_for(task, 10)
    async with maker() as session:
        report = await session.scalar(select(AiReport).where(AiReport.user_id == owner_id))
        assert report is None
