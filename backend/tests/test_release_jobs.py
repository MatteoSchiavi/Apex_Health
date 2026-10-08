"""Queue contracts, account ownership and real Celery retry semantics."""

import os
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.encryption import encrypt_json
from app.models.integration import Integration
from app.models.user import AuthCredential, User
from app.tasks.provider_sync import SyncTaskError, _sync_account
from tests.conftest import csrf_headers, reset_owner_auth_state


async def test_sync_now_is_queued_and_job_status_is_scoped(client, db_session, monkeypatch):
    await reset_owner_auth_state(db_session)
    await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]})
    owner = await db_session.scalar(select(AuthCredential).where(AuthCredential.role == "owner"))
    integration = await db_session.scalar(select(Integration).where(Integration.user_id == owner.user_id, Integration.provider == "garmin"))
    if integration is None:
        integration = Integration(user_id=owner.user_id, provider="garmin")
        db_session.add(integration)
    integration.status = "active"
    integration.credentials_encrypted = encrypt_json({"unused": "fixture"})
    await db_session.commit()
    published = []
    def publish(*, args, task_id):
        published.append((args, task_id))
        return SimpleNamespace(id=task_id)
    monkeypatch.setattr("app.tasks.garmin_sync.sync_user_garmin.apply_async", publish)
    response = await client.post("/settings/integrations/garmin/sync", headers=csrf_headers(client))
    assert response.status_code == 202
    body = response.json()
    assert body["completed"] is False
    assert published == [([owner.user_id], body["job_id"])]
    monkeypatch.setattr("app.tasks.celery_app.celery_app.AsyncResult", lambda _: SimpleNamespace(state="FAILURE", result=RuntimeError("private-provider-secret")))
    status = await client.get(body["status_url"])
    assert status.status_code == 200
    assert status.json()["state"] == "FAILURE"
    assert "private-provider-secret" not in status.text
    # An unregistered/foreign ID never triggers a Celery result lookup.
    assert (await client.get("/settings/integrations/garmin/sync/foreign-job")).status_code == 404


async def test_missing_credentials_never_use_global_owner_credentials(db_session, monkeypatch):
    user = User(name="missing-provider-credentials")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Integration(user_id=user.id, provider="garmin", status="active"))
    await db_session.commit()
    calls = []
    monkeypatch.setattr("app.connectors.garmin.client.build_live_client", lambda credentials: calls.append(credentials))
    with pytest.raises(SyncTaskError, match="No stored"):
        await _sync_account("garmin", user.id)
    assert calls == []


async def test_disabled_account_does_not_fetch_or_enqueue_provider_data(db_session, monkeypatch):
    from app.tasks.provider_sync import enqueue_active
    user = User(name='Disabled provider account'); db_session.add(user); await db_session.flush()
    db_session.add_all([
        AuthCredential(user_id=user.id,email=f'disabled-{user.id}@example.com',password_hash='unused',role='friend',disabled=True),
        Integration(user_id=user.id,provider='garmin',status='active',credentials_encrypted=encrypt_json({'unused':'fixture'})),
    ])
    await db_session.commit()
    factory = lambda *_: pytest.fail('Disabled account must not open a provider client')
    monkeypatch.setattr('app.connectors.garmin.client.build_live_client', factory)
    assert (await _sync_account('garmin',user.id))['reason'] == 'Account disabled'
    published = []
    monkeypatch.setattr('app.tasks.provider_sync.celery_app.send_task',lambda name, args: published.append(args) or SimpleNamespace(id='fixture'))
    await enqueue_active('garmin')
    assert [user.id] not in published


def test_celery_sync_retries_then_reports_failure(monkeypatch):
    from app.tasks.garmin_sync import sync_user_garmin
    attempts = []
    def fail(job):
        attempts.append(job.cr_code.co_name)
        job.close()
        raise SyncTaskError("Provider temporarily unavailable")
    monkeypatch.setattr("app.tasks.provider_sync.run_async", fail)
    result = sync_user_garmin.apply(args=[123], throw=False)
    assert result.state == "FAILURE"
    assert attempts.count('sync_account') == 4  # initial sync plus three retries
    assert attempts.count('critical_connector_error') == 1


