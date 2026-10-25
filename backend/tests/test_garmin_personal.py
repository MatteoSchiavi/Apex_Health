"""Network-free public-schema examples, not live account validation."""
import base64
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.connectors.garmin.client import GarminAuthError, build_live_client
from app.connectors.garmin.personal import GarminPersonalClient, GarminPersonalError, TOKEN_PATH


# Transport/normalizer unit tests do not require or reset external services.
@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    pass


@pytest.fixture(scope="session", autouse=True)
def owner_account():
    pass


@pytest.fixture(autouse=True)
def clean_redis():
    pass


def token(exp=None):
    claims = base64.urlsafe_b64encode(json.dumps({"exp": exp or time.time() + 7200}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


def client_for(handler, **credentials):
    return GarminPersonalClient({"auth_type": "personal_api_key", "api_key": "private-key", **credentials},
                                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_key_exchange_and_account_scoped_token_reuse():
    requests = []
    jwt = token()
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=jwt) if request.method == "POST" else httpx.Response(200, json={"totalSteps": 7000})
    client = client_for(respond)
    try:
        await client.get_stats("2026-10-24")
        await client.get_stats("2026-10-23")
        assert [r.method for r in requests] == ["POST", "GET", "GET"]
        assert requests[0].url.path == TOKEN_PATH
        assert requests[0].headers["Authorization"] == "ApiKey private-key"
        assert requests[1].headers["Authorization"] == f"Bearer {jwt}"
        assert requests[1].url.params["calendarDate"] == "2026-10-24"
        dumped = client.dump_tokens()
        assert dumped["api_key"] == "private-key" and dumped["auth_type"] == "personal_api_key"
        assert dumped["expires_at"] <= time.time() + 86400
        assert "private-key" not in repr(client)
    finally:
        await client.aclose()
    assert client._http.is_closed


async def test_checkpoint_normalization_keeps_one_cumulative_sport_notice():
    from app.connectors.garmin.sync import SyncReport, normalize_pending
    from app.connectors.garmin.normalize import NormalizerStats
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    report = SyncReport(user_id=7, mode="backfill", notes=["Personal API pilot window"])
    report.stats = NormalizerStats(discipline_fallbacks=["synthetic:unknown_sport"])
    for _ in range(30):
        await normalize_pending(session, 7, ZoneInfo("UTC"), {}, report)
    assert report.notes == ["Personal API pilot window", "discipline fallback used for: synthetic:unknown_sport"]


async def test_expired_cache_is_renewed_and_24h_lifetime_is_capped():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=token(time.time() + 172800))
    client = client_for(respond, access_token=token(time.time() - 5), expires_at=time.time() + 172800)
    try:
        await client.authenticate(force=False)
        assert len(requests) == 1
        assert 86390 < client.dump_tokens()["expires_at"] - time.time() <= 86400
    finally:
        await client.aclose()


async def test_revocation_reexchanges_once_and_does_not_leak_credentials():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=token()) if request.method == "POST" else httpx.Response(401, text="private-key provider-secret")
    client = client_for(respond)
    try:
        with pytest.raises(GarminAuthError) as error:
            await client.get_stats("2026-10-24")
        assert [r.method for r in requests] == ["POST", "GET", "POST", "GET"]
        assert "private-key" not in str(error.value) and "provider-secret" not in str(error.value)
        assert "access_token" not in client.dump_tokens()
    finally:
        await client.aclose()


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_invalid_key_fails_without_retry_or_provider_body(status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="private-key")
    client = client_for(respond)
    try:
        with pytest.raises(GarminAuthError, match="rejected or expired") as error:
            await client.authenticate()
        assert len(calls) == 1 and "private-key" not in str(error.value)
    finally:
        await client.aclose()


