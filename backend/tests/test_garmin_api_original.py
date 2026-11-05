"""Garmin API archive -> existing owned activity, with real synthetic FIT bytes."""
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select, func
from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.integration import RawIngest
from app.models.user import User
from app.connectors.garmin.normalize import normalize_raw_row
from app.connectors.garmin.sync import fetch_streams, SyncReport, normalize_pending
from tests.test_garmin_api_downloads import envelope, zipped
from tests.test_fit_strength_exports import exported_fit
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def setup_activity(session):
    owner, foreign = User(name=uuid4().hex, timezone='Europe/Rome'), User(name=uuid4().hex, timezone='UTC')
    session.add_all([owner,foreign]); await session.flush()
    activity = Activity(user_id=owner.id, start_time=datetime(2026,10,1,8,tzinfo=UTC),local_date=datetime(2026,10,1).date(),start_tz_offset_minutes=120,duration_s=3600,data_completeness='partial', source_metrics={'garmin':{'existing':True}})
    session.add(activity); await session.flush()
    session.add(ActivitySourceLink(user_id=owner.id, activity_id=activity.id,source='garmin',external_id='123'))
    await session.flush()
    return owner,foreign,activity


async def test_api_archive_is_owned_idempotent_and_does_not_create_duplicate_activity(db_session):
    owner, foreign, activity = await setup_activity(db_session)
    payload = envelope(zipped({'activity.fit':exported_fit()}))
    client = SimpleNamespace(api_activity_archives=True, unsupported_capabilities={'exercise_sets'},get_activity_archive=AsyncMock(return_value=payload))
    report = SyncReport(user_id=owner.id,mode='incremental')
    for _ in range(2):
        await fetch_streams(db_session,owner.id,client,['123'],0,report,tz=ZoneInfo('Europe/Rome'),discipline_index={},checkpoint=True)
    assert await db_session.scalar(select(func.count()).select_from(Activity).where(Activity.user_id==owner.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ActivitySourceLink).where(ActivitySourceLink.user_id==owner.id)) == 1
    offsets = (await db_session.scalars(select(ActivityStream.t_offset_s).where(ActivityStream.activity_id==activity.id).order_by(ActivityStream.t_offset_s))).all()
    assert offsets == [0,3900,4200]
    assert activity.source_metrics['garmin']['existing']
    assert activity.source_metrics['garmin']['streams_state'] == 'available'
    sets = activity.source_metrics['fit']['exercises']
    assert sum(len(e['recorded_sets']) for e in sets) == 3 and sum(s['reps'] for e in sets for s in e['recorded_sets']) == 20
    assert sets[0]['recorded_sets'] == [{'reps':8,'weight_kg':40}]
    assert report.raw_rows_unprocessed == 0 and report.stats.activity_streams_upserted == 3
    # Same provider ID from another account cannot project onto this activity.
    raw = RawIngest(user_id=foreign.id,source='garmin',payload_type='api_activity_archive:123',raw_json=payload,processed=False)
    db_session.add(raw); await db_session.flush()
    foreign_report = SyncReport(user_id=foreign.id,mode='incremental')
    await normalize_pending(db_session,foreign.id,ZoneInfo('UTC'),{},foreign_report)
    assert not raw.processed and foreign_report.raw_rows_unprocessed == 1
    assert await db_session.scalar(select(func.count()).select_from(ActivityStream).where(ActivityStream.activity_id==activity.id)) == 3


@pytest.mark.parametrize('damage', ['crc', 'identity', 'time'])
async def test_malformed_original_remains_raw_and_cannot_modify_summary(db_session, damage):
    owner,foreign,activity = await setup_activity(db_session)
    content = exported_fit()
    if damage == 'crc': content = content[:-1]+bytes([content[-1]^1])
    payload = envelope(zipped({'activity.fit':content}))
    if damage == 'identity': payload['activity_id'] = 456
    if damage == 'time': activity.start_time = datetime(2026,10,2,8,tzinfo=UTC)
    raw = RawIngest(user_id=owner.id,source='garmin',payload_type='api_activity_archive:123',raw_json=payload,processed=False)
    db_session.add(raw); await db_session.flush()
    report = SyncReport(user_id=owner.id,mode='incremental')
    await normalize_pending(db_session,owner.id,ZoneInfo('UTC'),{},report)
    assert not raw.processed and raw.raw_json == payload and report.raw_rows_unprocessed == 1
    assert await db_session.scalar(select(func.count()).select_from(ActivityStream).where(ActivityStream.activity_id==activity.id)) == 0
    assert activity.duration_s == 3600


