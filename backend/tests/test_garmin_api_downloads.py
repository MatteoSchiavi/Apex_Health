"""Synthetic official-API responses; never call a Garmin account."""
import base64
import gzip
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo
import httpx
import pytest
from app.connectors.garmin.personal import GarminPersonalError, GarminPersonalClient
from app.connectors.garmin.client import GarminAuthError
from app.connectors.garmin.original import decode_original
from app.connectors.garmin.normalize import NormalizationError
from tests.test_garmin_personal import client_for, token

@pytest.fixture(scope="session", autouse=True)
def migrated_database(): pass
@pytest.fixture(scope="session", autouse=True)
def owner_account(): pass
@pytest.fixture(autouse=True)
def clean_redis(): pass


def envelope(content, activity_id=123):
    return {"activity_id": activity_id, "sha256": hashlib.sha256(content).hexdigest(),
            "content": base64.b64encode(content).decode(), "encoding": "base64"}


def zipped(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items(): archive.writestr(name, value)
    return out.getvalue()


async def test_archive_bytes_and_account_bearer_are_preserved():
    calls = []
    original = zipped({'activity.fit': b'original-fit-bytes'})
    def respond(request):
        calls.append(request)
        if request.method == 'POST': return httpx.Response(200, text=token())
        assert request.url.host == 'personal.connectapi.garmin.com'
        assert request.url.path == '/download-service/files/activity/123'
        assert request.headers['Authorization'].startswith('Bearer ')
        return httpx.Response(200, content=original)
    client = client_for(respond)
    try:
        payload = await client.get_activity_archive(123)
        assert base64.b64decode(payload['content']) == original
        assert payload['activity_id'] == 123
        assert decode_original(payload) == b'original-fit-bytes'
        assert len(calls) == 2
    finally: await client.aclose()


@pytest.mark.parametrize('status,error', [(403, GarminPersonalError), (404, GarminPersonalError), (302, GarminPersonalError), (401, GarminAuthError)])
async def test_failed_download_is_not_recorded_as_missing_data(status, error):
    client = client_for(lambda request: httpx.Response(200, text=token()) if request.method == 'POST' else httpx.Response(status, text='private-provider-body'))
    try:
        with pytest.raises(error) as failure: await client.get_activity_archive(123)
        assert 'private-provider-body' not in str(failure.value)
        if status == 401: assert client.dump_tokens().get('access_token') is None
    finally: await client.aclose()


async def test_decoded_response_size_and_compressed_json():
    client = client_for(lambda request: httpx.Response(200, content=gzip.compress(b'{"totalSteps":123}'), headers={'Content-Encoding':'gzip'}))
    try:
        response = await client._request('GET', '/unit-test', 'Bearer synthetic', max_bytes=100)
        assert response.json() == {'totalSteps':123}
        with pytest.raises(GarminPersonalError, match='size'):
            await client._request('GET', '/unit-test', 'Bearer synthetic', max_bytes=10)
    finally: await client.aclose()


@pytest.mark.parametrize('content', [b'bad zip', zipped({'a.fit':b'a','b.fit':b'b'}), zipped({'readme.txt':b'a'})])
def test_invalid_or_ambiguous_archive_is_rejected(content):
    with pytest.raises(NormalizationError): decode_original(envelope(content))


def test_hash_and_uncompressed_member_limit(monkeypatch):
    payload = envelope(zipped({'../activity.fit':b'a'*100}))
    # No filesystem extraction; a filename cannot escape an archive reader.
    assert decode_original(payload) == b'a'*100
    monkeypatch.setattr('app.connectors.garmin.original.MAX_FIT_BYTES', 99)
    with pytest.raises(NormalizationError): decode_original(payload)
    payload['sha256'] = 'wrong'
    with pytest.raises(NormalizationError): decode_original(payload)


async def test_every_requested_endpoint_and_query_is_in_official_contract(monkeypatch):
    contract = json.loads((Path(__file__).parent/'fixtures/garmin/personal_api_contract.json').read_text())
    seen = set()
    def respond(request):
        if request.method == 'POST': return httpx.Response(200, text=token())
        candidates = [p for p in contract['paths'] if re.fullmatch(re.sub(r'\{[^}]+\}', '[^/]+', p), request.url.path)]
        assert len(candidates) == 1, request.url.path
        path = candidates[0]
        assert set(request.url.params) <= set(contract['paths'][path]['query'])
        seen.add(path)
        if path.startswith('/weight-service'): return httpx.Response(200, json={'dailyWeightSummaries':[]})
        if path.startswith('/activitylist'): return httpx.Response(200, json=[])
        if path.startswith('/download'): return httpx.Response(204)
        if '/dayview/' in path: assert request.url.params['todayDate'] == '2026-11-06'
        return httpx.Response(200, json={'retained':'source-value'})
    monkeypatch.setattr('app.connectors.garmin.personal.asyncio.sleep', AsyncMock())
    client = client_for(respond)
    try:
        documents, errors = await client.get_api_documents('2026-11-05', today='2026-11-06')
        assert len(documents) == 15 and not errors
        assert all(d['payload'] == {'retained':'source-value'} for d in documents.values())
        assert len((await client.get_api_documents('2026-11-05', today='2026-11-06'))[0]) == 13
        await client.get_activity_documents(123)
        await client.get_activity_archive(123)
        await client.get_activities(0,25)
        await client.get_sleep_data('2026-11-05')
        await client.get_hrv_data('2026-11-05')
        await client.get_stats('2026-11-05')
        await client.get_body_composition('2026-11-05')
        # Range alternatives provide the same core data; /all is incompatible
        # with the documented October account check and deliberately not used.
        alternatives = {'/hrv-service/hrv/daily/{fromDate}/{toDate}', '/sleep-service/sleep/dailySleepSummariesByDate', '/weight-service/weight/all/{startDate}/{endDate}'}
        assert seen | alternatives == set(contract['paths'])
        assert GarminPersonalClient.initial_sync_days is None
    finally: await client.aclose()


async def test_optional_permission_failure_is_explicit_and_other_data_survives(monkeypatch):
    monkeypatch.setattr('app.connectors.garmin.personal.asyncio.sleep', AsyncMock())
    def respond(request):
        if request.method == 'POST': return httpx.Response(200,text=token())
        if '/food/' in request.url.path: return httpx.Response(403,text='private')
        return httpx.Response(200,json={'kept':True})
    client = client_for(respond)
    try:
        documents, errors = await client.get_api_documents('2026-11-05')
        assert 'hydration' in documents and 'food_logs' not in documents
        assert errors == {'food_logs': {'error_class':'permission','status_code':403}}
    finally: await client.aclose()


async def test_failed_wellness_feed_is_not_an_empty_history_boundary(monkeypatch):
    from app.connectors.garmin import sync
    client = SimpleNamespace(get_sleep_data=AsyncMock(side_effect=GarminPersonalError('safe',status_code=403)),
        get_hrv_data=AsyncMock(return_value={}), get_stats=AsyncMock(return_value={'totalSteps':123}),
        get_body_composition=AsyncMock(return_value={}), unsupported_capabilities={'stress_timeseries'})
    store = AsyncMock()
    monkeypatch.setattr(sync.fetch, 'store_raw', store)
    report = sync.SyncReport(user_id=9,mode='backfill')
    await sync.fetch_wellness(None,9,client,ZoneInfo('UTC'),from_day=date(2026,11,5),to_day=date(2026,1,1),delay_s=0,empty_gap_days=10,report=report)
    assert store.await_args.args[2] == 'stats:2026-11-05'
    assert report.wellness_feeds_failed == 1
    assert any('paused' in note for note in report.notes)
    assert not any('empty days' in note for note in report.notes)


async def test_failed_historical_day_is_retried_even_when_other_feed_already_has_rows(monkeypatch):
    from app.connectors.garmin import sync
    failed = date(2026,11,4)
    client = SimpleNamespace(wellness_retry_day=failed.isoformat(),
        get_sleep_data=AsyncMock(return_value={}), get_hrv_data=AsyncMock(return_value={}),
        get_stats=AsyncMock(return_value={}),get_body_composition=AsyncMock(return_value={}),
        unsupported_capabilities={'stress_timeseries'})
    # The canonical marker would otherwise skip November 4 after November 5.
    session = SimpleNamespace(scalar=AsyncMock(return_value=1),commit=AsyncMock())
    monkeypatch.setattr(sync,'normalize_pending',AsyncMock())
    report = sync.SyncReport(user_id=9,mode='backfill')
    await sync.fetch_wellness(session,9,client,ZoneInfo('UTC'),from_day=date(2026,11,5),to_day=failed,
        delay_s=0,empty_gap_days=10,report=report,discipline_index={},checkpoint=True)
    assert client.get_sleep_data.await_count == 2
    assert client.get_sleep_data.await_args.args == ('2026-11-04',)