@pytest.mark.parametrize("status", [429, 503, "timeout"])
async def test_transient_failures_are_bounded_and_sanitized(status, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.connectors.garmin.personal.asyncio.sleep", sleep)
    calls = []
    def respond(request):
        calls.append(request)
        if status == "timeout":
            raise httpx.ReadTimeout("private-key", request=request)
        return httpx.Response(status, text="private-key", headers={"Retry-After": "999999"})
    client = client_for(respond)
    try:
        with pytest.raises(GarminPersonalError) as error:
            await client.authenticate()
        assert len(calls) == 3 and sleep.await_count == 2
        assert all(call.args[0] <= 30 for call in sleep.await_args_list)
        assert "private-key" not in str(error.value)
        assert error.value.error_class == ("timeout" if status == "timeout" else "transport")
    finally:
        await client.aclose()


async def test_instances_do_not_share_credentials_or_auth_headers():
    seen = []
    def respond(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, text=token())
    a, b = client_for(respond), client_for(respond, api_key="second-key")
    try:
        await a.authenticate()
        await b.authenticate()
        assert seen == ["ApiKey private-key", "ApiKey second-key"]
        assert a.dump_tokens()["api_key"] != b.dump_tokens()["api_key"]
    finally:
        await a.aclose()
        await b.aclose()


async def test_factory_selects_personal_without_network(monkeypatch):
    monkeypatch.setattr(GarminPersonalClient, "authenticate", AsyncMock(side_effect=AssertionError("network during factory")))
    client = build_live_client({"auth_type": "personal_api_key", "api_key": "private-key"})
    try:
        assert isinstance(client, GarminPersonalClient)
        client.authenticate.assert_not_called()
    finally:
        await client.aclose()


async def test_schema_mapping_reaches_canonical_sleep_and_weight(monkeypatch):
    from app.connectors.garmin import normalize
    original_sleep = {"calendarDate": "2026-10-24", "sleepStartTimestampGMT": "2026-10-23T22:00:00Z",
                      "sleepEndTimestampGMT": "2026-10-24T06:00:00Z", "sleepTimeSeconds": 28000,
                      "deepSleepSeconds": 4500, "sleepScores": {"overall": {"value": 85}},
                      "averageRespirationValue": 14, "averageSpO2Value": 97}
    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, text=token())
        if request.url.path.startswith("/sleep-service"):
            return httpx.Response(200, json=original_sleep)
        assert request.url.path == "/weight-service/weight/range/2026-10-24/2026-10-24"
        assert request.url.params["includeAll"] == "true"
        return httpx.Response(200, json={"dailyWeightSummaries":[{"summaryDate":"2026-10-24", "allWeightMetrics":[{"calendarDate": "2026-10-24", "weight": 73.5, "bodyFat": 18.2}]}], "previousDateWeight":{"weight":90}})
    client = client_for(respond)
    saved = []
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), add=saved.append)
    monkeypatch.setattr(normalize, "_can_write_biometric", AsyncMock(return_value=True))
    try:
        sleep = await client.get_sleep_data("2026-10-24")
        raw = SimpleNamespace(id=1, user_id=4, payload_type="sleep")
        counts = normalize.NormalizerStats()
        await normalize._upsert_sleep(session, raw, sleep, ZoneInfo("Europe/Berlin"), counts)
        assert saved[0].start_time == datetime(2026, 10, 23, 22, tzinfo=UTC)
        assert saved[0].respiration_avg == 14 and saved[0].spo2_avg == 97
        assert saved[0].deep_s == 4500 and saved[0].rem_s is None
        assert saved[0].origin == "garmin" and saved[0].user_id == 4
        assert sleep["_personal_api_payload"] == original_sleep
        weight = await client.get_body_composition("2026-10-24")
        raw.payload_type = "body_composition:2026-10-24"
        await normalize._upsert_biometrics(session, raw, weight, "body_composition", counts)
        assert saved[-1].weight_kg == 73.5 and saved[-1].body_fat_pct == 18.2
    finally:
        await client.aclose()


async def test_activity_identifiers_units_and_hrv_204():
    activity = {"activityId": 12345, "startTimeGMT": "2026-10-23 15:00:00", "duration": 3600.5,
                "distance": 10000, "activityType": {"typeKey": "running"}, "vO2MaxValue": 49}
    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, text=token())
        if request.url.path.startswith("/hrv-service"):
            return httpx.Response(204)
        assert request.url.params["start"] == "0" and request.url.params["limit"] == "25"
        return httpx.Response(200, json=[activity])
    client = client_for(respond)
    try:
        assert await client.get_activities(0, 25) == [activity]
        assert await client.get_hrv_data("2026-10-24") == {}
        with pytest.raises(NotImplementedError):
            await client.get_activity_samples(12345)
        with pytest.raises(NotImplementedError):
            await client.get_stress_data("2026-10-24")
    finally:
        await client.aclose()


