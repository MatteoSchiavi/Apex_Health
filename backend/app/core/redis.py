"""Redis client (§2: Celery + Redis; §22.1: Redis-backed rate limiting)."""

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()


def get_redis() -> Redis:
    """FastAPI dependency yielding a Redis client."""
    return Redis.from_url(settings.redis_url, decode_responses=True)
