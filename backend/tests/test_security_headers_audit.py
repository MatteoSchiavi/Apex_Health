"""Headers on HTTPS, public SPA and rejected API requests."""
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_security_headers_apply_to_public_and_authenticated_error_responses(client):
    for path in ('/health','/admin','/api/admin/users','/privacy'):
        response = await client.get(path)
        assert response.headers['x-frame-options'] == 'DENY'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
        csp = response.headers['content-security-policy']
        assert "frame-ancestors 'none'" in csp
        assert "script-src 'self'" in csp and "'sha256-" in csp
        assert "max-age=31536000" == response.headers['strict-transport-security']
    assert (await client.get('/api/admin/users')).headers['cache-control'] == 'no-store'
    for path in ('/settings/notifications', '/imports/csv', '/schedule', '/gear'):
        assert (await client.get(path)).headers['cache-control'] == 'no-store'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as plain:
        assert 'strict-transport-security' not in (await plain.get('/health')).headers
