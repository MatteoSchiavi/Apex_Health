"""Acceptance tests for /health (Phase 0 criterion: /health returns 200)."""

from httpx import AsyncClient


async def test_health_returns_200_with_db_and_redis_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "db": "ok", "redis": "ok"}


async def test_health_is_public_and_csrf_exempt(client: AsyncClient):
    """§17: /health reachable without a session; it's a GET so CSRF never applies,
    but the explicit exemption guards against future method changes."""
    resp = await client.get("/health", headers={"X-Request-Source": "test"})
    assert resp.status_code == 200
