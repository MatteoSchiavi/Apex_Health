"""Recreate dev state without Docker — invoked by scripts/reset-dev.sh.

Drops and recreates the DATABASE_URL database (via the maintenance 'postgres'
database) and flushes the REDIS_URL database. Migrations are applied
afterwards by reset-dev.sh; the owner account re-bootstraps at next API
startup (§15).
"""

import asyncio
import os

import asyncpg
from redis.asyncio import Redis


def sync_dsn(async_url: str) -> str:
    return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def reset_database(async_url: str) -> None:
    dsn, dbname = sync_dsn(async_url).rsplit("/", 1)
    admin = await asyncpg.connect(dsn + "/postgres")
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()


async def reset_redis(redis_url: str) -> None:
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()


async def main() -> None:
    await reset_database(os.environ["DATABASE_URL"])
    await reset_redis(os.environ["REDIS_URL"])
    print("dev database recreated; redis flushed")


if __name__ == "__main__":
    asyncio.run(main())
