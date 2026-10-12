"""Hermetic sync outcome/alert contracts; no provider, database or Redis access."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.escalation import run_sync_with_escalation, sync_error_class
from app.models.admin import OwnerNotification
from app.models.alpha import AlphaEvent
from app.models.integration import Integration
from app.models.lab import FeedState
from app.services import owner_notifications
from app.services.sync_health import _account_summary, _state_from_feed
from app.tasks import provider_sync
from evals.harness import MemoryStore
from evals.scenarios import Scenario


@pytest.fixture(scope="session")
def migrated_database():
    yield


@pytest.fixture(scope="session")
def owner_account():
    yield


@pytest.fixture(autouse=True)
def clean_redis():
    yield


NOW = datetime(2026, 10, 11, 8, tzinfo=UTC)


def integration(**kwargs):
    values = dict(id=1, user_id=1, provider="garmin", status="active",
                  consecutive_failures=0, credentials_encrypted=b"SECRET")
    values.update(kwargs)
    return Integration(**values)


def feed(name="sleep", **kwargs):
    values = dict(user_id=1, provider="garmin", feed=name, availability="available", details={}, cursor={})
    values.update(kwargs)
    return FeedState(**values)


@pytest.fixture
def memory(monkeypatch):
    store = MemoryStore(Scenario("sync", "", (), (), {}))
    store.rows[Integration] = [integration()]
    monkeypatch.setattr(provider_sync, "sessionmaker", store.sessionmaker)
    monkeypatch.setattr("app.core.db.sessionmaker", store.sessionmaker)
    return store


class LockConnection:
    acquired = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def scalar(self, *args):
        return self.acquired

    async def execute(self, *args):
        return None


async def test_overlap_is_harmless_without_attempt_telemetry_or_alerts(memory, monkeypatch):
    lock = LockConnection()
    lock.acquired = False
    monkeypatch.setattr(provider_sync, "engine", SimpleNamespace(connect=lambda: lock))
    driver = AsyncMock()
    monkeypatch.setattr(provider_sync, "_sync_account", driver)
    assert await provider_sync.sync_account("garmin", 1) == {"status": "skipped", "reason": "already_running"}
    driver.assert_not_called()
    assert memory.writes == []


async def test_partial_sync_is_not_a_failure_and_warns_once_then_recovers(memory, monkeypatch):
    monkeypatch.setattr(provider_sync, "engine", SimpleNamespace(connect=LockConnection))
    outcome = {"status": "partial", "mode": "incremental", "raw_stored": 4, "streams_failed": 1, "unprocessed": 2}
    driver = AsyncMock(return_value=outcome)
    monkeypatch.setattr(provider_sync, "_sync_account", driver)
    for _ in range(2):
        assert await provider_sync.sync_account("garmin", 1) == outcome
    events = memory.rows[AlphaEvent]
    assert [row.event for row in events] == ["integration_sync_partial"] * 2
    assert memory.rows[Integration][0].consecutive_failures == 0
    account = memory.rows[FeedState][0]
    assert account.last_attempt_at is not None and account.last_success_at is not None
    assert account.availability == "partial" and account.details["streams_failed"] == 1
    assert [row.kind for row in memory.rows[OwnerNotification]] == ["connector_warning"]
    driver.return_value = {"status": "ok", "mode": "incremental", "raw_stored": 2}
    await provider_sync.sync_account("garmin", 1)
    await provider_sync.sync_account("garmin", 1)
    assert [row.kind for row in memory.rows[OwnerNotification]] == ["connector_warning", "connector_recovery"]


async def test_transient_retries_escalate_only_at_persistent_threshold(memory, monkeypatch):
    monkeypatch.setattr(provider_sync, "engine", SimpleNamespace(connect=LockConnection))
    monkeypatch.setattr(provider_sync, "_sync_account", AsyncMock(side_effect=TimeoutError("token=SECRET health=PRIVATE")))
    for attempt in range(1, 5):
        with pytest.raises(provider_sync.SyncTaskError) as raised:
            await provider_sync.sync_account("garmin", 1)
        assert raised.value.error_class == "timeout" and "SECRET" not in str(raised.value)
        assert len(memory.rows.get(OwnerNotification, [])) == (0 if attempt < 3 else 1)
    assert memory.rows[Integration][0].consecutive_failures == 4
    assert memory.rows[FeedState][0].details["error_class"] == "timeout"
    assert all(row.metadata_json == {"provider": "garmin", "error_class": "timeout"} for row in memory.rows[AlphaEvent])


async def test_authentication_alert_is_actionable_and_deduplicated(memory):
    for _ in range(3):
        await provider_sync._record_sync_outcome("garmin", 1, error_class="authentication")
    notifications = memory.rows[OwnerNotification]
    assert len(notifications) == 1 and notifications[0].kind == "connector_error"
    assert "Reconnect" in notifications[0].message and "SECRET" not in notifications[0].message


async def test_success_without_a_previous_alert_never_sends_recovery(memory):
    await provider_sync._record_sync_outcome("garmin", 1)
    assert memory.rows.get(OwnerNotification, []) == []


@pytest.mark.parametrize("error,code", [
    (TimeoutError("SECRET"), "timeout"),
    (ConnectionError("SECRET"), "transport"),
    (PermissionError("SECRET"), "permission"),
    (httpx.HTTPStatusError("SECRET", request=httpx.Request("GET", "https://example.test"), response=httpx.Response(401)), "authentication"),
    (RuntimeError("SECRET"), "unknown"),
])
async def test_escalation_retains_sanitized_failure_signal_without_critical_logs(error, code, caplog):
    connection = integration()
    session = SimpleNamespace(rollback=AsyncMock(), scalar=AsyncMock(return_value=1),
                              commit=AsyncMock(), refresh=AsyncMock(), add=lambda _: None)
    with caplog.at_level("INFO"):
        report = await run_sync_with_escalation(session, SimpleNamespace(id=1), connection,
                                               AsyncMock(side_effect=error), source_label="Garmin")
    assert report is None and connection._sync_failure_code == code
    assert sync_error_class(error) == code
    assert not any(record.levelname in {"ERROR", "CRITICAL"} for record in caplog.records)
    assert "SECRET" not in caplog.text


def test_measurement_age_does_not_turn_recent_success_into_attempt_failure():
    connection = integration(last_synced_at=NOW - timedelta(minutes=2))
    sleep = feed(last_attempt_at=NOW - timedelta(minutes=1), last_success_at=NOW - timedelta(minutes=1),
                 latest_measurement_at=NOW - timedelta(days=3))
    account = _account_summary("garmin", connection, [sleep], None, NOW)
    assert _state_from_feed(sleep, NOW) == "stale"
    assert account["state"] == "awaiting_new_data" and account["data_freshness"] == "stale"
    assert account["has_successful_sync"] is True and account["error_class"] is None


@pytest.mark.parametrize("availability,details,expected", [
    ("partial", {"streams_failed": 1}, "partial"),
    ("fetch_failed", {"error_class": "authentication"}, "auth_required"),
    ("fetch_failed", {"error_class": "timeout"}, "failed"),
    ("pending_sync", {}, "syncing"),
    ("available", {}, "successful"),
])
def test_account_states_keep_attempt_and_measurement_timestamps_distinct(availability, details, expected):
    attempt = NOW - timedelta(minutes=1)
    success = NOW - timedelta(minutes=5)
    measured = NOW - timedelta(hours=2)
    account_feed = feed("account_sync", availability=availability, details=details,
                        last_attempt_at=attempt, last_success_at=success)
    summary = _account_summary("garmin", integration(), [account_feed], measured, NOW)
    assert summary["state"] == expected and summary["last_attempt_at"] == attempt
    assert summary["last_success_at"] == success and summary["latest_measurement_at"] == measured
    assert "SECRET" not in str(summary)


def test_ingestion_evidence_prevents_never_synced_without_fabricating_attempt_time():
    measured = NOW - timedelta(hours=1)
    summary = _account_summary("garmin", integration(), [], measured, NOW)
    assert summary["has_successful_sync"] is True
    assert summary["last_success_at"] is None and summary["last_attempt_at"] is None


def test_checkpoint_then_failure_is_explicitly_partial():
    attempt = NOW - timedelta(minutes=5)
    account = feed("account_sync", availability="fetch_failed", last_attempt_at=attempt, details={"error_class": "transport"})
    sleep = feed(last_success_at=attempt + timedelta(minutes=1), latest_measurement_at=NOW - timedelta(hours=1))
    summary = _account_summary("garmin", integration(consecutive_failures=3), [account, sleep], None, NOW)
    assert summary["state"] == "partial" and summary["has_successful_sync"] is True


def test_old_attempt_and_stalled_sync_are_delayed():
    old = NOW - timedelta(days=3)
    assert _account_summary("garmin", integration(last_synced_at=old), [], old, NOW)["state"] == "delayed"
    stalled = feed("account_sync", availability="pending_sync", last_attempt_at=NOW - timedelta(hours=1))
    assert _account_summary("garmin", integration(), [stalled], None, NOW)["state"] == "delayed"


@pytest.mark.parametrize("result,expected", [
    ({"status": "partial", "mode": "incremental", "streams_failed": 1, "unprocessed": 2, "private": "SECRET"},
     {"status": "partial", "mode": "incremental", "streams_failed": 1, "unprocessed": 2}),
    ({"status": "skipped", "reason": "already_running"}, {"status": "skipped", "reason": "already_running"}),
])
async def test_job_status_exposes_partial_counts_and_safe_overlap_reason(monkeypatch, result, expected):
    from app.api.integrations import garmin_sync_status
    monkeypatch.setattr("app.tasks.celery_app.celery_app.AsyncResult", lambda _: SimpleNamespace(state="SUCCESS", result=result))
    response = await garmin_sync_status("fixture-job", provider="garmin", user=SimpleNamespace(id=1),
                                       redis=SimpleNamespace(get=AsyncMock(return_value="1")))
    assert response["state"] == "SUCCESS" and response["completed"] is True
    assert response["result"] == expected and "SECRET" not in str(response)


def test_known_sync_failure_signal_does_not_duplicate_connector_alert(caplog):
    from app.tasks.owner_notifications import capture_task_failure
    with caplog.at_level("ERROR"):
        capture_task_failure(sender=SimpleNamespace(name="garmin.sync_user"), exception=RuntimeError("SECRET"))
    assert caplog.records == []
