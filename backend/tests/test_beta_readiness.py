"""Regression cases derived from failures in the deployed beta account."""
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.agent.entrypoint import HARNESS_VERSION, _history_messages
from app.connectors.garmin.sync import (
    SyncReport, fetch_strength_sets, missing_strength_links, replay_activity_metadata,
)
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.chat import AiChatMessage, AiChatSession
from app.models.integration import RawIngest
from app.models.user import AuthCredential, User
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def test_legacy_strength_without_provider_metadata_is_repairable_and_owned(db_session):
    other = User(name='Other gym athlete'); db_session.add(other); await db_session.flush()
    discipline = await db_session.scalar(select(Discipline).where(Discipline.name == 'strength'))
    day = date(2026,10,5)
    for uid, external in [(1,'123'),(other.id,'456')]:
        activity = Activity(user_id=uid,discipline_id=discipline.id,start_time=datetime(2026,10,5,8,tzinfo=UTC),
            start_tz_offset_minutes=0,local_date=day,duration_s=3600,source_metrics=None)
        db_session.add(activity); await db_session.flush()
        db_session.add(ActivitySourceLink(user_id=uid,activity_id=activity.id,source='garmin',external_id=external))
    await db_session.commit()
    assert (await db_session.scalars(missing_strength_links(1,day,day))).all() == ['123']
    client = AsyncMock(); client.get_activity_exercise_sets.return_value = {'exerciseSets':[]}
    report = SyncReport(user_id=1,mode='repair')
    await fetch_strength_sets(db_session,1,client,'456',0,report)
    client.get_activity_exercise_sets.assert_not_awaited()
    await fetch_strength_sets(db_session,1,client,'123',0,report)
    client.get_activity_exercise_sets.assert_awaited_once_with(123)
    assert report.raw_rows_stored == 1


async def test_metadata_replay_uses_only_current_owned_link_and_preserves_recorded_sets(db_session):
    other = User(name='Other raw athlete'); db_session.add(other); await db_session.flush()
    discipline = await db_session.scalar(select(Discipline).where(Discipline.name == 'strength'))
    day = date(2026,10,5)
    def raw(uid, external, load):
        return RawIngest(user_id=uid,source='garmin',payload_type='activity_summary',processed=True,
            raw_json={'activityId':external,'activityType':{'typeKey':'strength_training'},
                'startTimeGMT':'2026-10-05 08:00:00','duration':3600,'activityTrainingLoad':load})
    old, current, erased, foreign = raw(1,123,999),raw(1,123,42),raw(1,789,88),raw(other.id,456,77)
    db_session.add_all([old,current,erased,foreign]); await db_session.flush()
    sets = [{'name':'Squat','muscle_group':'legs','recorded_sets':[{'reps':8,'weight_kg':40}]}]
    activity = Activity(user_id=1,discipline_id=discipline.id,start_time=datetime(2026,10,5,8,tzinfo=UTC),
        start_tz_offset_minutes=0,local_date=day,duration_s=3600,source_metrics={'garmin':{'exercises':sets}})
    db_session.add(activity); await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=1,activity_id=activity.id,source='garmin',external_id='123',raw_ingest_id=current.id))
    await db_session.commit()
    assert await replay_activity_metadata(db_session,1,ZoneInfo('UTC'),{'strength':discipline.id},day,day) == 1
    await db_session.flush()
    assert activity.training_load == 42
    assert activity.source_metrics['garmin']['training_load_method'] == 'garmin_activity_training_load'
    assert activity.source_metrics['garmin']['exercises'] == sets
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == 1))).all()) == 1


async def test_failed_coach_turns_are_not_replayed_as_assistant_guidance(db_session):
    chat = AiChatSession(user_id=1,started_at=datetime.now(UTC),last_activity_at=datetime.now(UTC))
    db_session.add(chat); await db_session.flush()
    for status in ('incomplete','invalid','structured','narrative_only'):
        db_session.add(AiChatMessage(session_id=chat.id,role='user',content='Question '+status))
        db_session.add(AiChatMessage(session_id=chat.id,role='assistant',content='Reply '+status,
            referenced_data={'harness_version':HARNESS_VERSION,'grounding':{'status':status}}))
    await db_session.flush()
    messages = await _history_messages(db_session,chat.id,None)
    assert [m['content'] for m in messages] == ['Question structured','Reply structured','Question narrative_only','Reply narrative_only']


async def test_disabled_account_maintenance_cancels_before_any_health_processing(db_session):
    from app.models.lab import LabJob
    from app.tasks.lab_tasks import run_job
    user = User(name='Disabled maintenance account'); db_session.add(user); await db_session.flush()
    db_session.add(AuthCredential(user_id=user.id,email=f'maintenance-{user.id}@example.com',password_hash='unused',role='friend',disabled=True))
    job = LabJob(user_id=user.id,kind='repair',state='queued',parameters={'start':'2026-10-01','end':'2026-10-08'},progress={})
    db_session.add(job); await db_session.commit()
    assert await run_job(job.id) == {'state':'cancelled'}
    await db_session.refresh(job)
    assert job.state == 'cancelled' and job.progress == {}
