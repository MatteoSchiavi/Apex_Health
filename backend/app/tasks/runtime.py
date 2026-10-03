"""Run async Celery jobs without carrying pooled connections across loops."""

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.db import engine


def run_async(job: Coroutine[Any, Any, Any]) -> Any:
    async def run():
        try:
            return await job
        finally:
            # asyncio.run creates a fresh loop for each task. asyncpg connections
            # belong to their creating loop and cannot survive into the next job.
            await engine.dispose()
    return asyncio.run(run())