async def test_capability_skips_do_not_fabricate_empty_stream_records():
    from app.connectors.garmin.sync import fetch_streams, fetch_strength_sets, SyncReport
    client = client_for(lambda request: pytest.fail("unsupported data must not be requested"))
    report = SyncReport(user_id=4, mode="incremental")
    session = SimpleNamespace(scalar=AsyncMock(side_effect=AssertionError("unsupported must not write not_measured")))
    try:
        await fetch_streams(session, 4, client, ["12345"], 0, report)
        await fetch_strength_sets(session, 4, client, "12345", 0, report)
        assert report.streams_failed == report.streams_fetched == report.raw_rows_stored == 0
    finally:
        await client.aclose()


@pytest.mark.parametrize("payload", ["private-key", '"private-key"', '{"access_token":"private-key"}'])
async def test_token_exchange_rejects_non_jwt_without_disclosing_body(payload):
    client = client_for(lambda request: httpx.Response(200, text=payload))
    try:
        with pytest.raises(GarminAuthError) as error:
            await client.authenticate()
        assert "private-key" not in str(error.value)
        assert "access_token" not in client.dump_tokens()
    finally:
        await client.aclose()


async def test_redirects_are_not_followed_and_permission_is_not_an_empty_day():
    for status, error_class in [(302, "transport"), (403, "permission"), (404, "transport")]:
        calls = []
        def respond(request):
            calls.append(request)
            if request.method == "POST":
                return httpx.Response(200, text=token())
            return httpx.Response(status, headers={"Location": "https://untrusted.example"}, text="private-key")
        client = client_for(respond)
        try:
            with pytest.raises(GarminPersonalError) as error:
                await client.get_stats("2026-10-24")
            assert error.value.error_class == error_class and len(calls) == 2
            assert "private-key" not in str(error.value)
        finally:
            await client.aclose()


async def test_hrv_schema_normalizes_utc_readings_and_nightly_average():
    from app.connectors.garmin.normalize import _upsert_hrv, NormalizerStats
    body = {"hrvSummary": {"calendarDate": "2026-10-24", "lastNightAvg": 52},
            "hrvReadings": [{"readingTimeGMT": "2026-10-24T05:50:00.000", "hrvValue": 55}]}
    client = client_for(lambda request: httpx.Response(200, text=token()) if request.method == "POST" else httpx.Response(200, json=body))
    saved = []
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), add=saved.append)
    try:
        payload = await client.get_hrv_data("2026-10-24")
        await _upsert_hrv(session, SimpleNamespace(id=1, user_id=9, payload_type="hrv"), payload, NormalizerStats(), ZoneInfo("Europe/Berlin"))
        assert [row.hrv_ms for row in saved] == [55, 52]
        assert [row.reading_type for row in saved] == ["5min", "overnight_avg"]
        assert all(row.timestamp == datetime(2026, 10, 24, 5, 50, tzinfo=UTC) for row in saved)
        assert all(row.user_id == 9 and row.origin == "garmin" for row in saved)
    finally:
        await client.aclose()


