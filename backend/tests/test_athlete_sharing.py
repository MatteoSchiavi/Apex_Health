"""Real database/API tests of scoped snapshots, capability privacy, and revocation."""
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import SessionCheckin
from app.models.lab import ChangeAudit
from app.models.sharing import AthleteShare
from app.models.structured_workout import StructuredWorkoutVersion
from app.models.training import TrainingPlan, PlannedSession
from app.models.user import User, AuthCredential
from app.services.evidence import canonical, digest
from tests.conftest import csrf_headers
from tests.test_athlete_training import authenticate
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def isolate_grants(db_session):
    await db_session.execute(text('TRUNCATE athlete_shares RESTART IDENTITY'))
    await db_session.execute(text('UPDATE auth_credentials SET disabled=false,failed_login_count=0,locked_until=NULL WHERE user_id=1'))
    await db_session.commit()


async def activity(db_session, user_id=1, day=date(2026,10,12)):
    sport = await db_session.scalar(select(Discipline.id).where(Discipline.name=='running'))
    row = Activity(user_id=user_id, discipline_id=sport, start_time=datetime.combine(day,datetime.min.time(),tzinfo=UTC)+timedelta(hours=8),
        local_date=day,start_tz_offset_minutes=0,duration_s=1800,distance_m=5000,avg_hr=140,
        source_metrics={'garmin':{'latitude':12.34,'raw_private_notes':'RAW PRIVATE VALUE'}},
        weather_snapshot={'location':'PRIVATE LOCATION'})
    db_session.add(row)
    await db_session.commit()
    return row


async def plan(db_session, user_id=1, status='active'):
    row = TrainingPlan(user_id=user_id,week_start=date(2026,10,12),end_date=date(2026,10,18),
        created_by='manual',status=status,title='Reviewed running week')
    db_session.add(row)
    await db_session.flush()
    sport = await db_session.scalar(select(Discipline.id).where(Discipline.name=='running'))
    workout = PlannedSession(training_plan_id=row.id,date=date(2026,10,12),discipline_id=sport,
        session_type='easy',target_duration_min=30,target_distance_m=5000,description='PRIVATE SESSION INSTRUCTIONS',
        intensity_targets={'rpe':'3'})
    db_session.add(workout)
    await db_session.commit()
    return row,workout


async def preview(client,selection,days=7):
    result = await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={
        'selection':selection,'expires_in_days':days})
    assert result.status_code==200,result.text
    return result.json()


async def grant(client,selection,days=7):
    reviewed = await preview(client,selection,days)
    result = await client.post('/athlete/shares',headers=csrf_headers(client),json={
        'selection':selection,'expires_in_days':days,'preview_hash':reviewed['payload_hash']})
    assert result.status_code==201,result.text
    assert result.json()['snapshot']==reviewed['snapshot']
    return result.json()


async def test_share_exact_minimal_encrypted_snapshot_metadata_and_header_only_read(client,db_session):
    await authenticate(client)
    recorded = await activity(db_session)
    db_session.add(SessionCheckin(user_id=1,activity_id=recorded.id,status='completed',rpe=6,note='PRIVATE FEEDBACK NOTE'))
    await db_session.commit()
    selection = {'type':'activity','resource_ids':[recorded.id]}
    created = await grant(client,selection)
    fields = created['snapshot']['items'][0]['fields']
    assert set(fields)=={'date','discipline','duration_s','distance_m'}
    assert 'PRIVATE' not in json.dumps(created['snapshot']) and 'avg_hr' not in fields
    token=created['token']
    assert len(token)==43 and created['url_fragment']=='#'+token
    stored=await db_session.get(AthleteShare,created['grant']['id'])
    assert stored.token_hash==hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored.token_hash and b'running' not in stored.snapshot_ciphertext
    assert json.loads(decrypt_bytes(stored.snapshot_ciphertext))==created['snapshot']
    listing=await client.get('/athlete/shares')
    assert listing.status_code==200
    assert token not in listing.text and 'snapshot' not in listing.text and 'token_hash' not in listing.text
    assert listing.json()[0]['state']=='active'
    client.cookies.clear()
    public=await client.get('/sharing/view',headers={'X-Apex-Share':token})
    assert public.status_code==200 and public.json()['snapshot']==created['snapshot']
    assert public.headers['Cache-Control']=='no-store' and public.headers['Referrer-Policy']=='no-referrer'
    assert (await client.get('/sharing/view')).status_code==404
    assert (await client.get('/sharing/view?token='+token)).status_code==404
    assert (await client.get('/sharing/view?token='+token,headers={'X-Apex-Share':token})).status_code==404
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':'a'*43})).status_code==404
    assert (await client.post('/sharing/view',headers={'X-Apex-Share':token},json={'duration_s':1})).status_code in {403,405}


