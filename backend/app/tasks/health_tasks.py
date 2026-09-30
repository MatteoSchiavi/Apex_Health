"""Phase 0 health task: proves the worker can reach Redis (broker round-trip)
and the database. Scheduled jobs arrive with their owning phases (§19)."""

import asyncio

from sqlalchemy import text

from app.core.db import sessionmaker
from app.tasks.celery_app import celery_app


@celery_app.task(name="health.ping")
def ping() -> dict:
    async def _check_db() -> None:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))

    asyncio.run(_check_db())
    return {"status": "ok", "db": "ok"}
