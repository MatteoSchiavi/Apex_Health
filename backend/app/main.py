"""FastAPI application factory (MASTER_SPEC §2, §18)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    activities,
    auth,
    challenges,
    chats,
    coach,
    dashboard,
    devices,
    gear,
    health,
    imports,
    integrations,
    labs,
    me,
    metrics,
    schedule,
    settings,
    sleep,
    watch,
    weather,
)
from app.auth.service import ensure_owner
from app.core.config import get_settings
from app.core.db import engine, sessionmaker
from app.core.logging import configure_logging
from app.core.middleware import CSRFMiddleware, ProxyHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # §15: owner account is bootstrapped from OWNER_EMAIL/OWNER_PASSWORD at startup.
    async with sessionmaker() as session:
        await ensure_owner(session)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Health Control Center", lifespan=lifespan)
    app.add_middleware(CSRFMiddleware)
    # §15: behind Tailscale Funnel/Caddy, honor X-Forwarded-* from the local
    # terminator when configured to (infra/tailscale-funnel-setup.md).
    app.add_middleware(ProxyHeadersMiddleware, trusted=get_settings().trust_proxy_headers)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(labs.router)
    app.include_router(gear.router)
    app.include_router(integrations.router)
    app.include_router(schedule.router)
    app.include_router(settings.router)
    app.include_router(coach.router)
    app.include_router(challenges.router)
    app.include_router(imports.router)
    app.include_router(watch.router)
    app.include_router(weather.router)
    # Web UI surface (migration 0007 / STACK.md §3)
    app.include_router(me.router)
    app.include_router(dashboard.router)
    app.include_router(activities.router)
    app.include_router(sleep.router)
    app.include_router(metrics.router)
    app.include_router(chats.router)
    app.include_router(devices.router)
    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built SPA (frontend/dist) with a history-API fallback.

    Zero runtime cost when dist/ is absent (dev against `npm run dev`); in
    Docker the image build stage bakes dist in and the API serves it — one
    process, no nginx, no Node (STACK.md §2.1). API routes, /docs and
    /health are matched before the fallback, so they always win.
    """
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    env_dir = os.environ.get("SPA_DIST_DIR", "")
    dist = Path(env_dir) if env_dir else (
        Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    if not (dist / "index.html").exists():
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Real files (favicon, fonts, service worker) win; anything else is a
        # client-side route and gets index.html.
        candidate = (dist / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and str(candidate).startswith(str(dist.resolve()))
        ):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
