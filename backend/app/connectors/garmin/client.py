"""Garmin authentication facade and unofficial Connect transport.

The sync pipeline depends on the `GarminTransport` protocol in `transport.py`.
Automated tests inject fixture-backed clients and never call Garmin live.
`LiveGarminClient` handles the unofficial `garminconnect` session while
`GarminConnectTransport` owns calls and response adaptation. The library is
imported lazily, so this module remains importable when it is not installed.

Real-account connection is performed manually by the owner (§23 Phase 1
acceptance): see tools/garmin_sync.py.
"""

import asyncio
import json
import logging
from typing import Any, Callable

from app.connectors.garmin.transport import GarminTransport
from app.core.config import get_settings

logger = logging.getLogger("connectors.garmin.client")


class GarminAuthError(Exception):
    """Raised when the live client cannot authenticate."""


# Keep the former protocol import stable for existing callers.
GarminClient = GarminTransport


class GarminConnectTransport:
    """Unofficial Garmin Connect API calls and response-shape adaptation."""

    def __init__(self, gc_client: Any) -> None:
        self._gc = gc_client

    async def _call(self, operation, method, *args):
        try:
            return await asyncio.to_thread(method, *args)
        except Exception as exc:
            # Fixed operation and exception class only, never request arguments,
            # provider response text, URLs, credentials or measurement dates.
            logger.error("Garmin fetch failed (%s, %s)", operation, type(exc).__name__,
                         extra={"error_code": type(exc).__name__, "fetch_operation": operation})
            raise

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        return await self._call("activity_summaries", self._gc.get_activities, start, limit)

    async def get_activity_exercise_sets(self, activity_id: int) -> dict[str, Any]:
        return await self._call("exercise_sets", self._gc.get_activity_exercise_sets, activity_id)

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        # garminconnect 0.3.x returns activityDetailMetrics aligned with
        # metricDescriptors. Keep converting at this provider boundary so the
        # sync pipeline and fixture clients retain their established shape.
        payload = await self._call("activity_streams", self._gc.get_activity_details, str(activity_id))
        if not isinstance(payload, dict):
            return []
        samples = payload.get("samples")
        if samples is None:
            legacy_keys = {
                "directTimestamp": "timestamp",
                "directHeartRate": "heartRate",
                "directPower": "power",
                "directCadence": "cadence",
                "directSpeed": "speed",
                "directElevation": "altitude",
                "directLatitude": "positionLat",
                "directLongitude": "positionLong",
            }
            descriptors = [
                d.get("key")
                for d in (payload.get("metricDescriptors") or [])
                if isinstance(d, dict)
            ]
            rebuilt: list[dict[str, Any]] = []
            for row in payload.get("activityDetailMetrics") or []:
                values = row.get("metrics") if isinstance(row, dict) else None
                if not isinstance(values, list):
                    continue
                sample: dict[str, Any] = {}
                for key, value in zip(descriptors, values):
                    name = legacy_keys.get(key)
                    if name is not None and value is not None:
                        sample[name] = value
                if sample:
                    rebuilt.append(sample)
            samples = rebuilt
        return samples if isinstance(samples, list) else []

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        return await self._call("sleep", self._gc.get_sleep_data, local_date)

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        return await self._call("hrv", self._gc.get_hrv_data, local_date)

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        return await self._call("stress", self._gc.get_stress_data, local_date)

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        return await self._call("stats", self._gc.get_stats_and_body, local_date)

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        return await self._call("body_composition", self._gc.get_body_composition, local_date)


