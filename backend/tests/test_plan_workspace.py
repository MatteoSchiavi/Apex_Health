"""An existing baseline can be adjusted without replacing it or rewriting history."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import func, select
from app.models.user import User
from app.models.athlete_training import SessionCheckin
from app.models.training import TrainingPlan, PlannedSession
from app.schemas.changes import ProposeIn
from app.services.changes import propose, apply
from app.services.evidence import EvidenceError
from app.services.plan_workspace import plan_workspace
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_athlete_training import authenticate


async def test_existing_plan_adaptation_preserves_completed_protected_and_historical_sessions(client, db_session):
    await authenticate(client)
    user = await db_session.get(User, 1)
    today = datetime.now(ZoneInfo(user.timezone)).date()
    plan = TrainingPlan(user_id=1, created_by='manual', status='active', week_start=today-timedelta(days=2), end_date=today+timedelta(days=14), title='Existing baseline')
    db_session.add(plan)
    await db_session.flush()
    workouts = [PlannedSession(training_plan_id=plan.id, date=today+timedelta(days=d), target_duration_min=40, session_type='easy', protected=protected) for d,protected in [(-1,False),(0,False),(1,True),(2,False),(3,False)]]
    db_session.add_all(workouts)
    await db_session.flush()
    db_session.add_all([SessionCheckin(user_id=1,planned_session_id=workouts[1].id,status='completed'),SessionCheckin(user_id=1,planned_session_id=workouts[4].id,status='partial')])
    foreign = User(name='Other athlete'); db_session.add(foreign); await db_session.flush()
    db_session.add(TrainingPlan(user_id=foreign.id, created_by='manual', status='active', week_start=today, end_date=today+timedelta(days=6),title='Private foreign plan'))
    await db_session.commit()
    response=await client.get('/athlete/plans?date='+str(today))
    assert response.status_code == 200,response.text
    data=response.json()
    assert [p['id'] for p in data['plans']] == [plan.id]
    assert data['plans'][0]['can_adapt']
    assert [s['id'] for s in data['plans'][0]['sessions'] if s['editable']] == [workouts[3].id]
    async def proposal(workout):
        return await propose(db_session,1,ProposeIn.model_validate({'change':{'kind':'session_patch','target_id':workout.id,'target_duration_min':30},'reason':'Review upcoming duration based on recorded feedback'}))
    for blocked in (workouts[0],workouts[1],workouts[2],workouts[4]):
        with pytest.raises(EvidenceError): await proposal(blocked)
    draft = await proposal(workouts[3]); await db_session.commit()
    assert workouts[3].target_duration_min == 40
    await apply(db_session,1,draft['id'],draft['payload_hash']); await db_session.commit()
    assert workouts[3].target_duration_min == 30
    assert all(w.target_duration_min == 40 for w in (workouts[0],workouts[1],workouts[2],workouts[4]))
    assert await db_session.scalar(select(func.count()).select_from(TrainingPlan).where(TrainingPlan.user_id==1)) == 1
    plan.status = 'completed'
    await db_session.commit()
    assert (await plan_workspace(db_session,user,today))['plans'] == []
    historical = await plan_workspace(db_session,user,today-timedelta(days=1))
    assert not historical['plans'][0]['can_adapt']
    assert (await client.get('/athlete/plans?date=bad')).status_code == 422
