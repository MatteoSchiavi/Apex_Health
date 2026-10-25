"""Transport boundary for Garmin ingestion.

The sync pipeline consumes this narrow asynchronous surface. The existing
Garmin Connect adapter implements it using the unofficial ``garminconnect``
library. The official owner-only Personal API client in personal.py implements
this surface with explicit unsupported capabilities. The placeholder below
remains for the separate Business integration, which is not implemented.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GarminTransport(Protocol):
    """Operations required by Garmin fetch and sync orchestration."""

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        """Return one page of provider activity summaries."""
        ...

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        """Return activity sample rows in the connector's existing shape."""
        ...

    async def get_activity_exercise_sets(self, activity_id: int) -> dict[str, Any]: ...

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_stress_data(self, local_date: str) -> dict[str, Any]: ...

    async def get_stats(self, local_date: str) -> dict[str, Any]: ...

    async def get_body_composition(self, local_date: str) -> dict[str, Any]: ...


class OfficialGarminTransport:
    """Unsupported placeholder for a future approved Business integration.

    This is not the owner-only GarminPersonalClient. Each operation fails
    explicitly rather than fabricating an empty successful response.
    """

    _MESSAGE = (
        "Garmin official transport is unsupported: obtain approved official "
        "credentials and provider schemas before implementing this operation"
    )

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError(self._MESSAGE)

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError(self._MESSAGE)

    async def get_activity_exercise_sets(self, activity_id: int) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError(self._MESSAGE)
