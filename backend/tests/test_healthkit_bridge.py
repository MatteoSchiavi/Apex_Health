"""Bridge contract/security tests using the migrated PostgreSQL fixture."""
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_session_token, new_session_token
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.healthkit import HealthKitBatch, HealthKitPairing, HealthKitSample
from app.models.lab import FeedState, Observation
from app.models.user import AuthCredential, User
from app.models.watch import DeviceToken
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.schemas.healthkit import HealthKitAddition, HealthKitDelta
from app.services.healthkit_ingest import SOURCE, ingest_healthkit
from app.services.biometric_provenance import biometric_origin, set_biometric
from conftest import csrf_headers, login, reset_owner_auth_state


def sample(kind="StepCount", value=1000, start="2026-09-01T06:00:00Z", end="2026-09-01T07:00:00Z", source="Apple Watch", **kwargs):
    return {"uuid": str(uuid4()), "type": f"HKQuantityTypeIdentifier{kind}", "start_at": start,
        "end_at": end, "value": value, "unit": "count", "source_bundle": "com.apple.health",
        "source_name": source, "device": source, "metadata": {}, "workout_activity_type": None, **kwargs}


def delta(additions=(), deletions=(), checkpoint=0, **kwargs):
    return HealthKitDelta(batch_id=uuid4(), expected_checkpoint=checkpoint,
        additions=list(additions), deletions=list(deletions), **kwargs)


