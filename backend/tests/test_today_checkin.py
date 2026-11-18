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
    assert len(calls) == 2 and calls[0]['tier'] == 'cheap' and calls[0]['max_tokens'] == 1024 and calls[0]['json_output'] is True
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
    assert result['reason'] == 'provider_timeout' and 'private' not in str(result)
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
    now, llm, calls = checkin_data
    await open_checkin(sessionmaker,1,now=now,llm=llm)
    reservation=(await db_session.execute(text('SELECT reserved_tokens, actual_tokens FROM ai_budget_reservations WHERE user_id=1'))).one()
    # Reserve the bounded JSON envelope, rather than the default 4096 output tokens.
    expected_input = len(json.dumps(calls[0], ensure_ascii=False, default=str).encode())
    assert reservation.reserved_tokens == expected_input + 1024
    assert reservation.actual_tokens == 350


async def test_numeric_json_summary_uses_issued_examples_in_one_call(checkin_data, db_session):
    now, _, calls = checkin_data
    for metric,value,unit in [('resting_hr',48,'bpm'),('body_battery',55,'/100')]:
        await record_observation(db_session,user_id=1,metric=metric,value=value,unit=unit,origin='garmin',
            source_record_id='synthetic-today-'+metric,measured_at=now,fetched_at=now,timezone='Europe/Rome')
    await db_session.commit()
    async def numeric(**kwargs):
        calls.append(kwargs)
        pack=json.loads(kwargs['messages'][0]['content'])
        claims=[c for c in pack['claim_examples'] if c['metric'] in {'resting_hr','body_battery'}]
        assert len(claims)==2 and all(c['evidence_id'].startswith('observation:') and 'value' in c for c in claims)
        assert kwargs['json_output'] is True and kwargs['thinking'] is False
        return LLMResponse(content=json.dumps({'answer':"Today: resting HR 48 bpm; Body Battery 55.\nThe week's coverage is sparse.\nReview today's workout and record how it felt.", 'claims':claims,'limitations':[]}),model='fixture',tokens_in=600,tokens_out=200)
    result=await open_checkin(sessionmaker,1,now=now,llm=SimpleNamespace(complete=numeric))
    assert result['mode']=='ai' and len(result['lines'])==3 and '48 bpm' in result['lines'][0]
    saved=await open_checkin(sessionmaker,1,now=now,llm=SimpleNamespace(complete=numeric),generate=False)
    assert saved['mode']=='ai' and saved['lines']==result['lines'] and len(calls)==1


async def test_invalid_response_reports_safe_validation_code_and_attempt_time(checkin_data):
    now,_,calls=checkin_data
    async def mismatched(**kwargs):
        calls.append(kwargs)
        return LLMResponse(content=json.dumps({'answer':'Resting HR 99 bpm','claims':[]}),model='fixture',tokens_in=20,tokens_out=20)
    llm=SimpleNamespace(complete=mismatched)
    result=await open_checkin(sessionmaker,1,now=now,llm=llm)
    cached=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
    assert result['reason']==cached['reason']=='grounding'
    assert result['detail']==cached['detail']=='UNCITED_NUMERIC_TEXT'
    assert result['attempted_at'] and cached['attempted_at'] and len(calls)==1


async def test_read_only_check_never_creates_claim_or_invokes_provider(checkin_data,db_session,client):
    now,llm,calls=checkin_data
    assert (await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False))['reason']=='not_generated'
    from tests.test_athlete_training import authenticate
    await authenticate(client)
    response=await client.get('/dashboard/check-in')
    assert response.status_code==200 and response.json()['reason']=='not_generated'
    assert calls==[] and await db_session.scalar(text('SELECT count(*) FROM today_checkins'))==0
    assert await db_session.scalar(text('SELECT count(*) FROM ai_budget_reservations'))==0


async def test_pending_visit_can_read_completed_summary_without_another_call(checkin_data):
    now,original,calls=checkin_data
    started,release=asyncio.Event(),asyncio.Event()
    async def held(**kwargs):
        started.set();await release.wait();return await original.complete(**kwargs)
    llm=SimpleNamespace(complete=held)
    task=asyncio.create_task(open_checkin(sessionmaker,1,now=now,llm=llm))
    await asyncio.wait_for(started.wait(),timeout=5)
    try:
        pending=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
        assert pending['reason']=='pending' and pending['attempted_at']
    finally:
        release.set()
    await task
    saved=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
    assert saved['mode']=='ai' and len(calls)==1


async def test_truncated_json_is_distinct_from_measurement_validation_failure(checkin_data):
    now,_,calls=checkin_data
    async def truncated(**kwargs):
        calls.append(kwargs)
        return LLMResponse(content='{"answer":"PRIVATE INCOMPLETE',model='fixture',tokens_in=10,tokens_out=1024,finish_reason='length')
    llm=SimpleNamespace(complete=truncated)
    first=await open_checkin(sessionmaker,1,now=now,llm=llm)
    cached=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
    assert first['reason']==cached['reason']=='output_limit' and len(calls)==1
    assert 'PRIVATE' not in str(first) and 'PRIVATE' not in str(cached)


@pytest.mark.parametrize('code',['provider_auth','provider_rate_limit','provider_request','provider_timeout'])
async def test_provider_error_reasons_are_safe_and_cached(checkin_data,code):
    from app.core.llm import LLMError
    now,_,calls=checkin_data
    async def failed(**kwargs):
        calls.append(kwargs);raise LLMError('PRIVATE ERROR BODY',code=code)
    llm=SimpleNamespace(complete=failed)
    first=await open_checkin(sessionmaker,1,now=now,llm=llm)
    cached=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
    assert first['reason']==cached['reason']==code and len(calls)==1
    assert 'PRIVATE' not in str(first) and 'PRIVATE' not in str(cached)


async def test_old_pending_slot_is_reported_as_interrupted_without_retry(checkin_data,db_session):
    now,llm,calls=checkin_data
    await open_checkin(sessionmaker,1,now=now,llm=llm)
    await db_session.execute(text("UPDATE today_checkins SET status='pending',content=NULL,generated_at=:at"),{'at':now-timedelta(seconds=91)})
    await db_session.commit()
    result=await open_checkin(sessionmaker,1,now=now,llm=llm,generate=False)
    assert result['reason']=='interrupted' and len(calls)==1


def test_native_score_denominator_is_normalized_without_weakening_measurement_checks():
    from app.reports.checkin import checked_answer
    evidence={'body_battery':[{'id':'observation:10:1','metric':'body_battery','value':55,'unit':'/100'}]}
    claim={'evidence_id':'observation:10:1','metric':'body_battery','value':55}
    content=json.dumps({'answer':'Body Battery 55/100.\nCoverage is sparse.\nReview the workout.','claims':[claim]})
    text,detail=checked_answer(content,evidence,'en')
    assert detail is None and text.startswith('Body Battery 55.')
    for answer,claims in [('Body Battery 99/100.',[claim]),('Body Battery 55/10.',[claim]),('Body Battery 55/100.',[]),('Resting HR 55/100 bpm.',[claim])]:
        assert checked_answer(json.dumps({'answer':answer,'claims':claims}),evidence,'en')[0] is None
    wrong_unit={'body_battery':[{**evidence['body_battery'][0],'unit':'ms'}]}
    assert checked_answer(content,wrong_unit,'en')[0] is None