async def test_additional_source_document_is_archived_without_fabricating_measurements(db_session):
    owner,foreign,activity = await setup_activity(db_session)
    payload = {'endpoint':'/nutrition-service/food/logs/2026-10-01','requested_date':'2026-10-01','payload':{'unknownUnit':123}}
    raw = RawIngest(user_id=owner.id,source='garmin',payload_type='api_document:food_logs:2026-10-01',raw_json=payload,processed=False)
    db_session.add(raw); await db_session.flush()
    stats = await normalize_raw_row(db_session,raw,ZoneInfo('UTC'),{})
    assert raw.processed and raw.raw_json == payload and stats.biometrics_upserted == 0


def cycling_fit():
    import struct
    from fitdecode.utils import compute_crc
    stamp = int((datetime(2026,10,1,8,tzinfo=UTC)-datetime(1989,12,31,tzinfo=UTC)).total_seconds())
    def message(number, fields, values):
        return b'\x40\x00\x00'+struct.pack('<HB',number,len(fields))+b''.join(bytes(f) for f in fields)+b'\x00'+values
    data = message(18,[(2,4,0x86),(5,1,0),(8,4,0x86),(7,4,0x86),(253,4,0x86)],struct.pack('<IBIII',stamp,2,60000,120000,stamp+120))
    data += message(20,[(253,4,0x86),(3,1,2),(7,2,0x84),(4,1,2),(6,2,0x84),(2,2,0x84),(0,4,0x85),(1,4,0x85)],struct.pack('<IBHBHHii',stamp+90,145,225,88,3500,3000,2**29,2**28))
    data += message(19,[(2,4,0x86),(8,4,0x86),(9,4,0x86),(15,1,2),(19,2,0x84)],struct.pack('<IIIBH',stamp,60000,100000,145,225))
    header = struct.pack('<BBHI4s',14,0x10,2100,len(data),b'.FIT')
    content = header+struct.pack('<H',compute_crc(header))+data
    return content+struct.pack('<H',compute_crc(content))


async def test_original_recorded_channels_laps_units_and_elapsed_offset(db_session):
    from app.models.activity import ActivityLap
    owner,foreign,activity = await setup_activity(db_session)
    db_session.add(ActivityStream(activity_id=activity.id,t_offset_s=90,hr=141))
    await db_session.flush()
    from app.connectors.garmin.sync import _external_ids_missing_streams
    assert '123' in await _external_ids_missing_streams(db_session,owner.id,include_originals=True)
    payload = envelope(zipped({'activity.fit':cycling_fit()}))
    raw = RawIngest(user_id=owner.id,source='garmin',payload_type='api_activity_archive:123',raw_json=payload,processed=False)
    db_session.add(raw); await db_session.flush()
    await normalize_raw_row(db_session,raw,ZoneInfo('Europe/Rome'),{})
    stream = await db_session.scalar(select(ActivityStream).where(ActivityStream.activity_id==activity.id))
    assert stream.t_offset_s == 90  # pause-inclusive elapsed offset, not 60s timer
    assert (stream.hr,float(stream.power),float(stream.cadence)) == (141,225,88)  # existing signal preserved; missing channels filled
    assert float(stream.speed) == 3.5 and float(stream.altitude) == 100
    assert float(stream.lat) == 45 and float(stream.lon) == 22.5
    lap = await db_session.scalar(select(ActivityLap).where(ActivityLap.activity_id==activity.id))
    assert lap.duration_s == 60 and float(lap.distance_m) == 1000
    assert lap.avg_hr == 145 and float(lap.avg_power) == 225
    assert '123' not in await _external_ids_missing_streams(db_session,owner.id,include_originals=True)
    # Replaying identical bytes preserves recalculated daily snapshots.
    # Identity/hash/sample count are stable, so no second invalidation occurs.
    from unittest.mock import patch
    with patch('app.services.derived_data.invalidate_calculation_dates', new=AsyncMock()) as invalidate:
        await normalize_raw_row(db_session,raw,ZoneInfo('Europe/Rome'),{})
        invalidate.assert_not_awaited()