@pytest.fixture
async def bridge(db_session):
    name = f"healthkit-{uuid4()}"
    user = User(name=name, timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    db_session.add(AuthCredential(user_id=user.id, email=f"{name}@test.invalid", password_hash="not-used"))
    raw = new_session_token()
    token = DeviceToken(user_id=user.id, name="iPhone", scope="healthkit_sync", sync_checkpoint=0,
        token_hash=hash_session_token(raw, get_settings().session_secret), absolute_expires_at=datetime.now(UTC) + timedelta(days=365))
    db_session.add(token)
    await db_session.commit()
    return user, token, raw


@pytest.mark.parametrize("changes", [
    {"value": True}, {"value": float("inf")}, {"value": -1}, {"unit": "kg"},
    {"type": "steps"}, {"start_at": "2026-09-01T06:00:00"},
    {"end_at": "2026-09-01T05:00:00Z"}, {"metadata": {str(n): n for n in range(33)}},
    {"metadata": {"source_revision": "x" * 8200}}, {"metadata": {"x": float("nan")}},
    {"workout_activity_type": 37}, {"source_bundle": ""}, {"unknown": "field"},
])
def test_rejects_invalid_samples(changes):
    with pytest.raises(ValidationError):
        HealthKitAddition.model_validate(sample(**changes))


def test_bounds_combined_batch_and_ambiguous_uuids():
    with pytest.raises(ValidationError):
        delta([sample() for _ in range(251)], [uuid4() for _ in range(250)])
    item = sample()
    with pytest.raises(ValidationError):
        delta([item, item])
    with pytest.raises(ValidationError):
        delta([item], [item["uuid"]])
    with pytest.raises(ValidationError):
        delta(checkpoint=True)


async def test_all_quantity_types_have_honest_units_and_source_context(db_session, bridge):
    user, token, _ = bridge
    inputs = [("HeartRate", 100, "count/min"), ("RestingHeartRate", 55, "count/min"),
        ("HeartRateVariabilitySDNN", 42, "ms"), ("StepCount", 1000, "count"),
        ("ActiveEnergyBurned", 300, "kcal"), ("BodyMass", 72, "kg"),
        ("BodyFatPercentage", 20, "%"), ("RespiratoryRate", 14, "count/min"),
        ("OxygenSaturation", 98, "%"), ("VO2Max", 54, "mL/kg/min"),
        ("BodyTemperature", 36.8, "degC"), ("BasalBodyTemperature", 36.5, "degC"),
        ("AppleSleepingWristTemperature", 34.5, "degC")]
    await ingest_healthkit(db_session, user, token, delta([sample(kind=kind, value=value, unit=unit) for kind, value, unit in inputs]))
    bio = await db_session.get(DailyBiometric, {"user_id": user.id, "date": date(2026, 9, 1)})
    assert bio.resting_hr == 55 and bio.steps == 1000
    assert float(bio.weight_kg) == 72 and float(bio.body_fat_pct) == 20
    assert float(bio.spo2_avg) == 98 and float(bio.vo2max) == 54
    assert bio.source_metrics[SOURCE]["active_energy_kcal"]["value"] == 300
    assert bio.source_metrics[SOURCE]["basal_body_temperature_c"]["value"] == 36.5
    assert bio.source_metrics[SOURCE]["sleeping_wrist_temperature_c"]["value"] == 34.5
    rows = (await db_session.scalars(select(Observation).where(Observation.user_id == user.id))).all()
    assert all(row.origin == SOURCE for row in rows)
    assert {row.metric for row in rows} >= {"resting_hr", "steps", "weight", "body_fat", "respiration", "spo2", "vo2max", "temperature"}
    assert not any(row.metric == "hrv_overnight_rmssd" for row in rows)


async def test_duplicate_retry_checkpoint_conflicts_and_empty_batch(db_session, bridge):
    user, token, _ = bridge
    batch = delta([sample()])
    first = await ingest_healthkit(db_session, user, token, batch)
    await db_session.commit()
    assert first == {"checkpoint": 1, "accepted": 1, "deleted": 0}
    assert await ingest_healthkit(db_session, user, token, batch) == first
    with pytest.raises(Exception) as mismatch:
        await ingest_healthkit(db_session, user, token, batch.model_copy(update={"additions": []}))
    assert mismatch.value.status_code == 409
    with pytest.raises(Exception) as checkpoint:
        await ingest_healthkit(db_session, user, token, delta())
    assert checkpoint.value.status_code == 409
    empty = await ingest_healthkit(db_session, user, token, delta(checkpoint=1))
    assert empty == {"checkpoint": 2, "accepted": 0, "deleted": 0}
    assert len((await db_session.scalars(select(HealthKitSample).where(HealthKitSample.user_id == user.id))).all()) == 1


async def test_deletion_tombstones_block_resurrection_and_receipts_count_inputs(db_session, bridge):
    user, token, _ = bridge
    item, unknown = sample(), uuid4()
    await ingest_healthkit(db_session, user, token, delta([item]))
    assert await ingest_healthkit(db_session, user, token, delta(deletions=[item["uuid"], unknown], checkpoint=1)) == {"checkpoint": 2, "accepted": 0, "deleted": 2}
    bio = await db_session.get(DailyBiometric, {"user_id": user.id, "date": date(2026, 9, 1)})
    assert bio.steps is None
    assert "steps" not in bio.source_metrics[SOURCE]
    assert await ingest_healthkit(db_session, user, token, delta([item], checkpoint=2)) == {"checkpoint": 3, "accepted": 1, "deleted": 0}
    assert bio.steps is None
    rows = (await db_session.scalars(select(HealthKitSample).where(HealthKitSample.user_id == user.id))).all()
    assert all(row.deleted and row.payload is None for row in rows)
    obs = await db_session.scalar(select(Observation).where(Observation.user_id == user.id, Observation.current.is_(True)))
    assert obs.availability == "deleted" and obs.value == {"value": None}
    # New UUID on the same day can replace a deleted daily aggregate safely.
    await ingest_healthkit(db_session, user, token, delta([sample(value=500)], checkpoint=3))
    assert bio.steps == 500


async def test_uuid_payload_immutable_and_account_scoped(db_session, bridge):
    user, token, _ = bridge
    item = sample()
    await ingest_healthkit(db_session, user, token, delta([item]))
    with pytest.raises(Exception) as conflict:
        await ingest_healthkit(db_session, user, token, delta([{**item, "value": 2000}], checkpoint=1))
    assert conflict.value.status_code == 409
    other = User(name="other-healthkit", timezone="UTC")
    db_session.add(other)
    await db_session.flush()
    other_token = DeviceToken(user_id=other.id, name="other", scope="healthkit_sync", token_hash=str(uuid4()), sync_checkpoint=0)
    db_session.add(other_token)
    await db_session.flush()
    await ingest_healthkit(db_session, other, other_token, delta([item]))
    assert len((await db_session.scalars(select(HealthKitSample).where(HealthKitSample.uuid == item["uuid"]))).all()) == 2


async def test_watch_source_overlap_timezone_and_other_provider_ownership(db_session, bridge):
    user, token, _ = bridge
    user.timezone = "America/Los_Angeles"
    await ingest_healthkit(db_session, user, token, delta([
        sample(value=1000, start="2026-09-01T01:00:00Z", end="2026-09-01T02:00:00Z", source="iPhone"),
        sample(value=1200, start="2026-09-01T01:00:00Z", end="2026-09-01T02:00:00Z"),
        sample(value=800, start="2026-09-01T02:00:00Z", end="2026-09-01T03:00:00Z"),
        sample(value=500, start="2026-09-01T01:30:00Z", end="2026-09-01T02:00:00Z"),
    ]))
    bio = await db_session.get(DailyBiometric, {"user_id": user.id, "date": date(2026, 8, 31)})
    assert bio.steps == 2000
    assert bio.source_metrics[SOURCE]["steps"]["samples"] == 3
    # Another provider replaces the field; deletion may not erase it.
    bio.steps = 9000
    bio.source_metrics = {**bio.source_metrics, "garmin": {"steps": 9000}}
    ids = (await db_session.scalars(select(HealthKitSample.uuid).where(HealthKitSample.user_id == user.id))).all()
    await ingest_healthkit(db_session, user, token, delta(deletions=ids, checkpoint=1))
    assert bio.steps == 9000 and bio.source_metrics["garmin"]["steps"] == 9000


async def test_sdnn_preserves_method_and_does_not_populate_rmssd(db_session, bridge):
    user, token, _ = bridge
    await ingest_healthkit(db_session, user, token, delta([sample(kind="HeartRateVariabilitySDNN", value=42, unit="ms",
        metadata={"source_revision": {"version": "11", "product_type": "Watch"}})]))
    bio = await db_session.get(DailyBiometric, {"user_id": user.id, "date": date(2026, 9, 1)})
    assert bio.source_metrics[SOURCE]["hrv_sdnn_ms"]["value"] == 42
    assert await db_session.scalar(select(HrvReading.id).where(HrvReading.user_id == user.id)) is None
    assert await db_session.scalar(select(Observation.id).where(Observation.user_id == user.id, Observation.metric == "hrv_overnight_rmssd")) is None
    ledger = await db_session.scalar(select(HealthKitSample).where(HealthKitSample.user_id == user.id))
    assert ledger.payload["metadata"]["source_revision"]["version"] == "11"


async def test_sleep_stages_overlap_wake_day_and_deletion_protects_other_provider(db_session, bridge):
    user, token, _ = bridge
    def sleep(value, start, end, source="Apple Watch"):
        return sample(value=value, type="HKCategoryTypeIdentifierSleepAnalysis", unit=None, start=start, end=end, source=source)
    asleep = sleep(1, "2026-09-01T23:00:00Z", "2026-09-02T07:00:00Z")
    deep = sleep(4, "2026-09-01T23:30:00Z", "2026-09-02T00:30:00Z")
    awake = sleep(2, "2026-09-02T01:00:00Z", "2026-09-02T01:10:00Z")
    await ingest_healthkit(db_session, user, token, delta([asleep, deep, awake,
        sleep(1, "2026-09-01T22:00:00Z", "2026-09-02T07:00:00Z", source="iPhone")]))
    row = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id, SleepSession.origin == SOURCE))
    assert row.local_date == date(2026, 9, 2)
    assert row.total_sleep_s == 8 * 3600 - 600 and row.deep_s == 3600 and row.awake_s == 600
    other = SleepSession(user_id=user.id, origin="garmin", local_date=date(2026, 9, 2),
        start_time=datetime(2026, 9, 1, 22, tzinfo=UTC), end_time=datetime(2026, 9, 2, 6, tzinfo=UTC), total_sleep_s=28000)
    db_session.add(other)
    await db_session.flush()
    ids = (await db_session.scalars(select(HealthKitSample.uuid).where(HealthKitSample.user_id == user.id))).all()
    await ingest_healthkit(db_session, user, token, delta(deletions=ids, checkpoint=1))
    assert await db_session.scalar(select(SleepSession.id).where(SleepSession.user_id == user.id, SleepSession.origin == SOURCE)) is None
    assert await db_session.get(SleepSession, {"id": other.id, "start_time": other.start_time}) is other


