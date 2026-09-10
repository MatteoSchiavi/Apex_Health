"""Garmin client abstraction.

§0/§16.7/§20: automated tests NEVER talk to the live Garmin API — the sync
pipeline depends only on the `GarminClient` protocol and tests inject a
fixture-backed implementation. `LiveGarminClient` wraps the unofficial
`garminconnect` library (§3) and imports it lazily, so the codebase works
without it installed and no test can reach the network even by accident.

Real-account connection is performed manually by the owner (§23 Phase 1
acceptance): see tools/garmin_sync.py.
"""

import asyncio
import logging
from typing import Any, Protocol

from app.core.config import get_settings

logger = logging.getLogger("connectors.garmin.client")


class GarminAuthError(Exception):
    """Raised when the live client cannot authenticate."""


class GarminClient(Protocol):
    """The surface the sync pipeline needs. All methods are async; the live
    implementation bridges the synchronous garminconnect library via
    asyncio.to_thread."""

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        """Activity summaries, newest first, paginated (§6.3 backfill walks
        every page)."""
        ...

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        """Per-second(ish) stream samples for one activity."""
        ...

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_stress_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_stats(self, local_date: str) -> dict[str, Any]: ...

    async def get_body_composition(self, local_date: str) -> dict[str, Any]: ...


class LiveGarminClient:
    """Unofficial-API client. Authentication:

    - `from_tokens(garth_dump)`: resume a previously stored session
      (credentials_encrypted path — preferred; no password needed).
    - `from_password(email, password)`: fresh login, used once by the owner's
      manual `tools/garmin_sync.py connect` step.

    Tokens are NOT cached here — the caller owns persisting them encrypted.
    """

    def __init__(self, _gc_client: Any) -> None:
        self._gc = _gc_client

    @classmethod
    def from_tokens(cls, garth_dump: dict[str, Any]) -> "LiveGarminClient":
        gc_client = cls._new_garmin()
        oauth1, oauth2 = garth_dump.get("oauth1"), garth_dump.get("oauth2")
        if not oauth1 or not oauth2:
            raise GarminAuthError("stored garth dump is missing oauth1/oauth2 tokens")
        gc_client.garth.loads(oauth1, oauth2)
        return cls(gc_client)

    @classmethod
    def from_password(cls, email: str, password: str) -> "LiveGarminClient":
        if not email or not password:
            raise GarminAuthError(
                "Garmin credentials missing: set GARMIN_EMAIL/GARMIN_PASSWORD or "
                "run tools/garmin_sync.py connect first"
            )
        gc_client = cls._new_garmin()
        try:
            gc_client.login(email, password)
        except Exception as exc:  # garminconnect raises bare urllib/http errors
            raise GarminAuthError(f"Garmin login failed: {exc}") from exc
        return cls(gc_client)

    def dump_tokens(self) -> dict[str, Any]:
        """Return the garth session dump for the caller to encrypt and store."""
        return {"oauth1": self._gc.garth.dump()["oauth1"], "oauth2": self._gc.garth.dump()["oauth2"]}

    @staticmethod
    def _new_garmin() -> Any:
        try:
            from garminconnect import Garmin
        except ImportError as exc:  # pragma: no cover - depends on env
            raise GarminAuthError(
                "garminconnect is not installed in this environment"
            ) from exc
        return Garmin(logfile=None)

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._gc.get_activities, start, limit)

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._gc.get_activity_samples, activity_id)

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._gc.get_sleep_data, local_date)

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._gc.get_hrv_data, local_date)

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._gc.get_stress_data, local_date)

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._gc.get_stats_and_body_composition_data, local_date)

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._gc.get_body_composition, local_date)


def build_live_client(credentials: dict[str, Any] | None) -> LiveGarminClient:
    """Build the live client from stored credentials, falling back to env
    GARMIN_EMAIL/GARMIN_PASSWORD (§5) when nothing is stored yet."""
    if credentials:
        return LiveGarminClient.from_tokens(credentials)
    settings = get_settings()
    return LiveGarminClient.from_password(settings.garmin_email, settings.garmin_password)


def credentials_from_env() -> dict[str, Any] | None:
    """Credentials payload for first-time connect (owner's manual step)."""
    settings = get_settings()
    if settings.garmin_email and settings.garmin_password:
        return {"email": settings.garmin_email}
    return None
