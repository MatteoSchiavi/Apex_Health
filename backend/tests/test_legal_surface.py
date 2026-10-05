"""Notices must load directly in the production SPA without exposing APIs."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.legal import router
from app.main import _mount_spa


async def test_public_legal_config_has_only_notice_facts(client):
    response = await client.get("/legal/config")
    assert response.status_code == 200
    assert set(response.json()) == {
        "controller_name", "controller_address", "contact_email", "hosting_region",
        "effective_date", "account_basis", "health_basis", "ai_processor",
        "backup_location", "transfer_details", "details_complete",
    }
    assert "password" not in response.text
    assert "token" not in response.json()


@pytest.mark.asyncio
async def test_only_exact_legal_pages_get_spa_fallback(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("public legal SPA")
    monkeypatch.setenv("SPA_DIST_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    _mount_spa(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        for path in ("privacy", "terms", "cookies"):
            response = await client.get(f"/legal/{path}")
            assert response.status_code == 200
            assert response.text == "public legal SPA"
            assert "text/html" in response.headers["content-type"]
        response = await client.get("/legal/private-typo")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}