async def test_deleted_sleep_invalidates_scores_and_baseline_dependents(db_session, bridge):
    from app.features.engine import compute_user_day
    from app.models.features import DailyFeature
    user, token, _ = bridge
    sleep = sample(type='HKCategoryTypeIdentifierSleepAnalysis', value=4, unit=None,
        start='2026-09-01T23:00:00Z', end='2026-09-02T07:00:00Z')
    await ingest_healthkit(db_session, user, token, delta([sleep]))
    await db_session.commit()
    day = date(2026, 9, 2)
    computed = await compute_user_day(db_session, user, day)
    assert computed['daily']['sleep_architecture_score'] is not None
    # Later snapshots can incorporate the deleted date in their baselines.
    db_session.add_all([DailyFeature(user_id=user.id, date=day + timedelta(days=30), recovery_score=80),
        DailyFeature(user_id=user.id, date=day + timedelta(days=31), recovery_score=70)])
    await db_session.commit()
    await ingest_healthkit(db_session, user, token, delta(deletions=[sleep['uuid']], checkpoint=1))
    await db_session.commit()
    dates = (await db_session.scalars(select(DailyFeature.date).where(DailyFeature.user_id == user.id))).all()
    assert dates == [day + timedelta(days=31)]


async def test_erasing_garmin_preserves_explicit_other_provider_wellness(db_session, bridge):
    from app.api.lab_assets import source_preview, erase_source
    from app.schemas.changes import ApproveIn
    user, token, _ = bridge
    native_sleep = sample(type='HKCategoryTypeIdentifierSleepAnalysis', value=4, unit=None,
        start='2026-09-01T23:00:00Z', end='2026-09-02T07:00:00Z')
    await ingest_healthkit(db_session, user, token, delta([
        sample(kind='RestingHeartRate', value=55, unit='count/min'), sample(), native_sleep]))
    mixed = DailyBiometric(user_id=user.id, date=date(2026, 9, 3))
    set_biometric(mixed, 'weight_kg', 72, 'whoop')
    set_biometric(mixed, 'steps', 500, 'garmin')
    legacy = DailyBiometric(user_id=user.id, date=date(2026, 9, 4), resting_hr=52)
    hrv = HrvReading(user_id=user.id, timestamp=datetime(2026, 9, 1, 7, tzinfo=UTC),
        hrv_ms=50, reading_type='overnight_avg', origin='oura', method='RMSSD')
    sleep = SleepSession(user_id=user.id, origin='garmin', local_date=date(2026, 9, 5),
        start_time=datetime(2026, 9, 4, 23, tzinfo=UTC), end_time=datetime(2026, 9, 5, 7, tzinfo=UTC), total_sleep_s=28000)
    db_session.add_all([mixed, legacy, hrv, sleep,
        FeedState(user_id=user.id, provider='oura', feed='sleep', availability='permission_denied')])
    await db_session.commit()
    preview = await source_preview(db_session, user.id, 'garmin')
    mixed.steps = 501  # Same counts, no observation revision: approval must expire.
    await db_session.commit()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as stale:
        await erase_source('garmin', ApproveIn(payload_hash=preview['payload_hash']), session=db_session, user=user)
    assert stale.value.status_code == 409
    await db_session.rollback()
    await db_session.refresh(user)
    preview = await source_preview(db_session, user.id, 'garmin')
    await erase_source('garmin', ApproveIn(payload_hash=preview['payload_hash']), session=db_session, user=user)
    owner_id = user.id
    db_session.expire_all()
    native = await db_session.get(DailyBiometric, {'user_id': owner_id, 'date': date(2026, 9, 1)})
    assert native.resting_hr == 55 and native.steps == 1000
    preserved = await db_session.get(DailyBiometric, {'user_id': owner_id, 'date': date(2026, 9, 3)})
    assert float(preserved.weight_kg) == 72 and preserved.steps is None
    assert await db_session.scalar(select(SleepSession.id).where(SleepSession.user_id == owner_id, SleepSession.origin == SOURCE)) is not None
    assert await db_session.scalar(select(SleepSession.id).where(SleepSession.user_id == owner_id, SleepSession.origin == 'garmin')) is None
    assert await db_session.scalar(select(HrvReading.id).where(HrvReading.user_id == owner_id, HrvReading.origin == 'oura')) is not None
    assert await db_session.scalar(select(FeedState.availability).where(FeedState.user_id == owner_id, FeedState.provider == 'oura')) == 'permission_denied'
    assert await db_session.scalar(select(FeedState.id).where(FeedState.user_id == owner_id, FeedState.provider == SOURCE)) is not None
    assert await db_session.get(DailyBiometric, {'user_id': owner_id, 'date': date(2026, 9, 4)}) is None


