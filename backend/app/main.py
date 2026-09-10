"""FastAPI application factory (MASTER_SPEC §2, §18)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, labs
from app.auth.service import ensure_owner
from app.core.db import engine, sessionmaker
from app.core.logging import configure_logging
from app.core.middleware import CSRFMiddleware


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
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(labs.router)
    return app


app = create_app()