async def test_new_official_observations_do_not_relabel_historical_acquisition(db_session):
    from app.models.lab import Observation
    owner,foreign,activity = await setup_activity(db_session)
    for day, official in [('2026-10-01',True),('2026-10-02',False)]:
        payload = {'calendarDate':day,'totalSteps':1234,'restingHeartRate':52}
        if official: payload['_garmin_api'] = True
        raw = RawIngest(user_id=owner.id,source='garmin',payload_type='stats:'+day,raw_json=payload,processed=False)
        db_session.add(raw); await db_session.flush()
        await normalize_raw_row(db_session,raw,ZoneInfo('Europe/Rome'),{})
    rows = (await db_session.scalars(select(Observation).where(Observation.user_id==owner.id))).all()
    assert rows
    assert {r.acquisition for r in rows if str(r.local_date)=='2026-10-01'} == {'official_api'}
    assert {r.acquisition for r in rows if str(r.local_date)=='2026-10-02'} == {'unofficial_adapter'}


async def test_api_daily_failure_keeps_durable_retry_even_when_stats_were_committed(db_session):
    from app.connectors.garmin.sync import sync_user_garmin
    from app.connectors.garmin.personal import GarminPersonalError
    from app.models.integration import Integration
    from app.models.lab import FeedState
    owner,foreign,activity = await setup_activity(db_session)
    integration = Integration(user_id=owner.id,provider='garmin',status='active')
    db_session.add(integration); await db_session.flush()
    calls = []
    failing = True
    async def sleep(day):
        calls.append(day)
        if day == '2026-11-04' and failing:
            raise GarminPersonalError('safe',status_code=503)
        return {}
    async def stats(day): return {'totalSteps':123} if day == '2026-11-04' else {}
    client = SimpleNamespace(api_activity_archives=True,unsupported_capabilities={'exercise_sets','stress_timeseries'},
        get_activities=AsyncMock(return_value=[]),get_activity_archive=AsyncMock(return_value={}),
        get_sleep_data=sleep,get_hrv_data=AsyncMock(return_value={}),get_stats=stats,get_body_composition=AsyncMock(return_value={}))
    options = dict(page_size=25,page_delay_s=0,empty_gap_days=3,checkpoint=True,now=datetime(2026,11,5,12,tzinfo=UTC))
    first = await sync_user_garmin(db_session,owner,integration,client,**options)
    assert first.state == 'partial' and integration.last_synced_at is None
    retry = await db_session.scalar(select(FeedState).where(FeedState.user_id==owner.id,FeedState.provider=='garmin',FeedState.feed=='wellness_retry'))
    assert retry.cursor == {'date':'2026-11-04'} and retry.availability == 'fetch_failed'
    failing = False
    second = await sync_user_garmin(db_session,owner,integration,client,**options)
    assert second.state == 'complete' and integration.last_synced_at == options['now']
    assert calls.count('2026-11-04') == 2
    assert retry.cursor == {} and retry.availability == 'available'


async def test_failed_activity_documents_remain_retry_candidates_after_fit_success(db_session):
    from app.connectors.garmin.sync import _external_ids_missing_streams
    owner,foreign,activity = await setup_activity(db_session)
    client = SimpleNamespace(api_activity_archives=True,unsupported_capabilities={'exercise_sets'},
        get_activity_archive=AsyncMock(return_value=envelope(zipped({'activity.fit':exported_fit()}))),
        get_activity_documents=AsyncMock(side_effect=[({}, {'activity_workouts':{'error_class':'permission','status_code':403}}),
            ({'activity_workouts':{'endpoint':'/activity-service/activity/123/workouts','activity_id':123,'payload':{'workouts':[]}}}, {})]))
    report = SyncReport(user_id=owner.id,mode='incremental')
    await fetch_streams(db_session,owner.id,client,['123'],0,report,tz=ZoneInfo('UTC'),discipline_index={},checkpoint=True)
    assert activity.source_metrics['garmin']['original_archive_checked']
    assert not activity.source_metrics['garmin']['activity_documents_checked']
    assert '123' in await _external_ids_missing_streams(db_session,owner.id,include_originals=True,include_documents=True)
    await fetch_streams(db_session,owner.id,client,['123'],0,report,tz=ZoneInfo('UTC'),discipline_index={},checkpoint=True)
    assert activity.source_metrics['garmin']['activity_documents_checked']
    assert '123' not in await _external_ids_missing_streams(db_session,owner.id,include_originals=True,include_documents=True)