async def test_workout_reconciliation_and_safe_multi_source_deletion(db_session, bridge):
    user, token, _ = bridge
    running = await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    start = datetime(2026, 9, 1, 9, tzinfo=UTC)
    existing = Activity(user_id=user.id, discipline_id=running, start_time=start,
        start_tz_offset_minutes=0, local_date=start.date(), duration_s=1800, distance_m=5000)
    db_session.add(existing)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=existing.id, source="garmin", external_id="run"))
    await db_session.flush()
    workout = sample(type="HKWorkoutType", value=None, unit=None, workout_activity_type=37,
        start="2026-09-01T09:00:00Z", end="2026-09-01T09:30:00Z",
        metadata={"workout_summary": {"distance_m": 5200, "total_energy_kcal": 300}})
    await ingest_healthkit(db_session, user, token, delta([workout]))
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == user.id))).all()) == 1
    assert float(existing.distance_m) == 5000
    await ingest_healthkit(db_session, user, token, delta(deletions=[workout["uuid"]], checkpoint=1))
    assert await db_session.get(Activity, existing.id) is existing
    assert SOURCE not in existing.source_metrics
    # A standalone automatic workout disappears when its sole source is deleted.
    solo = {**workout, "uuid": str(uuid4()), "start_at": "2026-09-02T09:00:00Z", "end_at": "2026-09-02T09:30:00Z"}
    await ingest_healthkit(db_session, user, token, delta([solo], checkpoint=2))
    await ingest_healthkit(db_session, user, token, delta(deletions=[solo["uuid"]], checkpoint=3))
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == user.id))).all()) == 1


