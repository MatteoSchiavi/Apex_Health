"""Explicit goals and threshold provenance never upgrade an estimate to a test."""
from datetime import date
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.schemas.athlete import AthleteUpdate, ConfirmedFTP, MeasurableGoal
from app.services.cycling_metrics import confirmed_ftp
from app.models.lab import AthleteEntry
from tests.conftest import csrf_headers
from tests.test_athlete_context import authenticate
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


@pytest.mark.parametrize("goal", [
    {"metric":"best_power_w","target":250},
    {"metric":"exercise_estimated_1rm_kg","target":100,"exercise":" "},
    {"metric":"weekly_distance_km","target":float("nan")},
    {"metric":"weekly_duration_min","target":0},
    {"metric":"weekly_distance_km","target":10,"duration_s":60},
])
def test_goal_requires_finite_target_and_compatible_reference(goal):
    with pytest.raises(ValidationError):
        MeasurableGoal.model_validate(goal)


@pytest.mark.parametrize("focus,goal", [
    ("running", {"metric":"best_power_w","target":300,"duration_s":300}),
    ("cycling", {"metric":"exercise_estimated_1rm_kg","target":100,"exercise":"Squat"}),
    ("gym", {"metric":"weekly_distance_km","target":10}),
])
def test_goal_cannot_be_saved_for_incompatible_sport(focus,goal):
    with pytest.raises(ValidationError):
        AthleteUpdate.model_validate({"expected_revision":0,"training_focus":[focus],"context":{"focuses":{focus:{"measurable_goal":goal}}}})


@pytest.mark.parametrize("source,extra", [("tested",{}),("tested",{"methodology":"20-minute result"}),
    ("imported",{"methodology":"device result"}),("estimated",{})])
def test_nonmanual_threshold_requires_explicit_provenance(source,extra):
    with pytest.raises(ValidationError):
        ConfirmedFTP.model_validate({"watts":250,"measured_on":"2026-10-12","confirmed":True,"source":source,**extra})


def test_estimated_ftp_never_becomes_load_threshold_and_legacy_manual_remains_supported():
    legacy = {"watts":250,"measured_on":"2026-10-12","confirmed":True}
    assert confirmed_ftp({"ftp":legacy},date(2026,10,12))[0] == 250
    assert confirmed_ftp({"ftp":{**legacy,"source":"estimated","methodology":"0.95 × 20-min mean"}},date(2026,10,12)) == (None,"unvalidated_estimated_ftp",None)


async def test_profile_goals_and_ftp_metadata_are_persisted_and_stale_write_rejected(client,db_session):
    await authenticate(client)
    threshold={"watts":252,"measured_on":"2026-10-12","confirmed":True,"source":"tested", "methodology":"Recorded protocol result", "protocol":"Ramp protocol supplied by athlete"}
    payload={"expected_revision":0,"training_focus":["cycling"],"context":{"ftp":threshold,"focuses":{"cycling":{"measurable_goal":{"metric":"best_power_w","target":300,"duration_s":300}}}}}
    response=await client.put('/athlete/profile',headers=csrf_headers(client),json=payload)
    assert response.status_code == 200,response.text
    stored=(await client.get('/athlete/profile')).json()
    assert stored['context']['ftp']['source'] == 'tested'
    assert stored['context']['focuses']['cycling']['measurable_goal']['duration_s'] == 300
    assertion=await db_session.scalar(select(AthleteEntry).where(AthleteEntry.user_id==1,AthleteEntry.kind=='ftp_assertion'))
    assert assertion.payload['threshold_source']=='tested'
    assert assertion.payload['protocol']==threshold['protocol']
    assert assertion.payload['source']=='user_confirmed'
    assert (await client.put('/athlete/profile',headers=csrf_headers(client),json=payload)).status_code==409


async def test_legacy_client_unrelated_profile_save_preserves_estimated_threshold(client,db_session):
    await authenticate(client)
    threshold={"watts":240,"measured_on":"2026-10-12","confirmed":True,"source":"estimated","methodology":"Fraction of recorded best 20-minute power"}
    payload={"expected_revision":0,"training_focus":["cycling"],"context":{"ftp":threshold}}
    result=await client.put('/athlete/profile',headers=csrf_headers(client),json=payload)
    assert result.status_code==200,result.text
    legacy={"expected_revision":result.json()['revision'],"training_focus":["cycling"],"context":{"athlete_notes":"Changed unrelated note","ftp":{key:threshold[key] for key in ('watts','measured_on','confirmed')}}}
    saved=await client.put('/athlete/profile',headers=csrf_headers(client),json=legacy)
    assert saved.status_code==200,saved.text
    assert saved.json()['context']['ftp']['source']=='estimated'
    assert confirmed_ftp(saved.json()['context'],date(2026,10,12))[1]=='unvalidated_estimated_ftp'
    assertions=list((await db_session.scalars(select(AthleteEntry).where(AthleteEntry.user_id==1,AthleteEntry.kind=='ftp_assertion'))).all())
    assert len(assertions)==1
