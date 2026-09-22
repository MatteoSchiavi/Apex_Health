"""FastAPI application factory (MASTER_SPEC §2, §18)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    auth,
    challenges,
    coach,
    gear,
    health,
    imports,
    integrations,
    labs,
    schedule,
    settings,
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
    return app


app = create_app()