async def test_selected_hr_feedback_and_notes_require_separate_explicit_fields(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    db_session.add(SessionCheckin(user_id=1,activity_id=recorded.id,status='completed',rpe=7,pain=True,felt_unwell=True,
        fatigue=5,note='EXPLICIT SHARED NOTE',terrain_notes='EXPLICIT TERRAIN'))
    await db_session.commit()
    selection={'type':'activity','resource_ids':[recorded.id],'fields':['date','avg_hr','feedback_status','rpe'],'include_feedback':True}
    created=await grant(client,selection)
    fields=created['snapshot']['items'][0]['fields']
    assert fields=={'date':'2026-10-12','avg_hr':140.0,'feedback_status':'completed','rpe':7}
    assert 'pain' not in json.dumps(created['snapshot']) and 'EXPLICIT' not in json.dumps(created['snapshot'])
    selection['fields']+=['feedback_note']
    explicit=await preview(client,selection)
    assert explicit['snapshot']['items'][0]['fields']['feedback_note']=='EXPLICIT SHARED NOTE'
    selection['include_feedback']=False
    refused=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={'selection':selection})
    assert refused.status_code==422


async def test_snapshot_change_refused_and_later_source_changes_do_not_change_approved_share(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    selection={'type':'activity','resource_ids':[recorded.id],'fields':['duration_s']}
    reviewed=await preview(client,selection)
    recorded.duration_s=2400
    await db_session.commit()
    stale=await client.post('/athlete/shares',headers=csrf_headers(client),json={'selection':selection,'preview_hash':reviewed['payload_hash']})
    assert stale.status_code==409
    assert not await db_session.scalar(select(AthleteShare.id))
    created=await grant(client,selection)
    recorded.duration_s=3000
    await db_session.commit()
    public=await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})
    assert public.json()['snapshot']['items'][0]['fields']['duration_s']==2400
    await db_session.delete(recorded)
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404


async def test_revoke_erases_snapshot_audits_and_is_idempotent(client,db_session):
    await authenticate(client)
    created=await grant(client,{'type':'activity','resource_ids':[(await activity(db_session)).id]})
    endpoint=f"/athlete/shares/{created['grant']['id']}"
    assert (await client.delete(endpoint,headers=csrf_headers(client))).status_code==204
    assert (await client.delete(endpoint,headers=csrf_headers(client))).status_code==204
    stored=await db_session.get(AthleteShare,created['grant']['id'],populate_existing=True)
    assert stored.revoked_at and stored.erased_at and stored.snapshot_ciphertext is None
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404
    audits=(await db_session.scalars(select(ChangeAudit).where(ChangeAudit.action.in_(('athlete_share_created','athlete_share_revoked'))))).all()
    assert len(audits)==2 and created['token'] not in str([row.payload for row in audits])


async def test_expiry_disabled_owner_and_underlying_ownership_are_enforced(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    created=await grant(client,{'type':'activity','resource_ids':[recorded.id]})
    credential=await db_session.get(AuthCredential,1)
    credential.disabled=True
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404
    credential.disabled=False
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==200
    row=await db_session.get(AthleteShare,created['grant']['id'])
    row.created_at=datetime.now(UTC)-timedelta(days=3)
    row.expires_at=datetime.now(UTC)-timedelta(days=1)
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404
    await db_session.refresh(row)
    assert row.snapshot_ciphertext is None and row.erased_at
    other=User(name='Other athlete',timezone='UTC')
    db_session.add(other)
    await db_session.commit()
    created=await grant(client,{'type':'activity','resource_ids':[recorded.id]})
    recorded.user_id=other.id
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404


async def test_record_and_grant_cross_user_isolation_and_unsupported_source(client,db_session):
    await authenticate(client)
    other=User(name='Other athlete',timezone='UTC')
    db_session.add(other)
    await db_session.flush()
    private=await activity(db_session,other.id)
    response=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={'selection':{'type':'activity','resource_ids':[private.id]}})
    assert response.status_code==404
    owner_activity=await activity(db_session)
    created=await grant(client,{'type':'activity','resource_ids':[owner_activity.id]})
    row=await db_session.get(AthleteShare,created['grant']['id'])
    row.user_id=other.id
    await db_session.commit()
    assert (await client.get('/athlete/shares')).json()==[]
    assert (await client.delete(f'/athlete/shares/{row.id}',headers=csrf_headers(client))).status_code==404
    db_session.add(ActivitySourceLink(user_id=1,activity_id=owner_activity.id,source='unsupported_private_connector',external_id='private'))
    await db_session.commit()
    response=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={'selection':{'type':'activity','resource_ids':[owner_activity.id]}})
    assert response.status_code==422