@pytest.mark.parametrize('native_sport,existing_sport', [(3000, 'running'), (37, None)])
async def test_unknown_workout_disciplines_never_merge_on_time_alone(db_session, bridge, native_sport, existing_sport):
    user, token, _ = bridge
    discipline = await db_session.scalar(select(Discipline.id).where(Discipline.name == existing_sport)) if existing_sport else None
    start = datetime(2026, 9, 1, 9, tzinfo=UTC)
    existing = Activity(user_id=user.id, discipline_id=discipline, start_time=start,
        start_tz_offset_minutes=0, local_date=start.date(), duration_s=1800,
        source_metrics={'garmin': {'sport': existing_sport}})
    db_session.add(existing)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=existing.id, source='garmin', external_id=str(uuid4())))
    await db_session.flush()
    workout = sample(type='HKWorkoutType', value=None, unit=None, workout_activity_type=native_sport,
        start='2026-09-01T09:00:00Z', end='2026-09-01T09:30:00Z')
    await ingest_healthkit(db_session, user, token, delta([workout]))
    assert len((await db_session.scalars(select(Activity).where(Activity.user_id == user.id))).all()) == 2
    native_link = await db_session.scalar(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id,
        ActivitySourceLink.source == SOURCE))
    assert native_link.activity_id != existing.id
    assert SOURCE not in existing.source_metrics


async def test_scoped_bearer_required_disabled_revoked_expired_denied(client, db_session, bridge):
    user, token, raw = bridge
    headers = {"Authorization": f"Bearer {raw}"}
    assert (await client.get("/healthkit/status", headers=headers)).status_code == 200
    assert (await client.get("/healthkit/status")).status_code == 401
    assert (await client.get("/watch/today", headers=headers)).status_code == 401
    for field, value in (("scope", "watch_read"), ("revoked_at", datetime.now(UTC)),
                         ("absolute_expires_at", datetime.now(UTC) - timedelta(seconds=1))):
        old = getattr(token, field)
        setattr(token, field, value)
        await db_session.commit()
        assert (await client.get("/healthkit/status", headers=headers)).status_code == 401
        setattr(token, field, old)
        await db_session.commit()
    credential = await db_session.get(AuthCredential, user.id)
    credential.disabled = True
    await db_session.commit()
    assert (await client.get("/healthkit/status", headers=headers)).status_code == 401


