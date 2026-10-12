"""Only explicit sensor units survive normalization; details reuse canonical calculations."""
from types import SimpleNamespace as Row
import pytest
from app.services.recorded_dynamics import canonical_dynamics, decoded_fit_dynamics, explicit_summary_dynamics
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_athlete_training import authenticate
from tests.test_athlete_sharing import activity,grant
from tests.conftest import csrf_headers
from app.models.activity import ActivitySourceLink
from app.models.sharing import AthleteShare

@pytest.mark.parametrize('value',[None,True,'nan',float('inf'),-1,9999])
def test_invalid_sensor_quantity_remains_missing(value):
    assert canonical_dynamics({'ground_contact_time_ms':value})=={}

def test_fit_profile_units_and_step_vs_stride_are_preserved():
    values,provenance=decoded_fit_dynamics([Row(name='avg_vertical_oscillation',value=80,units='mm'),
        Row(name='avg_stance_time',value=250,units='ms'),Row(name='avg_step_length',value=1200,units='mm'),
        Row(name='avg_vertical_ratio',value=8,units='percent')])
    assert values=={'vertical_oscillation_cm':8,'ground_contact_time_ms':250,'step_length_m':1.2,'vertical_ratio_pct':8}
    assert 'stride_length_m' not in values
    assert provenance['step_length_m']['conversion_factor']==.001
    assert decoded_fit_dynamics([Row(name='avg_stance_time',value=250,units='seconds')])[0]=={}

def test_generic_provider_fields_need_explicit_units():
    assert explicit_summary_dynamics({'avgVerticalOscillation':8})[0]=={}
    good=explicit_summary_dynamics({'avgVerticalOscillation':8,'field_units':{'avgVerticalOscillation':'cm'}})
    assert good[0]['vertical_oscillation_cm']==8

async def test_activity_detail_advanced_contract_and_resource_picker_are_owned(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    response=await client.get(f'/activities/{recorded.id}/endurance')
    assert response.status_code==200,response.text
    metrics={m['key']:m for m in response.json()['metrics']}
    assert metrics['running_dynamics']['value'] is None
    assert metrics['distance_half_split']['availability']=='unavailable'
    picker=await client.get('/athlete/shares/resources?type=activity')
    assert picker.status_code==200,picker.text
    assert picker.json()['items'][0]['id']==recorded.id

async def test_source_erasure_revokes_and_removes_shared_snapshot(client,db_session):
    await authenticate(client)
    recorded=await activity(db_session)
    db_session.add(ActivitySourceLink(user_id=1,activity_id=recorded.id,source='garmin',external_id='synthetic'))
    await db_session.commit()
    created=await grant(client,{'type':'activity','resource_ids':[recorded.id]})
    preview=(await client.get('/lab/sources/garmin/deletion-preview')).json()
    assert preview['counts']['athlete_shares_affected']==1
    result=await client.post('/lab/sources/garmin/delete',headers=csrf_headers(client),json={'payload_hash':preview['payload_hash']})
    assert result.status_code==200,result.text
    db_session.expire_all()
    row=await db_session.get(AthleteShare,created['grant']['id'])
    assert row.snapshot_ciphertext is None and row.revoked_at is not None
    assert (await client.get('/sharing/view',headers={'X-Apex-Share':created['token']})).status_code==404
