import io
import zipfile
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.lab import LabDocument
from app.models.integration import RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.services.apple_health_import import (
    AppleHealthImportError, import_apple_health, parse_export,
)


def archive(xml: bytes, name="apple_health_export/export.xml") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, xml)
    return out.getvalue()


def test_stream_reader_preserves_records_and_workout_summary_attributes():
    xml = b'''<?xml version="1.0"?><HealthData>
      <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="42.5" unit="ms" startDate="2026-09-01 23:00:00 +0000" endDate="2026-09-01 23:00:00 +0000" />
      <Workout workoutActivityType="HKWorkoutActivityTypeRunning" startDate="2026-09-02 06:00:00 +0000" endDate="2026-09-02 06:30:00 +0000"><WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="5000" unit="m"/></Workout>
    </HealthData>'''
    records = parse_export(archive(xml))
    assert len(records) == 2
    assert records[0]["value"] == "42.5"
    assert records[1]["statistics"][0]["sum"] == "5000"


def test_rejects_zip_without_exactly_one_export_xml():
    with pytest.raises(AppleHealthImportError, match="exactly one export.xml"):
        parse_export(archive(b"<HealthData/>", "unexpected.xml"))


def test_ignores_route_members_in_large_export_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("apple_health_export/export.xml", b"<HealthData/>")
        for index in range(100):
            zf.writestr(f"apple_health_export/workout-routes/route-{index}.gpx", b"<gpx/>")
    assert parse_export(out.getvalue()) == []


def test_invalid_xml_fails_cleanly():
    with pytest.raises(AppleHealthImportError, match="invalid or incomplete"):
        parse_export(archive(b"<HealthData><Record>"))


def health_zip(extra="") -> bytes:
    xml = f'''<HealthData>
      <Record type="HKQuantityTypeIdentifierStepCount" value="1000" unit="count" sourceName="iPhone" startDate="2026-09-01 06:00:00 +0000" endDate="2026-09-01 07:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierStepCount" value="1200" unit="count" sourceName="Apple Watch" startDate="2026-09-01 06:00:00 +0000" endDate="2026-09-01 07:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierStepCount" value="800" unit="count" sourceName="Apple Watch" startDate="2026-09-01 07:00:00 +0000" endDate="2026-09-01 08:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierBodyMass" value="165" unit="lb" sourceName="Scale" startDate="2026-09-01 08:00:00 +0000" endDate="2026-09-01 08:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierRestingHeartRate" value="55" unit="count/min" sourceName="Apple Watch" startDate="2026-09-01 08:00:00 +0000" endDate="2026-09-01 08:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierOxygenSaturation" value="0.97" unit="1" sourceName="Apple Watch" startDate="2026-09-01 08:00:00 +0000" endDate="2026-09-01 08:00:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" value="0.05" unit="s" sourceName="Apple Watch" startDate="2026-09-01 08:00:00 +0000" endDate="2026-09-01 08:00:00 +0000"/>
      <Workout id="stable-workout-id" workoutActivityType="HKWorkoutActivityTypeRunning" sourceName="Apple Watch" sourceVersion="11" startDate="2026-09-01 09:00:00 +0000" endDate="2026-09-01 09:30:00 +0000">
        <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="5000" unit="m"/>
        <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" sum="300" unit="kcal"/>
        <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" average="150" maximum="180" unit="count/min"/>
      </Workout>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisInBed" startDate="2026-09-01 22:00:00 +0000" endDate="2026-09-02 07:00:00 +0000"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepUnspecified" startDate="2026-09-01 23:00:00 +0000" endDate="2026-09-02 07:00:00 +0000"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisDeep" startDate="2026-09-01 23:30:00 +0000" endDate="2026-09-02 00:30:00 +0000"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAwake" startDate="2026-09-02 01:00:00 +0000" endDate="2026-09-02 01:10:00 +0000"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepUnspecified" startDate="2026-09-02 13:00:00 +0000" endDate="2026-09-02 13:20:00 +0000"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepUnspecified" startDate="2026-09-02 16:00:00 +0000" endDate="2026-09-02 16:10:00 +0000"/>
      {extra}
    </HealthData>'''.encode()
    return archive(xml)


@pytest.fixture(autouse=True)
async def clean_apple_import_tables(db_session):
    await db_session.execute(text("TRUNCATE lab_documents, activities, activity_source_links, daily_biometrics, sleep_sessions RESTART IDENTITY CASCADE"))
    await db_session.commit()
    yield


async def _user(session, name: str) -> User:
    user = User(name=name, timezone="UTC")
    session.add(user)
    await session.flush()
    return user


