"""MCP connection stores only the authenticated account's verified token."""
import os
from sqlalchemy import select
from app.core.config import get_settings
from app.core.encryption import decrypt_json
from app.models.integration import Integration
from app.models.user import AuthCredential
from tests.conftest import csrf_headers, login


async def test_coros_connect_is_account_scoped_and_never_uses_oauth(client, db_session, monkeypatch):
    from app.connectors.coros import client as connector
    settings = get_settings()
    monkeypatch.setattr(settings, 'coros_mcp_url', 'https://mcp.example.test/mcp')
    monkeypatch.setattr(settings, 'coros_mcp_activity_tool', 'read_activities')
    received = []
    class FakeClient:
        async def fetch_activities(self):
            return {'structuredContent': {'activities': []}}
    def build(credentials):
        received.append(dict(credentials))
        return FakeClient()
    monkeypatch.setattr(connector, 'build_live_client', build)
    assert (await client.get('/settings/integrations/coros/mcp/status')).status_code == 401
    await login(client, os.environ['OWNER_EMAIL'], os.environ['OWNER_PASSWORD'])
    assert (await client.get('/settings/integrations/coros/mcp/status')).json() == {'configured': True}
    response = await client.post('/settings/integrations/coros/mcp/connect',
                                 json={'access_token': 'account-mcp-token'}, headers=csrf_headers(client))
    assert response.status_code == 200
    assert received == [{'mcp_access_token': 'account-mcp-token'}]
    assert 'account-mcp-token' not in response.text
    owner = await db_session.scalar(select(AuthCredential.user_id).where(AuthCredential.role == 'owner'))
    row = await db_session.scalar(select(Integration).where(Integration.user_id == owner, Integration.provider == 'coros'))
    assert row.status == 'active'
    assert decrypt_json(row.credentials_encrypted) == {'mcp_access_token': 'account-mcp-token'}
    assert (await client.post('/settings/integrations/coros/authorize', headers=csrf_headers(client))).status_code == 410


async def test_coros_connect_rejects_unconfigured_or_invalid_server_without_saving(client, db_session, monkeypatch):
    from app.connectors.coros import client as connector
    settings = get_settings()
    await login(client, os.environ['OWNER_EMAIL'], os.environ['OWNER_PASSWORD'])
    monkeypatch.setattr(settings, 'coros_mcp_url', '')
    response = await client.post('/settings/integrations/coros/mcp/connect', json={'access_token':'secret'}, headers=csrf_headers(client))
    assert response.status_code == 409
    monkeypatch.setattr(settings, 'coros_mcp_url', 'https://mcp.example.test/mcp')
    monkeypatch.setattr(settings, 'coros_mcp_activity_tool', 'read_activities')
    class FakeClient:
        async def fetch_activities(self):
            return {'structuredContent': {'unknown': 'secret'}}
    monkeypatch.setattr(connector, 'build_live_client', lambda credentials: FakeClient())
    response = await client.post('/settings/integrations/coros/mcp/connect', json={'access_token':'secret'}, headers=csrf_headers(client))
    assert response.status_code == 422
    assert 'secret' not in response.text


async def test_browser_oauth_returns_to_devices_and_api_clients_keep_json(client, monkeypatch):
    from app.api import integrations
    async def complete(*args, **kwargs):
        return {'connected': True, 'provider': 'whoop'}
    monkeypatch.setattr(integrations, 'whoop_complete', complete)
    path = '/integrations/whoop/callback?code=approved&state=single-use-state'
    browser = await client.get(path, headers={'Accept': 'text/html'}, follow_redirects=False)
    assert browser.status_code == 303
    assert browser.headers['location'] == '/app/settings?tab=devices'
    api = await client.get(path, headers={'Accept': 'application/json'})
    assert api.status_code == 200
    assert api.json() == {'connected': True, 'provider': 'whoop'}
