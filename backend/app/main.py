"""FastAPI application factory (MASTER_SPEC §2, §18)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

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
from app.core.secret_validation import validate_startup_secrets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # F-12 audit: validate startup secrets BEFORE ensure_owner so a
    # misconfigured production boot fails loudly instead of creating a
    # compromised owner account from an empty/default password.
    validate_startup_secrets()
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

    # Reserved first segments: every API route prefix that exists at this
    # point (routers are all included before _mount_spa runs). A GET to an
    # UNKNOWN path under a reserved segment (/gear/999 on a GET-less route,
    # a typo'd API path) must answer JSON 404 — NOT index.html with 200,
    # which would leak HTML into API clients and mask isolation bugs.
    #
    # Route introspection walks nested structures because FastAPI keeps
    # include_router() results as lazy router wrappers whose real APIRoutes
    # (with the prefix baked in) live one level down.
    def _iter_route_paths(obj):  # type: ignore[no-untyped-def]
        path = getattr(obj, "path", None)
        if isinstance(path, str):
            yield path
        children: list = list(getattr(obj, "routes", None) or [])
        original = getattr(obj, "original_router", None)
        if original is not None:
            children.append(original)
        for child in children:
            yield from _iter_route_paths(child)

    reserved: set[str] = {"docs", "redoc", "openapi.json", "health"}
    for path in _iter_route_paths(app):
        if path and not path.startswith("/{"):
            reserved.add(path.lstrip("/").split("/", 1)[0])

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Real files (favicon, fonts, service worker) win; anything else is a
        # client-side route and gets index.html. API-shaped paths never reach
        # the fallback (see reserved above) — they 404 as JSON.
        first = full_path.split("/", 1)[0]
        if full_path and first in reserved:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        candidate = (dist / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and str(candidate).startswith(str(dist.resolve()))
        ):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