class LiveGarminClient:
    """Unofficial-API client, garminconnect >= 0.3.13 (native-token era).

    Authentication:

    - `from_tokens(dump)`: resume a previously stored session
      (credentials_encrypted path — preferred; no password needed). The dump
      is the 0.3.x native-token triple (di_token / di_refresh_token /
      di_client_id) — NOT the pre-0.3 garth oauth1/oauth2 pair.
    - `from_password(email, password, prompt_mfa)`: fresh login, used once by
      the owner's manual `tools/garmin_sync.py connect` step. `prompt_mfa` is
      an optional callback returning the one-time code when the account has
      MFA enabled (the CLI wires input()).

    Tokens are NOT cached here — the caller owns persisting them encrypted.
    """

    def __init__(
        self,
        _gc_client: Any,
        *,
        transport: GarminTransport | None = None,
    ) -> None:
        self._gc = _gc_client
        self._transport = (
            transport if transport is not None else GarminConnectTransport(_gc_client)
        )

    @classmethod
    def from_tokens(cls, garth_dump: dict[str, Any]) -> "LiveGarminClient":
        gc_client = cls._new_garmin()
        if not garth_dump.get("di_token") or not garth_dump.get("di_refresh_token"):
            raise GarminAuthError(
                "stored Garmin token dump is missing di_token/di_refresh_token "
                "(garminconnect 0.3.x native-token format) — re-run "
                "tools/garmin_sync.py connect to refresh"
            )
        try:
            # login(tokenstore=JSON) loads the native tokens AND the profile —
            # resuming straight on client.loads would skip profile load.
            gc_client.login(tokenstore=json.dumps(garth_dump))
        except Exception as exc:  # noqa: BLE001 — the lib raises bare http errors
            raise GarminAuthError(f"stored Garmin tokens rejected: {exc}") from exc
        return cls(gc_client)

    @classmethod
    def from_password(
        cls,
        email: str,
        password: str,
        prompt_mfa: Callable[[], str] | None = None,
    ) -> "LiveGarminClient":
        if not email or not password:
            raise GarminAuthError(
                "Garmin credentials missing: set GARMIN_EMAIL/GARMIN_PASSWORD or "
                "run tools/garmin_sync.py connect first"
            )
        gc_client = cls._new_garmin(email=email, password=password, prompt_mfa=prompt_mfa)
        try:
            needs_mfa, _ = gc_client.login()
        except Exception as exc:  # noqa: BLE001 — garminconnect raises bare urllib/http errors
            raise GarminAuthError(f"Garmin login failed: {exc}") from exc
        if needs_mfa:
            raise GarminAuthError(
                "Garmin account requires MFA and no prompt_mfa callback was "
                "provided — connect via tools/garmin_sync.py connect, which "
                "collects the one-time code interactively"
            )
        return cls(gc_client)

    def dump_tokens(self) -> dict[str, Any]:
        """Return the native-token session dump for the caller to encrypt
        and store (garminconnect 0.3.x replaced garth's oauth1/oauth2 with
        the di_token triple)."""
        c = self._gc.client
        dump: dict[str, Any] = {
            "di_token": c.di_token,
            "di_refresh_token": c.di_refresh_token,
        }
        client_id = getattr(c, "di_client_id", None)
        if client_id:
            dump["di_client_id"] = client_id
        return dump

    @staticmethod
    def _new_garmin(
        email: str | None = None,
        password: str | None = None,
        prompt_mfa: Callable[[], str] | None = None,
    ) -> Any:
        try:
            from garminconnect import Garmin
        except ImportError as exc:  # pragma: no cover - depends on env
            raise GarminAuthError(
                "garminconnect is not installed in this environment"
            ) from exc
        # 0.3.x: credentials go to the constructor (the old logfile kwarg and
        # login(email, password) signature are gone).
        return Garmin(email=email, password=password, prompt_mfa=prompt_mfa)

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        return await self._transport.get_activities(start, limit)

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        return await self._transport.get_activity_samples(activity_id)

    async def get_activity_exercise_sets(self, activity_id: int) -> dict[str, Any]:
        return await self._transport.get_activity_exercise_sets(activity_id)

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        return await self._transport.get_sleep_data(local_date)

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        return await self._transport.get_hrv_data(local_date)

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        return await self._transport.get_stress_data(local_date)

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        return await self._transport.get_stats(local_date)

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        return await self._transport.get_body_composition(local_date)


# The old concrete class name remains the public integration surface for the
# CLI and settings API. The Garmin Connect qualifier makes the unofficial
# transport explicit for new call sites.
GarminConnectClient = LiveGarminClient


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
