"""Approval/version boundaries and correctly scoped optional training feedback."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.models.training import TrainingPlan
from app.models.structured_workout import StructuredWorkoutDraft, StructuredWorkoutVersion
from app.schemas.workouts import WorkoutStructure, total_seconds
from app.schemas.athlete_training import ReviewedWorkout
from tests.conftest import csrf_headers
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_athlete_training import authenticate, make_plan, reviewed_document, structure

BLOCKS = [
    {'id':'warm','kind':'warmup','duration_s':600},
    {'id':'reps','kind':'repeat','repetitions':4,'steps':[
        {'id':'effort','kind':'interval','duration_s':120,'target':{'kind':'rpe','lower':6,'upper':8}},
        {'id':'recover','kind':'recovery','duration_s':60}]},
    {'id':'cool','kind':'cooldown','duration_s':300}]

async def setup(client, db_session):
    await authenticate(client)
    day = datetime.now(ZoneInfo('Europe/Rome')).date()+timedelta(days=1)
    plan,items = await make_plan(db_session,day)
    return plan,items[0]

async def draft(client,plan,item,blocks=BLOCKS,revision=0):
    return await client.post(f'/athlete/planned-sessions/{item.id}/workout-drafts',
        headers=csrf_headers(client),json={'expected_plan_revision':plan.revision,'expected_workout_revision':revision,
              'structure':{'title':'Intervals','steps':blocks}})

async def approve(client,row,fingerprint=None):
    return await client.post(f"/athlete/workout-drafts/{row['id']}/confirm",headers=csrf_headers(client),json={
        'payload_hash':fingerprint or row['payload_hash']})

def test_repeat_group_duration_and_whole_structure_validation():
    value = WorkoutStructure(steps=BLOCKS)
    assert total_seconds(value.steps)==1620
    assert total_seconds(WorkoutStructure(steps=[{'id':'distance','kind':'easy','distance_m':1000}]).steps) is None
    with pytest.raises(ValidationError):
        ReviewedWorkout(discipline='running',steps=[BLOCKS[0],BLOCKS[0]])
    with pytest.raises(ValidationError):
        WorkoutStructure(steps=[{'id':'a','kind':'repeat','repetitions':2,'steps':BLOCKS}])
    with pytest.raises(ValidationError):
        WorkoutStructure(steps=[{'id':'a','kind':'easy','duration_s':1,'target':{'kind':'hr_bpm','lower':310,'upper':315}}])

async def test_draft_changes_nothing_until_exact_confirmation_and_retry(client,db_session):
    plan,item = await setup(client,db_session)
    response = await draft(client,plan,item)
    assert response.status_code==201,response.text
    row = response.json()
    assert row['duration_total_s']==1620
    assert not await db_session.scalar(select(StructuredWorkoutVersion.id))
    stored = await db_session.get(StructuredWorkoutDraft,row['id'])
    assert b'Intervals' not in stored.structure_ciphertext
    assert (await approve(client,row,'0'*64)).status_code==409
    approved = await approve(client,row)
    assert approved.status_code==200,approved.text
    assert approved.json()['revision']==1
    assert (await approve(client,row)).json()['id']==approved.json()['id']
    details = (await client.get(f'/athlete/planned-sessions/{item.id}/workout')).json()
    assert details['session']['duration_min']==27
    assert details['plan_revision']==2
    assert details['education'][0]['kind']=='warmup'

async def test_superseded_draft_and_stale_plan_cannot_apply(client,db_session):
    plan,item = await setup(client,db_session)
    first = (await draft(client,plan,item)).json()
    changed = [{**BLOCKS[0],'duration_s':300}]
    second = (await draft(client,plan,item,changed)).json()
    assert (await approve(client,first)).status_code==409
    plan.revision += 1
    await db_session.commit()
    assert (await approve(client,second)).status_code==409
    assert not await db_session.scalar(select(StructuredWorkoutVersion.id))

@pytest.mark.parametrize('restriction',['protected','completed','past'])
async def test_protected_and_historical_sessions_preserved(client,db_session,restriction):
    plan,item = await setup(client,db_session)
    if restriction=='protected':
        item.protected=True
    elif restriction=='past':
        item.date -= timedelta(days=2)
    else:
        saved=await client.put('/athlete/checkins',headers=csrf_headers(client),json={'planned_session_id':item.id,'status':'completed'})
        assert saved.status_code==200,saved.text
    await db_session.commit()
    response=await draft(client,plan,item)
    assert response.status_code==409,response.text

async def test_owner_scope_and_approved_plan_steps(client,db_session):
    await authenticate(client)
    assert (await client.get('/athlete/planned-sessions/999999/workout')).status_code==404
    doc=await reviewed_document(client)
    day=datetime.now(ZoneInfo('Europe/Rome')).date()+timedelta(days=1)
    value=structure(day,sports=('running',))
    value['sessions'][0]['steps']=BLOCKS
    extracted=await client.post(f"/lab/documents/{doc['id']}/plan-drafts",headers=csrf_headers(client),json={
        'expected_document_revision':doc['revision'],'structure':value})
    row=extracted.json()
    response=await client.post(f"/lab/plan-drafts/{row['id']}/confirm",headers=csrf_headers(client),json={'payload_hash':row['payload_hash']})
    assert response.status_code==200,response.text
    version=await db_session.scalar(select(StructuredWorkoutVersion))
    assert version.source=='approved_plan'

async def test_journal_preserves_omitted_new_fields_and_clears_skipped_quality(client,db_session):
    plan,item=await setup(client,db_session)
    saved=await client.put('/athlete/checkins',headers=csrf_headers(client),json={'planned_session_id':item.id,'status':'partial',
        'fatigue':7,'soreness':2,'workout_quality':6,'modification_reason':'Short on time','terrain_notes':'Hills'})
    assert saved.status_code==200,saved.text
    old_client=await client.put('/athlete/checkins',headers=csrf_headers(client),json={'planned_session_id':item.id,'status':'partial',
        'expected_revision':1,'note':'Updated note'})
    assert old_client.status_code==200,old_client.text
    assert old_client.json()['fatigue']==7 and old_client.json()['terrain_notes']=='Hills'
    stale=await client.put('/athlete/checkins',headers=csrf_headers(client),json={'planned_session_id':item.id,'status':'partial',
        'expected_revision':1,'fatigue':3})
    assert stale.status_code==409
    skipped=await client.put('/athlete/checkins',headers=csrf_headers(client),json={'planned_session_id':item.id,'status':'skipped','expected_revision':2})
    assert skipped.status_code==200,skipped.text
    assert skipped.json()['workout_quality'] is None
    assert skipped.json()['fatigue']==7
