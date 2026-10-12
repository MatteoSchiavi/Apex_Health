"""Equipment comparisons reuse owned canonical links without altering counters."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from app.models.activity import Activity, Discipline
from app.models.gear import ActivityGearLink, Gear
from app.models.user import User
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_athlete_training import authenticate


async def world(db_session):
    owner=await db_session.scalar(select(User).order_by(User.id).limit(1))
    sport=await db_session.scalar(select(Discipline).where(Discipline.name=='running'))
    gear=[Gear(user_id=owner.id,name=name,gear_type=kind) for name,kind in
        [('Old shoes','shoes'),('New shoes','shoes'),('Bike','bike')]]
    db_session.add_all(gear)
    await db_session.flush()
    at=datetime(2026,10,12,12,tzinfo=UTC)
    for ident,days in ((0,0),(0,-14),(1,-1),(1,-15)):
        start=at+timedelta(days=days)
        row=Activity(user_id=owner.id,discipline_id=sport.id,start_time=start,start_tz_offset_minutes=0,
            local_date=start.date(),duration_s=3600,distance_m=10000 if ident==0 else 9900,avg_hr=120,
            source_metrics={'garmin':{'comparison_context':{'route_id':'loop','terrain':'paved',
                'indoor':True,'time_convention':'elapsed','effort_type':'easy'}}})
        db_session.add(row)
        await db_session.flush()
        db_session.add(ActivityGearLink(activity_id=row.id,gear_id=gear[ident].id))
    await db_session.commit()
    return owner,gear


async def test_comparison_endpoint_owned_links_units_and_unchanged_counters(client,db_session):
    _,gear=await world(db_session)
    path=f'/gear/{gear[0].id}/comparison?other_gear_id={gear[1].id}'
    assert (await client.get(path)).status_code==401
    await authenticate(client)
    before=(await client.get(f'/gear/{gear[0].id}/history')).json()
    response=await client.get(path)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['status']=='available' and len(data['pairs'])==2
    assert data['selected_gear']['id']==gear[0].id
    assert data['units']['avg_hr_bpm']=='bpm'
    assert data['summaries'][0]['pair_count']==2
    assert data['history_scope']['selected_total']==2
    assert data['history_scope']['truncated'] is False
    after=(await client.get(f'/gear/{gear[0].id}/history')).json()
    assert after['lifetime']==before['lifetime'] and after['gear']==before['gear']
    assert (await client.get(f'/gear/{gear[0].id}/comparison?other_gear_id={gear[0].id}')).status_code==422
    assert (await client.get(f'/gear/{gear[0].id}/comparison?other_gear_id={gear[2].id}')).status_code==422


async def test_comparison_ownership_and_no_context_unavailable(client,db_session):
    _,gear=await world(db_session)
    outsider=User(name='Other athlete',timezone='UTC')
    db_session.add(outsider)
    await db_session.flush()
    foreign=Gear(user_id=outsider.id,name='Private shoes',gear_type='shoes')
    db_session.add(foreign)
    # Corrupt legacy cross-owner association must never become another athlete's evidence.
    foreign_activity=Activity(user_id=outsider.id,start_time=datetime(2026,10,10,tzinfo=UTC),
        start_tz_offset_minutes=0,local_date=datetime(2026,10,10).date(),duration_s=3600,distance_m=10000)
    db_session.add(foreign_activity)
    await db_session.flush()
    db_session.add(ActivityGearLink(activity_id=foreign_activity.id,gear_id=gear[0].id))
    for row in (await db_session.scalars(select(Activity).where(Activity.user_id!=outsider.id))).all():
        row.source_metrics={}
    await db_session.commit()
    await authenticate(client)
    assert (await client.get(f'/gear/{gear[0].id}/comparison?other_gear_id={foreign.id}')).status_code==404
    assert (await client.get(f'/gear/{foreign.id}/comparison?other_gear_id={gear[0].id}')).status_code==404
    response=await client.get(f'/gear/{gear[0].id}/comparison?other_gear_id={gear[1].id}')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['status']=='unavailable' and data['pairs']==[]
    assert data['history_scope']['selected_total']==2
    assert data['reason']=='insufficient_compatible_recordings'
