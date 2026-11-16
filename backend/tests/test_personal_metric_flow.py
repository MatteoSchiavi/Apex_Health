"""Provider payload to Today and activity detail, with genuine zero vs absent."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.connectors.garmin.fetch import store_raw
from app.connectors.garmin.normalize import normalize_raw_row
from app.models.activity import Activity, Discipline
from app.models.wellness import DailyBiometric
from tests.conftest import csrf_headers, login
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def test_official_wellness_and_power_reach_views(client, db_session):
    from app.core.config import get_settings
    settings = get_settings()
    assert (await login(client, settings.owner_email, settings.owner_password)).status_code == 200
    day = datetime.now(UTC).date()
    payload = {'calendarDate':str(day), 'averageStressLevel':0, 'bodyBatteryMostRecentValue':65, 'hydrationValueInML':750, 'restingHeartRate':0}
    payload['_personal_api_payload'] = dict(payload)
    raw = await store_raw(db_session, 1, f'stats:{day}', payload)
    await normalize_raw_row(db_session, raw, ZoneInfo('UTC'), {})
    raw = await store_raw(db_session, 1, 'activity_summary', {
        'activityId':54321, 'startTimeGMT':f'{day} 08:00:00', 'duration':3600,
        'activityType':{'typeKey':'cycling'}, 'averagePower':200, 'normalizedPower':225,
        'intensityFactor':.75, 'trainingStressScore':56.25, 'hrTimeInZone_1':0, 'hrTimeInZone_2':3600})
    discipline = await db_session.scalar(select(Discipline).where(Discipline.name == 'road_cycling'))
    await normalize_raw_row(db_session, raw, ZoneInfo('UTC'), {'road_cycling':discipline.id})
    await db_session.commit()
    biometric = await db_session.get(DailyBiometric, (1, day))
    assert biometric.hydration_ml == 750 and biometric.resting_hr is None
    response = await client.get(f'/dashboard/overview?date={day}')
    assert response.status_code == 200
    signals = {row['metric']:row['value'] for row in response.json()['provider_signals']}
    assert signals == {'stress':0, 'body_battery':65, 'hydration':750}
    assert response.json()['resting_hr'] is None
    activity = await db_session.scalar(select(Activity).where(Activity.user_id == 1))
    result = await client.get(f'/activities/{activity.id}/endurance')
    assert result.status_code == 200, result.text
    metrics = {row['key']:row for row in result.json()['metrics']}
    assert metrics['normalized_power']['value'] == 225 and metrics['normalized_power']['kind'] == 'recorded'
    assert metrics['tss_style']['value'] == 56.25
    assert metrics['hr_zone_time']['value'][0]['duration_s'] == 0
