"""Fixture-backed Garmin client implementations for tests.

These are the ONLY clients automated tests use (§0/§16.7: no live third-party
calls, ever). `FixtureGarminClient` serves the recorded corpus and records its
call pattern so tests can assert pagination and incremental-fetch minimization.
"""

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "garmin"


class FixtureGarminClient:
    def __init__(self, fixtures_dir: Path = FIXTURES_DIR) -> None:
        self._dir = fixtures_dir
        self.activity_calls: list[tuple[int, int]] = []
        self.stream_calls: list[int] = []
        self.wellness_calls: list[str] = []
        self._activities: list[dict[str, Any]] = self._load("activities.json", [])

    def _load(self, rel: str, default: Any) -> Any:
        path = self._dir / rel
        if not path.exists():
            return default
        return json.loads(path.read_text())

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        self.activity_calls.append((start, limit))
        return self._activities[start : start + limit]

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        self.stream_calls.append(activity_id)
        return self._load(f"streams/{activity_id}.json", [])

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        self.wellness_calls.append(f"sleep:{local_date}")
        return self._load(f"sleep/{local_date}.json", {})

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        self.wellness_calls.append(f"hrv:{local_date}")
        return self._load(f"hrv/{local_date}.json", {})

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        self.wellness_calls.append(f"stress:{local_date}")
        return self._load(f"stress/{local_date}.json", {})

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        self.wellness_calls.append(f"stats:{local_date}")
        return self._load(f"stats/{local_date}.json", {})

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        self.wellness_calls.append(f"body:{local_date}")
        return self._load(f"body_composition/{local_date}.json", {})


class FailingGarminClient:
    """Every remote call raises — §21 escalation tests."""

    def _raise(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("garmin unreachable (simulated outage)")

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        self._raise()

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        self._raise()

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        self._raise()

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        self._raise()

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        self._raise()

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        self._raise()

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        self._raise()
