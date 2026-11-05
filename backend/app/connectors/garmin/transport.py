"""Typed boundary used by Garmin API ingestion and synthetic fixture clients.
Unsupported operations are declared by the concrete API client; no fake
"official" placeholder participates in runtime selection.
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
