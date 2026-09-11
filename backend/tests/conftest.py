"""Shared test fixtures.

Env is finalized BEFORE app modules are imported (Settings reads process env
first, .env second). The Alembic migration chain is re-applied once per test
session so every test sees a fresh, complete schema.
"""

import asyncio
import os
import stat
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

# --- env defaults (must run before any `app` import) ---
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _ensure_usable(name: str, default: str, *ok_prefixes: str) -> None:
    """Keep a deliberately exported value, replace anything unusable.

    setdefault alone is not enough: some dev sandboxes export unrelated values
    (e.g. DATABASE_URL=file:...) that would poison the SQLAlchemy URL. An
    explicit override with a real backend scheme (CI service containers) wins.
    """
    value = os.environ.get(name, "")
    if not value or not value.startswith(ok_prefixes):
        os.environ[name] = default


_ensure_usable("DATABASE_URL", "postgresql+asyncpg://hcc@localhost:5433/hcc", "postgresql")
_ensure_usable("REDIS_URL", "redis://localhost:6380/0", "redis")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("OWNER_EMAIL", "owner@apexhealth.dev")
os.environ.setdefault("OWNER_PASSWORD", "test-owner-password")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.service import ensure_owner  # noqa: E402 (after env setup)


def _run_alembic(*args: str) -> None:
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
    )


async def _wipe_domain_tables() -> None:
    """Truncate every table the migration downgrade needs empty.

    `alembic downgrade base` deletes seeded rows (disciplines, weights) and
    fails on any leftover referencing data (e.g. activities from a previous
    test session). Truncating the FK roots + global config tables first makes
    the downgrade deterministic; CASCADE clears everything hanging off
    users/disciplines. Without this, a swallowed downgrade error turns the
    following `upgrade head` into a no-op and stale rows (old weight
    versions!) leak across sessions.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE users, disciplines, feature_weights RESTART IDENTITY CASCADE")
        )
    await engine.dispose()


def _alembic_downgrade_tolerant() -> None:
    """Best-effort teardown: a fresh database has nothing to downgrade."""
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        cwd=BACKEND_DIR,
        check=False,
        capture_output=True,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Rebuild the schema from scratch for the whole session."""
    asyncio.run(_wipe_domain_tables())
    _alembic_downgrade_tolerant()
    _run_alembic("upgrade", "head")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def owner_account(migrated_database) -> AsyncIterator[None]:
    """Ensure the owner account exists (what app lifespan does at startup)."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await ensure_owner(session)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(owner_account) -> AsyncIterator[AsyncClient]:
    """ASGI client; base_url https so Secure cookies round-trip."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    """Flush Redis between tests: rate-limit windows must not leak across tests."""
    from redis.asyncio import Redis

    r = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield


async def reset_owner_auth_state(session: AsyncSession) -> None:
    """Clear lockout bookkeeping on the owner row (used by auth tests)."""
    await session.execute(
        text(
            "UPDATE auth_credentials SET failed_login_count = 0, locked_until = NULL "
            "WHERE role = 'owner'"
        )
    )
    await session.commit()


@pytest.fixture
def fake_pg_dump(tmp_path):
    """An executable stand-in for pg_dump emitting a tiny valid dump (backup tests).

    Hermetic: CI and sandboxes need no PostgreSQL toolchain — the LIVE restore
    drill is a phase demo, not a unit test.
    """
    fake_sql = (
        "--\n-- PostgreSQL database dump\n--\n\n"
        "CREATE TABLE public.daily_features (user_id integer);\n"
        "COPY public.daily_features (user_id) FROM stdin;\n"
        "42\n"
        "\\.\n"
        "-- PostgreSQL database dump complete\n"
    )
    script = tmp_path / "fake_pg_dump.sh"
    script.write_text(f"#!/bin/sh\ncat <<'SQLEOF'\n{fake_sql}SQLEOF\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)
