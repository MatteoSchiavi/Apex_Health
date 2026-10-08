"""Health endpoint (MASTER_SPEC §18, §21): public, checks DB + Redis connectivity."""

import asyncio
import os
import re

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.db import sessionmaker
from app.core.redis import get_redis
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/version")
async def version(response: Response) -> dict[str, str]:
    """Public release identity; contains no account or deployment secrets."""
    response.headers["Cache-Control"] = "no-store"
    commit = os.environ.get("APEX_COMMIT", "development")
    return {"version": "0.1.0", "stage": "beta", "commit":
            commit if re.fullmatch(r"[0-9a-f]{40}", commit) else "development"}


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    db_ok, redis_ok = await asyncio.gather(_check_db(), _check_redis())

    all_ok = db_ok and redis_ok
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db="ok" if db_ok else "error",
        redis="ok" if redis_ok else "error",
    )


async def _check_redis() -> bool:
    redis: Redis = get_redis()
    try:
        await asyncio.wait_for(redis.ping(), timeout=2)
        return True
    except Exception:
        return False
    finally:
        await redis.aclose()

async def _check_db() -> bool:
    try:
        async with asyncio.timeout(2):
            async with sessionmaker() as session:
                await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