async def test_import_normalizes_workout_daily_metrics_and_sleep_without_overlap(db_session):
    user = await _user(db_session, "apple-import")
    # Another source owns these canonical fields; Apple provenance is retained.
    bio = DailyBiometric(user_id=user.id, date=date(2026, 9, 1), steps=5000, weight_kg=70)
    db_session.add(bio)
    await db_session.flush()

    result = await import_apple_health(db_session, user, "export.zip", health_zip())
    assert result["activities_imported"] == 1
    assert result["sleep_sessions_imported"] == 3
    activity = await db_session.scalar(select(Activity).where(Activity.user_id == user.id))
    running_id = await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    assert activity.discipline_id == running_id
    assert activity.distance_m == 5000 and activity.calories == 300
    assert activity.avg_hr == 150 and activity.max_hr == 180
    assert activity.source_metrics["apple_health"]["workout_type"] == "HKWorkoutActivityTypeRunning"
    assert bio.steps == 5000 and float(bio.weight_kg) == 70
    assert bio.resting_hr == 55 and float(bio.spo2_avg) == 97
    assert bio.source_metrics["apple_health"]["steps"]["value"] == 2000
    assert bio.source_metrics["apple_health"]["steps"]["source"] == "Apple Watch"
    assert bio.source_metrics["apple_health"]["hrv_sdnn_ms"]["mean"] == 50
    assert bio.source_metrics["apple_health"]["weight_kg"]["original_unit"] == "lb"
    assert await db_session.scalar(select(HrvReading.id).where(HrvReading.user_id == user.id)) is None
    sessions = (await db_session.scalars(select(SleepSession).where(SleepSession.user_id == user.id))).all()
    night = next(row for row in sessions if row.total_sleep_s and row.total_sleep_s > 1000)
    assert night.deep_s == 3600 and night.awake_s == 600
    assert night.total_sleep_s == 7 * 3600 + 50 * 60


async def test_reimported_exports_deduplicate_workout_across_file_hashes_and_scope_users(db_session):
    user, other = await _user(db_session, "first"), await _user(db_session, "second")
    original = health_zip()
    changed_export = health_zip('<Record type="HKQuantityTypeIdentifierStepCount" value="1" unit="count" sourceName="iPhone" startDate="2026-09-03 06:00:00 +0000" endDate="2026-09-03 06:01:00 +0000"/>')
    await import_apple_health(db_session, user, "one.zip", original)
    duplicate = await import_apple_health(db_session, user, "one.zip", original)
    assert duplicate["already_imported"] is True
    await import_apple_health(db_session, user, "two.zip", changed_export)
    await import_apple_health(db_session, other, "one.zip", original)
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == user.id))).all()) == 1
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == other.id))).all()) == 1
    assert len((await db_session.scalars(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id))).all()) == 1
    assert len((await db_session.scalars(select(LabDocument).where(LabDocument.user_id == user.id))).all()) == 2


async def test_garmin_activity_is_reconciled_and_apple_preserves_its_values(db_session):
    user = await _user(db_session, "cross-provider")
    discipline_id = await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    garmin = Activity(
        user_id=user.id,
        discipline_id=discipline_id,
        start_time=datetime(2026, 9, 1, 9, 4, tzinfo=timezone.utc),
        start_tz_offset_minutes=0,
        local_date=date(2026, 9, 1),
        duration_s=1800,
        distance_m=4500,
        calories=280,
        avg_hr=140,
        max_hr=170,
        data_completeness="full",
        source_metrics={"garmin": {"training_effect": 3.2}},
    )
    db_session.add(garmin)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=garmin.id, source="garmin", external_id="garmin-run-1"))
    await db_session.flush()

    await import_apple_health(db_session, user, "export.zip", health_zip())
    # A later Apple export refreshes the same stable workout ID but must not
    # replace populated Garmin values on the reconciled activity.
    changed = health_zip().replace(b'average="150"', b'average="165"').replace(b'value="800"', b'value="801"')
    await import_apple_health(db_session, user, "export-updated.zip", changed)
    rows = (await db_session.scalars(select(Activity).where(Activity.user_id == user.id))).all()
    links = (await db_session.scalars(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id))).all()
    assert len(rows) == 1
    assert rows[0].id == garmin.id
    assert rows[0].distance_m == 4500 and rows[0].calories == 280
    assert rows[0].avg_hr == 140 and rows[0].max_hr == 170
    assert rows[0].source_metrics["garmin"]["training_effect"] == 3.2
    assert rows[0].source_metrics["apple_health"]["workout_type"] == "HKWorkoutActivityTypeRunning"
    assert {link.source for link in links} == {"garmin", "apple_health_import"}
    apple_link = next(link for link in links if link.source == "apple_health_import")
    reference = await db_session.get(RawIngest, apple_link.raw_ingest_id)
    document_id = await db_session.scalar(select(LabDocument.id).where(
        LabDocument.user_id == user.id, LabDocument.media_type == "application/zip",
        LabDocument.content_hash == reference.raw_json["file_hash"]))
    assert reference.raw_json["lab_document_id"] == document_id
