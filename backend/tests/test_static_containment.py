"""Static fallback must stay within its exact public directory."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import _mount_spa


@pytest.mark.asyncio
async def test_spa_does_not_serve_sibling_files_or_symlinks(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("public app")
    (dist / "favicon.txt").write_text("public asset")
    sibling = tmp_path / "dist-private"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("private fixture")
    (dist / "outside.txt").symlink_to(sibling / "secret.txt")
    monkeypatch.setenv("SPA_DIST_DIR", str(dist))
    app = FastAPI()
    _mount_spa(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        asset = await client.get("/favicon.txt")
        assert asset.text == "public asset"
        for url in ("/%2e%2e/dist-private/secret.txt", "/outside.txt"):
            response = await client.get(url)
            assert "private fixture" not in response.text
            assert response.text == "public app"