async def test_plan_and_workout_only_share_approved_explicit_fields_and_steps(client,db_session):
    await authenticate(client)
    baseline,workout=await plan(db_session)
    structure={'title':'Private workout title','objective':'PRIVATE OBJECTIVE','steps':[{'id':'warmup','kind':'warmup','duration_s':300,'description':'OPT IN STEP'}]}
    db_session.add(StructuredWorkoutVersion(user_id=1,planned_session_id=workout.id,revision=1,
        structure_ciphertext=encrypt_bytes(canonical(structure).encode()),payload_hash=digest(structure),source='user_confirmed'))
    await db_session.commit()
    minimal=await grant(client,{'type':'plan','resource_ids':[baseline.id]})
    assert set(minimal['snapshot']['items'][0]['fields'])=={'title','starts_on','ends_on','session_count'}
    assert 'PRIVATE' not in json.dumps(minimal['snapshot'])
    session_summary=await preview(client,{'type':'plan','resource_ids':[baseline.id],'fields':['sessions']})
    fields=session_summary['snapshot']['items'][0]['fields']['sessions'][0]
    assert set(fields)=={'date','discipline','duration_min','distance_m'}
    explicit=await grant(client,{'type':'workout','resource_ids':[workout.id],'fields':['date','description','steps']})
    assert explicit['snapshot']['items'][0]['fields']['description']=='PRIVATE SESSION INSTRUCTIONS'
    assert explicit['snapshot']['items'][0]['fields']['steps'][0]['description']=='OPT IN STEP'
    assert 'PRIVATE OBJECTIVE' not in json.dumps(explicit['snapshot'])
    baseline.status='draft'
    await db_session.commit()
    refused=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={'selection':{'type':'workout','resource_ids':[workout.id]}})
    assert refused.status_code==409


async def test_progress_projects_safe_aggregates_retains_missingness_and_dependency_liveness(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    db_session.add(AthleteProfile(user_id=1,training_focus=['running'],context={'athlete_notes':'PRIVATE PROFILE',
        'focuses':{'running':{'constraints':'PRIVATE CONSTRAINT','event':{'title':'PRIVATE EVENT','date':'2027-04-01'}}}}))
    await db_session.commit()
    selection={'type':'progress','sport':'running','starts_on':'2026-10-12','ends_on':'2026-10-18',
        'fields':['volume','consistency','adherence','goal_progress']}
    created=await grant(client,selection)
    snapshot=created['snapshot']
    assert snapshot['fields']['volume']['value']['distance_m']==5000
    for name in selection['fields']:
        assert {'value','unit','availability','unavailable_reason','formula','formula_version','limitations'} <= set(snapshot['fields'][name])
    assert snapshot['fields']['goal_progress']['value'] is None
    assert snapshot['fields']['goal_progress']['availability']=='unavailable'
    assert 'PRIVATE' not in json.dumps(snapshot) and 'source_dependencies' not in json.dumps(snapshot)
    assert 'avg_hr' not in json.dumps(snapshot) and 'goal_context' not in json.dumps(snapshot)
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==200
    await db_session.delete(recorded)
    await db_session.commit()
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404


@pytest.mark.parametrize('extra',[
    {'fields':['source_metrics']},{'fields':['latitude']},{'fields':['sleep']},{'fields':['pain'],'include_feedback':True},
    {'fields':['distance_m','distance_m']},{'rights':'write'},{'resource_ids':[]},{'resource_ids':[1,1]},
])
async def test_finite_fields_reject_private_data_authority_and_invalid_selection(client,extra):
    await authenticate(client)
    response=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={'selection':{'type':'activity','resource_ids':[1],**extra}})
    assert response.status_code==422


@pytest.mark.parametrize('days',[0,31])
async def test_expiry_limit_is_server_enforced(client,days):
    await authenticate(client)
    response=await client.post('/athlete/shares/preview',headers=csrf_headers(client),json={
        'selection':{'type':'activity','resource_ids':[1]},'expires_in_days':days})
    assert response.status_code==422
