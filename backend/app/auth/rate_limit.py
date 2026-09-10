"""Redis-backed sliding-window login rate limiting (MASTER_SPEC §22.1).

Five failed attempts per email per 15 minutes triggers a temporary lockout.
The window is a Redis ZSET of failure timestamps; the DB-side counters
(auth_credentials.failed_login_count / locked_until) are kept in sync by the
auth service so lockout state survives a Redis flush.
"""

import time

from redis.asyncio import Redis

from app.core.config import Settings


class LoginRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    def _key(self, email: str) -> str:
        return f"login:fails:{email.lower()}"

    def _window_seconds(self) -> int:
        return self._settings.login_window_minutes * 60

    async def window_failures(self, email: str) -> int:
        """Number of failed attempts inside the current sliding window."""
        key = self._key(email)
        now = time.time()
        await self._redis.zremrangebyscore(key, 0, now - self._window_seconds())
        return int(await self._redis.zcard(key))

    async def is_locked(self, email: str) -> bool:
        return await self.window_failures(email) >= self._settings.login_max_attempts

    async def record_failure(self, email: str) -> int:
        """Record a failure; returns the updated window count."""
        key = self._key(email)
        now = time.time()
        await self._redis.zremrangebyscore(key, 0, now - self._window_seconds())
        await self._redis.zadd(key, {str(now): now})
        return int(await self._redis.zcard(key))

    async def reset(self, email: str) -> None:
        await self._redis.delete(self._key(email))