async def test_oura_driver_uses_stored_credentials_and_real_sync(db_session, monkeypatch):
    user = User(name="oura-job", timezone="Pacific/Auckland")
    db_session.add(user)
    await db_session.flush()
    credentials = {"access_token": "fixture", "refresh_token": "fixture-refresh"}
    integration = Integration(user_id=user.id, provider="oura", status="active",
                              credentials_encrypted=encrypt_json(credentials))
    db_session.add(integration)
    await db_session.commit()
    class EmptyOura:
        tokens_out = None
        async def fetch_daily_sleep(self, *args): return []
        async def fetch_sleep_periods(self, *args): return []
        async def fetch_heartrate(self, *args): return []
        async def fetch_personal_info(self): return {}
    received = []
    def factory(value):
        received.append(value)
        return EmptyOura()
    monkeypatch.setattr("app.connectors.oura.client.build_live_client", factory)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026,10,8,13,tzinfo=UTC)
    monkeypatch.setattr('app.tasks.provider_sync.datetime', Clock)
    refreshes = []
    async def refresh(session, athlete, start, end):
        assert (await session.get(Integration,integration.id)).last_synced_at is not None
        refreshes.append((athlete.id,start,end))
    monkeypatch.setattr('app.features.engine.compute_user_range', refresh)
    result = await _sync_account("oura", user.id)
    assert received == [credentials]
    assert result["status"] == "ok"
    await db_session.refresh(integration)
    assert integration.last_synced_at is not None
    assert refreshes == [(user.id,date(2026,9,11),date(2026,10,9))]


async def test_failed_backfill_refreshes_committed_today_data_without_claiming_sync_success(db_session, monkeypatch):
    from datetime import timedelta
    from app.models.features import DailyFeature
    from app.models.wellness import SleepSession
    user = User(name='Checkpointed wellness', timezone='Europe/Rome')
    db_session.add(user); await db_session.flush()
    integration = Integration(user_id=user.id, provider='garmin', status='active',
                              credentials_encrypted=encrypt_json({'fixture':'owned'}))
    db_session.add(integration); await db_session.commit()
    now = datetime(2026,10,8,8,tzinfo=UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return now
    monkeypatch.setattr('app.tasks.provider_sync.datetime', Clock)
    monkeypatch.setattr('app.connectors.garmin.client.build_live_client', lambda _: SimpleNamespace())
    async def partial_checkpoint(session, athlete, connection, client, **kwargs):
        session.add(SleepSession(user_id=athlete.id, origin='garmin', local_date=now.date(),
            start_time=now-timedelta(hours=8),end_time=now,total_sleep_s=8*3600))
        historical_end = now - timedelta(days=100)
        session.add(SleepSession(user_id=athlete.id, origin='garmin', local_date=historical_end.date(),
            start_time=historical_end-timedelta(hours=8), end_time=historical_end, total_sleep_s=8*3600))
        connection.consecutive_failures = 1
        await session.commit()  # A later upstream call fails after this durable checkpoint.
        return None
    monkeypatch.setattr('app.connectors.garmin.sync.run_user_sync_with_escalation', partial_checkpoint)
    with pytest.raises(SyncTaskError, match='Provider sync failed'):
        await _sync_account('garmin', user.id)
    feature = await db_session.get(DailyFeature, (user.id, now.date()), populate_existing=True)
    assert feature is not None and feature.data_completeness == 'partial'
    assert feature.calculation_provenance['as_of'] == '2026-10-08'
    historic = await db_session.get(DailyFeature, (user.id, (now-timedelta(days=100)).date()), populate_existing=True)
    assert historic is not None and historic.calculation_provenance['as_of'] == (now-timedelta(days=100)).date().isoformat()
    await db_session.refresh(integration)
    assert integration.last_synced_at is None and integration.consecutive_failures == 1
