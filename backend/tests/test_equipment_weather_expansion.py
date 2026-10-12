"""Optional expansions retain ownership, missingness, units and configured thresholds."""
from copy import deepcopy
from datetime import UTC, date, datetime
from sqlalchemy import select
from app.models.activity import Activity, Discipline
from app.models.gear import ActivityGearLink, Gear
from app.models.user import User
from app.gear.service import accumulate_gear_usage
from app.connectors.weather.normalize import build_weather_snapshot
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_athlete_training import authenticate, make_plan
from tests.conftest import csrf_headers

PAYLOAD={'latitude':45.0,'longitude':9.0,'timezone':'UTC','daily':{'time':['2026-10-12']},
 'hourly':{'time':['2026-10-12T08:00'],'temperature_2m':[19.0],'relative_humidity_2m':[70.0],'wind_speed_10m':[12.0]},
 'hourly_units':{'temperature_2m':'°C','relative_humidity_2m':'%','wind_speed_10m':'km/h'}}

def test_weather_units_coordinate_provenance_and_ambiguous_hours():
    day=date(2026,10,12)
    good=build_weather_snapshot(PAYLOAD,day,start_hour=8,data_kind='archive_reanalysis',coordinate_source='activity_stream')
    assert good['comparison_eligible'] and good['temperature_c']==19
    assert good['method']=='gridded_weather_estimate' and good['data_kind']=='archive_reanalysis'
    home=build_weather_snapshot(PAYLOAD,day,start_hour=8,coordinate_source='configured_home')
    assert home['temperature_c'] is None and not home['comparison_eligible']
    bad=deepcopy(PAYLOAD);bad['hourly_units']['temperature_2m']='°F'
    assert build_weather_snapshot(bad,day,start_hour=8,coordinate_source='activity_stream')['temperature_c'] is None
    repeat=deepcopy(PAYLOAD);repeat['hourly']['time']*=2
    assert 'at_start' not in build_weather_snapshot(repeat,day,start_hour=8)
    assert build_weather_snapshot(PAYLOAD,date(2026,10,11)) is None

async def test_owned_gear_link_history_removal_and_configured_reminder(client,db_session):
    await authenticate(client)
    discipline=await db_session.scalar(select(Discipline.id).where(Discipline.name=='running'))
    activity=Activity(user_id=1,discipline_id=discipline,start_time=datetime(2026,10,12,8,tzinfo=UTC),
        local_date=date(2026,10,12),duration_s=3600,distance_m=10000,start_tz_offset_minutes=0)
    db_session.add(activity);await db_session.commit()
    gear=(await client.post('/gear',headers=csrf_headers(client),json={'name':'Trail shoes','gear_type':'shoes','service_interval_km':5})).json()
    path=f"/gear/{gear['gear_id']}/activities/{activity.id}"
    assert (await client.put(path,headers=csrf_headers(client))).status_code==200
    assert (await client.put(path,headers=csrf_headers(client))).status_code==200
    history=(await client.get(f"/gear/{gear['gear_id']}/history")).json()
    assert history['lifetime']['km']==10 and history['lifetime']['activity_count']==1
    assert history['gear']['usage_pct']==200
    assert history['reminder_policy']=='user_configured_intervals_only'
    assert (await client.delete(path,headers=csrf_headers(client))).status_code==204
    history=(await client.get(f"/gear/{gear['gear_id']}/history")).json()
    assert history['lifetime']['activity_count']==0 and history['lifetime']['km'] is None

async def test_cross_owner_legacy_link_cannot_inflate_counters_or_leak_history(client,db_session):
    await authenticate(client)
    other=User(name='Other');db_session.add(other);await db_session.flush()
    foreign=Activity(user_id=other.id,start_time=datetime(2026,10,12,8,tzinfo=UTC),local_date=date(2026,10,12),
        duration_s=3600,distance_m=10000,start_tz_offset_minutes=0)
    gear=Gear(user_id=1,name='Own shoes',gear_type='shoes')
    db_session.add_all([foreign,gear]);await db_session.flush()
    db_session.add(ActivityGearLink(activity_id=foreign.id,gear_id=gear.id));await db_session.commit()
    await accumulate_gear_usage(db_session,gear);await db_session.commit()
    assert gear.km_since_service==0
    history=(await client.get(f'/gear/{gear.id}/history')).json()
    assert history['activities']==[]
    denied=await client.put(f'/gear/{gear.id}/activities/{foreign.id}',headers=csrf_headers(client))
    assert denied.status_code==404

async def test_service_input_bounds_and_portable_export(client,db_session):
    await authenticate(client)
    bad=await client.post('/gear',headers=csrf_headers(client),json={'name':'Bike','gear_type':'bike','service_interval_km':-10})
    assert bad.status_code==422
    plan,items=await make_plan(db_session,date(2026,10,13))
    exported=await client.get(f'/lab/workouts/{items[0].id}/export')
    assert exported.status_code==200,exported.text
    assert exported.json()['device_compatibility']=='not_verified'
    assert exported.json()['structured_workout'] is None
