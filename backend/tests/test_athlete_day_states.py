"""Today distinguishes saved context, plan review, rest days and completed multisport work."""
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import select
from app.models.activity import Activity, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import PlanDocumentDraft
from app.models.lab import LabDocument
from app.models.training import TrainingPlan
from app.models.user import User
from app.schemas.athlete import AthleteContext
from app.services.athlete_day import your_day
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401

DAY = date(2026, 10, 12)


async def state(db_session):
    return await your_day(db_session, await db_session.get(User, 1), DAY)


async def test_saved_profile_is_distinct_from_missing_context(db_session):
    empty = await state(db_session)
    assert empty['planning_context']['state'] == 'no_profile'
    db_session.add(AthleteProfile(user_id=1, training_focus=['running'], context={'athlete_notes': 'I also sail.'}, revision=3))
    await db_session.commit()
    saved = await state(db_session)
    assert saved['state'] == 'no_plan'
    assert saved['planning_context']['state'] == 'profile_ready'
    assert saved['planning_context']['profile_revision'] == 3
    assert not saved['sessions'] and not saved['activities']


async def test_empty_defaults_are_incomplete_and_deletion_tombstone_is_absent(db_session):
    profile = AthleteProfile(user_id=1, training_focus=[], context=AthleteContext().model_dump(mode='json', exclude_none=True), revision=1)
    db_session.add(profile)
    await db_session.commit()
    assert (await state(db_session))['planning_context']['state'] == 'profile_incomplete'
    profile.context = {}
    await db_session.commit()
    assert (await state(db_session))['planning_context']['state'] == 'no_profile'


async def test_active_rest_day_does_not_prompt_onboarding(db_session):
    plan = TrainingPlan(user_id=1, week_start=DAY, end_date=DAY+timedelta(days=6), activated_on=DAY,
        status='active', created_by='manual')
    db_session.add(plan)
    await db_session.commit()
    result = await state(db_session)
    assert result['planning_context']['state'] == 'active_rest_day'
    assert result['planning_context']['active_plan_id'] == plan.id
    assert result['sessions'] == []
    plan.end_date = DAY-timedelta(days=1)
    await db_session.commit()
    assert (await state(db_session))['planning_context']['active_plan_id'] is None


async def test_current_owned_draft_has_direct_review_identity(db_session):
    other = User(name='Other athlete')
    db_session.add(other)
    await db_session.flush()
    documents = []
    for uid in (1, other.id):
        doc = LabDocument(user_id=uid, filename='plan.md', media_type='text/plain', content_hash='a'*64,
            ciphertext=b'opaque', excerpt_ciphertext=b'opaque', status='confirmed', revision=1)
        db_session.add(doc)
        await db_session.flush()
        draft = PlanDocumentDraft(user_id=uid, document_id=doc.id, document_revision=1, version=1,
            structure_ciphertext=b'opaque', payload_hash='b'*64, extraction_method='user_reviewed', status='draft')
        db_session.add(draft)
        documents.append((doc,draft))
    await db_session.commit()
    context = (await state(db_session))['planning_context']
    assert context['state'] == 'plan_draft'
    assert context['draft_id'] == documents[0][1].id
    assert context['draft_document_id'] == documents[0][0].id
    documents[0][0].revision = 2
    await db_session.commit()
    assert (await state(db_session))['planning_context']['draft_id'] is None


async def test_multisport_distance_is_partitioned_and_duration_is_shared(db_session):
    for name, distance, duration in [('running', 10000, 3600), ('road_cycling', 40000, 7200)]:
        discipline = await db_session.scalar(select(Discipline.id).where(Discipline.name == name))
        db_session.add(Activity(user_id=1, discipline_id=discipline, start_time=datetime(2026,10,12,8,tzinfo=UTC),
            local_date=DAY, start_tz_offset_minutes=0, duration_s=duration, distance_m=distance))
    await db_session.commit()
    result = await state(db_session)
    assert result['state'] == 'multiple_sessions'
    assert result['totals']['duration_s']['value'] == 10800
    assert 'distance_m' not in result['totals']
    assert result['sport_totals']['running']['distance_m']['value'] == 10000
    assert result['sport_totals']['cycling']['distance_m']['value'] == 40000


async def test_single_sport_distance_and_missing_values_keep_coverage(db_session):
    discipline = await db_session.scalar(select(Discipline.id).where(Discipline.name == 'running'))
    for distance in (10000, None):
        db_session.add(Activity(user_id=1, discipline_id=discipline, start_time=datetime(2026,10,12,8,tzinfo=UTC),
            local_date=DAY, start_tz_offset_minutes=0, duration_s=3600, distance_m=distance))
    await db_session.commit()
    total = (await state(db_session))['sport_totals']['running']['distance_m']
    assert total == {'value':10000,'unit':'m','available_sessions':1,'total_sessions':2}
