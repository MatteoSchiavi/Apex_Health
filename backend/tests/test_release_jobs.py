"""Queue contracts, account ownership and real Celery retry semantics."""

import os
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
    user = User(name="oura-job")
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
    result = await _sync_account("oura", user.id)
    assert received == [credentials]
    assert result["status"] == "ok"
    await db_session.refresh(integration)
    assert integration.last_synced_at is not None