async def test_pairing_web_csrf_one_use_expiry_and_cookie_free_exchange(client, db_session):
    await reset_owner_auth_state(db_session)
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    assert (await client.post("/healthkit/pairings")).status_code == 403
    pairing = await client.post("/healthkit/pairings", headers=csrf_headers(client))
    assert pairing.status_code == 201
    code = pairing.json()["code"]
    assert len(code) >= 32
    # Valid browser credentials cannot cross the native auth boundary.
    assert (await client.post("/healthkit/exchange", json={"code": code, "name": "iPhone"}, headers=csrf_headers(client))).status_code in {400, 403}
    client.cookies.clear()
    exchanged = await client.post("/healthkit/exchange", json={"code": code, "name": "iPhone"})
    assert exchanged.status_code == 200
    assert exchanged.json()["checkpoint"] == 0
    assert (await client.post("/healthkit/exchange", json={"code": code})).status_code == 401
    stored = await db_session.scalar(select(HealthKitPairing).where(HealthKitPairing.code_hash == hash_session_token(code, get_settings().session_secret)))
    assert stored.consumed_at is not None and stored.code_hash != code
    expired = new_session_token()
    db_session.add(HealthKitPairing(user_id=stored.user_id, code_hash=hash_session_token(expired, get_settings().session_secret), expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db_session.commit()
    assert (await client.post("/healthkit/exchange", json={"code": expired})).status_code == 401


async def test_concurrent_retry_is_exactly_once_and_failed_batch_rolls_back(client, db_session, bridge):
    import asyncio
    user, token, raw = bridge
    headers = {"Authorization": f"Bearer {raw}"}
    item = sample()
    body = delta([item]).model_dump(mode="json")
    replies = await asyncio.gather(*[client.post("/healthkit/deltas", json=body, headers=headers) for _ in range(2)])
    assert [r.status_code for r in replies] == [200, 200]
    assert replies[0].json() == replies[1].json() == {"checkpoint": 1, "accepted": 1, "deleted": 0}
    failed = delta([sample(), {**item, "value": 2222}], checkpoint=1)
    assert (await client.post("/healthkit/deltas", json=failed.model_dump(mode="json"), headers=headers)).status_code == 409
    await db_session.refresh(token)
    assert token.sync_checkpoint == 1
    assert len((await db_session.scalars(select(HealthKitSample).where(HealthKitSample.user_id == user.id))).all()) == 1
    assert len((await db_session.scalars(select(HealthKitBatch).where(HealthKitBatch.device_id == token.id))).all()) == 1
    state = await db_session.scalar(select(FeedState).where(FeedState.user_id == user.id, FeedState.provider == SOURCE))
    assert state.cursor == {"device_id": token.id, "checkpoint": 1}
    assert "uuid" not in str(state.details) and "metadata" not in str(state.details)


async def test_management_requires_session_csrf_and_owner_scope(client, db_session, bridge):
    _, foreign_token, raw = bridge
    assert (await client.get("/healthkit/devices", headers={"Authorization": f"Bearer {raw}"})).status_code == 401
    await reset_owner_auth_state(db_session)
    assert (await login(client, os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])).status_code == 200
    listed = await client.get("/healthkit/devices")
    assert listed.status_code == 200
    assert foreign_token.id not in [row["id"] for row in listed.json()]
    assert "token_hash" not in listed.text and '"token":' not in listed.text
    assert (await client.delete(f"/healthkit/devices/{foreign_token.id}", headers=csrf_headers(client))).status_code == 404
    assert (await client.delete(f"/healthkit/devices/{foreign_token.id}")).status_code == 403
    # A paired owner device can be revoked, and its bearer immediately fails.
    pairing = await client.post("/healthkit/pairings", headers=csrf_headers(client))
    code = pairing.json()["code"]
    saved_cookies = list(client.cookies.jar)
    client.cookies.clear()
    exchanged = await client.post("/healthkit/exchange", json={"code": code})
    device = exchanged.json()
    for cookie in saved_cookies:
        client.cookies.jar.set_cookie(cookie)
    assert (await client.delete(f'/healthkit/devices/{device["device_id"]}', headers=csrf_headers(client))).status_code == 204
    client.cookies.clear()
    assert (await client.get("/healthkit/status", headers={"Authorization": f'Bearer {device["token"]}'})).status_code == 401


async def test_native_body_limit_and_validation_do_not_echo_payload(client, bridge):
    _, _, raw = bridge
    headers = {"Authorization": f"Bearer {raw}", "Content-Type": "application/json"}
    response = await client.post("/healthkit/deltas", content=b"x" * (2 * 1024 * 1024 + 1), headers=headers)
    assert response.status_code == 413
    private_marker = "private-health-sample-do-not-echo"
    body = delta().model_dump(mode="json")
    body["additions"] = [sample(metadata={"private": private_marker}, unit="invalid")]
    response = await client.post("/healthkit/deltas", json=body, headers=headers)
    assert response.status_code == 422 and private_marker not in response.text


def test_equal_values_are_attributed_to_the_actual_writer_and_legacy_is_unknown():
    row = DailyBiometric(user_id=1, date=date(2026, 9, 1), resting_hr=55)
    assert biometric_origin(row, "resting_hr") is None
    set_biometric(row, "resting_hr", 55, SOURCE)
    row.source_metrics = {**row.source_metrics, SOURCE: {"canonical_supplier_fields": {"resting_hr": {"value": 55}}}}
    set_biometric(row, "resting_hr", 55, "garmin")
    assert biometric_origin(row, "resting_hr") == "garmin"
    assert "resting_hr" not in row.source_metrics[SOURCE]["canonical_supplier_fields"]
    set_biometric(row, "resting_hr", None, "garmin")
    assert biometric_origin(row, "resting_hr") is None


async def test_equal_value_provider_refresh_survives_healthkit_deletion(db_session, bridge):
    user, token, _ = bridge
    item = sample(kind="RestingHeartRate", value=55, unit="count/min")
    await ingest_healthkit(db_session, user, token, delta([item]))
    bio = await db_session.get(DailyBiometric, {"user_id": user.id, "date": date(2026, 9, 1)})
    assert biometric_origin(bio, "resting_hr") == SOURCE
    set_biometric(bio, "resting_hr", 55, "garmin")
    await ingest_healthkit(db_session, user, token, delta(deletions=[item["uuid"]], checkpoint=1))
    assert bio.resting_hr == 55 and biometric_origin(bio, "resting_hr") == "garmin"


async def test_deletion_preview_invalidates_same_count_ledger_change(db_session, bridge):
    from app.api.lab_assets import erase_source, source_preview
    from app.schemas.changes import ApproveIn
    from fastapi import HTTPException
    user, token, _ = bridge
    await ingest_healthkit(db_session, user, token, delta([sample(kind="HeartRate", value=100, unit="count/min")]))
    original = await source_preview(db_session, user.id, SOURCE)
    row = await db_session.scalar(select(HealthKitSample).where(HealthKitSample.user_id == user.id))
    replacement = uuid4()
    row.uuid = replacement
    row.payload = {**row.payload, "uuid": str(replacement), "value": 105}
    await db_session.flush()
    refreshed = await source_preview(db_session, user.id, SOURCE)
    assert refreshed["counts"] == original["counts"]
    assert refreshed["content_revision"] != original["content_revision"]
    assert refreshed["payload_hash"] != original["payload_hash"]
    with pytest.raises(HTTPException) as stale:
        await erase_source(SOURCE, ApproveIn(payload_hash=original["payload_hash"]), db_session, user)
    assert stale.value.status_code == 409


async def test_source_erasure_revokes_native_access_and_preserves_other_sources(db_session, bridge, client):
    from app.api.lab_assets import erase_source, source_preview
    from app.schemas.changes import ApproveIn
    user, token, raw = bridge
    day = date(2026, 9, 1)
    bio = DailyBiometric(user_id=user.id, date=day, weight_kg=73)
    db_session.add(bio)  # Unattributed legacy field must survive erasure.
    await db_session.flush()
    running = await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    workout = Activity(user_id=user.id, discipline_id=running, start_time=datetime(2026, 9, 1, 9, tzinfo=UTC),
        local_date=day, start_tz_offset_minutes=0, duration_s=1800, distance_m=5000)
    db_session.add(workout)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=workout.id, source="garmin", external_id=str(uuid4())))
    native_workout = sample(type="HKWorkoutType", value=None, unit=None, workout_activity_type=37,
        start="2026-09-01T09:00:00Z", end="2026-09-01T09:30:00Z")
    await ingest_healthkit(db_session, user, token, delta([sample(), sample(kind="BodyMass", value=72, unit="kg"),
        sample(kind="RestingHeartRate", value=55, unit="count/min"), native_workout,
        sample(type="HKCategoryTypeIdentifierSleepAnalysis", value=1, unit=None, start="2026-09-01T23:00:00Z", end="2026-09-02T07:00:00Z")]))
    set_biometric(bio, "resting_hr", 55, "garmin")
    # Separate user's ledger must be unaffected by account-scoped erasure.
    foreign = User(name="healthkit-erasure-foreign", timezone="UTC")
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(HealthKitSample(user_id=foreign.id, uuid=uuid4(), payload={"foreign": True}, deleted=False, received_at=datetime.now(UTC)))
    pending = new_session_token()
    db_session.add(HealthKitPairing(user_id=user.id, code_hash=hash_session_token(pending, get_settings().session_secret), expires_at=datetime.now(UTC) + timedelta(minutes=10)))
    await db_session.flush()
    preview = await source_preview(db_session, user.id, SOURCE)
    assert preview["counts"]["healthkit_samples"] == 5
    assert preview["counts"]["healthkit_batches"] == 1
    assert "Revoke" in preview["scope"] and "Preserve" in preview["scope"]
    result = await erase_source(SOURCE, ApproveIn(payload_hash=preview["payload_hash"]), db_session, user)
    assert result["state"] == "deleted"
    await db_session.refresh(token)
    assert token.revoked_at is not None
    assert (await client.get("/healthkit/status", headers={"Authorization": f"Bearer {raw}"})).status_code == 401
    assert (await client.post("/healthkit/exchange", json={"code": pending})).status_code == 401
    assert await db_session.scalar(select(HealthKitSample.uuid).where(HealthKitSample.user_id == user.id)) is None
    assert await db_session.scalar(select(HealthKitBatch.id).where(HealthKitBatch.device_id == token.id)) is None
    assert await db_session.scalar(select(HealthKitPairing.id).where(HealthKitPairing.user_id == user.id)) is None
    assert await db_session.scalar(select(HealthKitSample.uuid).where(HealthKitSample.user_id == foreign.id)) is not None
    await db_session.refresh(bio)
    assert bio.steps is None and float(bio.weight_kg) == 73 and bio.resting_hr == 55
    assert SOURCE not in (bio.source_metrics or {})
    assert biometric_origin(bio, "resting_hr") == "garmin"
    assert await db_session.scalar(select(SleepSession.id).where(SleepSession.user_id == user.id, SleepSession.origin == SOURCE)) is None
    assert await db_session.scalar(select(Observation.id).where(Observation.user_id == user.id, Observation.origin == SOURCE)) is None
    assert await db_session.get(Activity, workout.id) is workout
    await db_session.refresh(workout)
    assert float(workout.distance_m) == 5000
    links = (await db_session.scalars(select(ActivitySourceLink.source).where(ActivitySourceLink.activity_id == workout.id))).all()
    assert links == ["garmin"]


async def test_account_export_contains_only_active_healthkit_data_without_tokens(db_session, bridge):
    from app.api.lab_assets import export_account
    import json
    user, token, raw = bridge
    active, deleted_item = sample(), sample(start="2026-09-02T06:00:00Z", end="2026-09-02T07:00:00Z")
    await ingest_healthkit(db_session, user, token, delta([active, deleted_item]))
    await ingest_healthkit(db_session, user, token, delta(deletions=[deleted_item["uuid"]], checkpoint=1))
    response = await export_account(db_session, user)
    content = json.loads(response.body)
    assert [row["uuid"] for row in content["healthkit_samples"]] == [active["uuid"]]
    assert content["healthkit_samples"][0]["payload"]["source_bundle"] == "com.apple.health"
    assert raw not in response.body.decode() and token.token_hash not in response.body.decode()
    assert "device_tokens" not in content and "healthkit_pairings" not in content and "healthkit_batches" not in content
