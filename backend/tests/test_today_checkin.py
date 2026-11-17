"""On-open quota, local noon/DST, evidence grounding and erasure."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.db import sessionmaker
from app.core.llm import LLMResponse
from app.models.user import User
from app.reports.checkin import checkin_period, compact_answer, open_checkin
from app.services.evidence import record_observation
from tests.helpers.ai import authorized_ai_account  # noqa: F401
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture
async def checkin_data(db_session):
    user = await db_session.get(User, 1)
    user.timezone, user.locale = 'Europe/Rome', 'en'
    now = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
    await record_observation(db_session, user_id=1, metric='resting_hr', value=52, unit='bpm', origin='garmin',
        source_record_id='checkin-test', measured_at=now-timedelta(days=1), fetched_at=now, timezone='Europe/Rome')
    await db_session.commit()
    calls = []
    async def complete(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(.03)
        return LLMResponse(content=json.dumps({'answer': "Today's data is incomplete.\nThe week's coverage is sparse.\nSync your watch before deciding on intensity.", 'claims': [], 'limitations': []}), model='fixture', tokens_in=300, tokens_out=50)
    return now, SimpleNamespace(complete=complete), calls


def test_noon_slots_and_local_midnight_with_dst():
    assert checkin_period(datetime(2026, 11, 16, 10, 59, tzinfo=UTC), 'Europe/Rome')[1] == 'morning'
    assert checkin_period(datetime(2026, 11, 16, 11, 0, tzinfo=UTC), 'Europe/Rome')[1] == 'afternoon'
    assert checkin_period(datetime(2026, 7, 16, 10, 0, tzinfo=UTC), 'Europe/Rome')[1] == 'afternoon'
    assert str(checkin_period(datetime(2026, 11, 16, 23, 0, tzinfo=UTC), 'Europe/Rome')[0]) == '2026-11-17'


async def test_concurrent_opens_one_call_per_slot_and_no_catchup(checkin_data, db_session):
    now, llm, calls = checkin_data
    results = await asyncio.gather(*(open_checkin(sessionmaker, 1, now=now, llm=llm) for _ in range(4)))
    assert len(calls) == 1
    assert any(r['status'] == 'ready' and len(r['lines']) == 3 for r in results)
    cached = await open_checkin(sessionmaker, 1, now=now+timedelta(minutes=10), llm=llm)
    assert cached['status'] == 'ready' and len(calls) == 1
    afternoon = await open_checkin(sessionmaker, 1, now=now.replace(hour=17), llm=llm)
    assert afternoon['status'] == 'ready' and len(calls) == 2
    await open_checkin(sessionmaker, 1, now=now.replace(hour=20), llm=llm)
    assert len(calls) == 2 and calls[0]['tier'] == 'cheap' and calls[0]['max_tokens'] == 650
    assert await db_session.scalar(text('SELECT count(*) FROM today_checkins')) == 2
    assert await db_session.scalar(text("SELECT count(*) FROM token_usage WHERE call_type='today_checkin'")) == 2


async def test_timeout_consumes_slot_without_retry(checkin_data, db_session):
    now, _, calls = checkin_data
    async def failing(**kwargs):
        calls.append(kwargs)
        raise TimeoutError('private-provider-body')
    llm = SimpleNamespace(complete=failing)
    result = await open_checkin(sessionmaker, 1, now=now, llm=llm)
    assert result['status'] == 'ready' and result['mode'] == 'recorded' and len(result['lines']) == 3
    assert result['reason'] == 'provider' and 'private' not in str(result)
    await open_checkin(sessionmaker, 1, now=now, llm=llm)
    assert len(calls) == 1


async def test_consent_and_empty_data_do_not_invoke(checkin_data, db_session):
    now, llm, calls = checkin_data
    await db_session.execute(text('UPDATE ai_consents SET active=false WHERE user_id=1'))
    await db_session.commit()
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['status'] == 'ai_disabled'
    assert calls == []
    await db_session.execute(text('UPDATE ai_consents SET active=true WHERE user_id=1'))
    await db_session.execute(text('DELETE FROM lab_observations WHERE user_id=1'))
    await db_session.commit()
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['status'] == 'no_data'
    assert calls == []


async def test_erasure_scrubs_content_but_retains_quota(checkin_data, db_session):
    now, llm, calls = checkin_data
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['status'] == 'ready'
    from app.services.derived_data import clear_derived_health_data
    await clear_derived_health_data(db_session, 1)
    await db_session.commit()
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['lines'] == []
    assert len(calls) == 1
    assert await db_session.scalar(text('SELECT content FROM today_checkins WHERE user_id=1')) is None


def test_invalid_or_long_output_is_not_published():
    assert compact_answer(json.dumps({'answer':'a\nb\nc\nd','claims':[]}), {}, 'en') == 'a\nb\nc d'
    assert compact_answer(json.dumps({'answer':'Resting HR 99 bpm','claims':[]}), {}, 'en') is None
    assert len(compact_answer(json.dumps({'answer':'x'*181,'claims':[]}), {}, 'en')) <= 180


async def test_legacy_scheduler_is_noop():
    from app.tasks.ai_reports import _dispatch_daily
    from app.tasks.celery_app import celery_app
    assert await _dispatch_daily() == {'status': 'on_open_only'}
    assert not any(v['task'] == 'reports.daily_summary' for v in celery_app.conf.beat_schedule.values())


async def test_other_account_and_disabled_account_cannot_reuse_checkin(checkin_data, db_session):
    now, llm, calls = checkin_data
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['status'] == 'ready'
    assert (await open_checkin(sessionmaker, 99999999, now=now, llm=llm))['status'] == 'unavailable'
    await db_session.execute(text('UPDATE auth_credentials SET disabled=true WHERE user_id=1'))
    await db_session.commit()
    assert (await open_checkin(sessionmaker, 1, now=now, llm=llm))['status'] == 'ai_disabled'
    assert len(calls) == 1

    await db_session.execute(text('UPDATE auth_credentials SET disabled=false WHERE user_id=1'))
    await db_session.commit()


async def test_grounding_rejection_uses_recorded_data_and_retains_slot(checkin_data):
    now, _, calls = checkin_data
    async def fabricated(**kwargs):
        calls.append(kwargs)
        return LLMResponse(content=json.dumps({'answer': 'Resting HR 99 bpm', 'claims': []}), model='fixture', tokens_in=20, tokens_out=10)
    llm = SimpleNamespace(complete=fabricated)
    first = await open_checkin(sessionmaker, 1, now=now, llm=llm)
    second = await open_checkin(sessionmaker, 1, now=now, llm=llm)
    assert first['mode'] == second['mode'] == 'recorded'
    assert first['reason'] == 'grounding' and len(calls) == 1
    assert '99' not in str(first['lines'])


async def test_erasure_during_response_cannot_restore_summary(checkin_data, db_session):
    now, original, calls = checkin_data
    async def erased(**kwargs):
        from app.services.derived_data import clear_derived_health_data
        await clear_derived_health_data(db_session, 1)
        await db_session.commit()
        return await original.complete(**kwargs)
    result = await open_checkin(sessionmaker, 1, now=now, llm=SimpleNamespace(complete=erased))
    assert result['lines'] == [] and result['reason'] == 'erased'
    assert await db_session.scalar(text('SELECT content FROM today_checkins WHERE user_id=1')) is None


async def test_unrelated_revision_change_does_not_discard_grounded_answer(checkin_data, db_session):
    now, original, _ = checkin_data
    async def changed(**kwargs):
        await record_observation(db_session, user_id=1, metric='weight', value=70, unit='kg', origin='manual',
            source_record_id='unrelated', measured_at=now, fetched_at=now, timezone='Europe/Rome')
        await db_session.commit()
        return await original.complete(**kwargs)
    result = await open_checkin(sessionmaker, 1, now=now, llm=SimpleNamespace(complete=changed))
    assert result['mode'] == 'ai' and result['status'] == 'ready'


def test_recorded_fallback_uses_comparable_units_origins_and_sparse_coverage():
    from app.reports.recorded_checkin import recorded_lines
    day = datetime(2026,11,17).date()
    def row(value, days, origin='garmin', unit='bpm'):
        return {'value':value,'local_date':str(day-timedelta(days=days)),'origin':origin,'unit':unit}
    evidence={'resting_hr':[row(51,5),row(52,4),row(53,3),row(999,2,'other'),row(54,0)], 'sleep_duration':[row(28800,0,unit='s')]}
    lines=recorded_lines(evidence,day,'en')
    assert len(lines)==3 and '54 bpm' in lines[0] and '28800' not in str(lines)
    assert '51 → 53 bpm' in lines[1] and '3/7' in lines[1] and '999' not in lines[1]
    italian=recorded_lines({'resting_hr':[row(52,1)]},day,'it')
    assert 'insufficienti' in italian[1] and 'nessuna misura' in italian[0]


async def test_short_checkin_reserves_its_actual_output_limit(checkin_data, db_session):
    now, llm, _ = checkin_data
    await open_checkin(sessionmaker,1,now=now,llm=llm)
    reservation=(await db_session.execute(text('SELECT reserved_tokens, actual_tokens FROM ai_budget_reservations WHERE user_id=1'))).one()
    # Full input bytes still reserved conservatively, but only 650 output tokens.
    assert 650 < reservation.reserved_tokens < 4096
    assert reservation.actual_tokens == 350