async def test_wellness_sync_uses_supported_feeds_and_keeps_daily_stress(monkeypatch):
    from datetime import date
    from app.connectors.garmin import sync
    requests, stored = [], []
    def respond(request):
        requests.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(200, text=token())
        if request.url.path.startswith("/hrv-service"):
            return httpx.Response(204)
        if request.url.path.startswith("/weight-service"):
            return httpx.Response(200, json={"dailyWeightSummaries": [], "previousDateWeight":{"weight":90}, "totalAverage":{"weight":None}})
        if request.url.path.startswith("/usersummary-service"):
            return httpx.Response(200, json={"calendarDate": "2026-10-24", "averageStressLevel": 25, "bodyBatteryMostRecentValue": 60})
        return httpx.Response(200, json={})
    async def store(session, user_id, kind, payload):
        stored.append((user_id, kind, payload))
    monkeypatch.setattr(sync.fetch, "store_raw", store)
    client = client_for(respond)
    report = sync.SyncReport(user_id=9, mode="incremental")
    try:
        await sync.fetch_wellness(None, 9, client, ZoneInfo("UTC"), from_day=date(2026, 10, 24), to_day=date(2026, 10, 24), delay_s=0, empty_gap_days=1, report=report)
        assert len(requests) == 5  # exchange + four supported daily feeds
        assert stored == [(9, "stats:2026-10-24", {"calendarDate": "2026-10-24", "averageStressLevel": 25, "bodyBatteryMostRecentValue": 60})]
        assert report.wellness_days == 1 and report.raw_rows_stored == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("personal,last_sync,expected_start", [
    (True, None, "2026-09-25"),
    (True, datetime(2026, 1, 1, tzinfo=UTC), "2026-09-25"),
    (True, datetime(2026, 10, 23, tzinfo=UTC), "2026-10-22"),
    (False, None, "2026-10-24"),
])
async def test_personal_sync_is_bounded_without_changing_legacy_backfill(monkeypatch, personal, last_sync, expected_start):
    from app.connectors.garmin import sync
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    activities, wellness = AsyncMock(return_value=[]), AsyncMock()
    monkeypatch.setattr(sync, "fetch_activities", activities)
    monkeypatch.setattr(sync, "fetch_wellness", wellness)
    monkeypatch.setattr(sync, "fetch_streams", AsyncMock())
    monkeypatch.setattr(sync, "normalize_pending", AsyncMock())
    recovered = AsyncMock(return_value=[])
    monkeypatch.setattr(sync, "_external_ids_missing_streams", recovered)
    monkeypatch.setattr("app.services.evidence.update_feed", AsyncMock())
    feed = SimpleNamespace(details={}, last_success_at=None)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])), scalar=AsyncMock(return_value=feed))
    client = SimpleNamespace(initial_sync_days=30, unsupported_capabilities=GarminPersonalClient.unsupported_capabilities) if personal else SimpleNamespace()
    integration = SimpleNamespace(last_synced_at=last_sync)
    report = await sync.sync_user_garmin(session, SimpleNamespace(id=9, timezone="Europe/Berlin"), integration, client,
                                        page_size=25, page_delay_s=0, empty_gap_days=7, now=now, checkpoint=True)
    assert wellness.await_args.kwargs["from_day"].isoformat() == expected_start
    if personal:
        assert wellness.await_args.kwargs["to_day"].isoformat() == "2026-10-24"
        assert activities.await_args.kwargs["oldest_allowed"].astimezone(UTC) == datetime(2026, 9, 24, 22, tzinfo=UTC)
        assert "older history is not imported" in report.notes[0]
        recovered.assert_not_awaited()
    else:
        assert activities.await_args.kwargs["since"] is None
        assert activities.await_args.kwargs["oldest_allowed"] is None
        assert wellness.await_args.kwargs["to_day"].year < 1930
        recovered.assert_awaited_once()
    assert integration.last_synced_at == now


async def test_activity_window_does_not_import_old_rows_from_boundary_page(monkeypatch):
    from app.connectors.garmin import sync
    page = [{"activityId": 1, "startTimeGMT": "2026-10-24 10:00:00", "duration": 600},
            {"activityId": 2, "startTimeGMT": "2026-09-01 10:00:00", "duration": 600}]
    client = SimpleNamespace(get_activities=AsyncMock(return_value=page))
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    store = AsyncMock()
    monkeypatch.setattr(sync.fetch, "store_raw", store)
    cutoff = datetime(2026, 9, 25, tzinfo=UTC)
    ids = await sync.fetch_activities(session, 9, client, since=cutoff, oldest_allowed=cutoff, page_size=2,
                                      delay_s=0, report=sync.SyncReport(user_id=9, mode="backfill"))
    assert ids == ["1"] and store.await_count == 1
    assert store.await_args.args[-1]["activityId"] == 1
    client.get_activities.assert_awaited_once()


async def test_activity_schema_power_cadence_and_manual_aliases_keep_originals():
    original = {"activityId": 12345, "avgPower": 210, "normPower": 225,
                "averageRunningCadenceInStepsPerMinute": 178, "isManualActivity": False,
                "summarizedExerciseSets": [{"category": "SQUAT", "sets": 3, "reps": 15, "volume": 750000}]}
    client = client_for(lambda request: httpx.Response(200, text=token()) if request.method == "POST" else httpx.Response(200, json=[original]))
    try:
        result = (await client.get_activities(0, 25))[0]
        assert result["averagePower"] == 210 and result["normalizedPower"] == 225
        assert result["averageRunCadence"] == 178 and result["manual"] is False
        assert all(result[key] == value for key, value in original.items())
        assert "exerciseSets" not in result  # aggregates are not individual sets
    finally:
        await client.aclose()
