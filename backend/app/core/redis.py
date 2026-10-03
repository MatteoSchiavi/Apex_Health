"""Redis client (§2: Celery + Redis; §22.1: Redis-backed rate limiting)."""

from redis.asyncio import Redis
from collections.abc import AsyncIterator

from app.core.config import get_settings

settings = get_settings()


def get_redis() -> Redis:
    """FastAPI dependency yielding a Redis client."""
    return Redis.from_url(settings.redis_url, decode_responses=True,
                          socket_connect_timeout=3, socket_timeout=5)


async def get_redis_dependency() -> AsyncIterator[Redis]:
    """Request-scoped pool; closing it prevents leaked sockets on every API call."""
    redis = get_redis()
    try:
        yield redis
    finally:
        await redis.aclose()
