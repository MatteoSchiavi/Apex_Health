"""Open-Meteo client (MASTER_SPEC §2, §14 — weather source).

Free, no API key (the spec's exact reason: "keeps a real feature inside the
€5/month budget instead of trading it away"). Two endpoints:

- forecast API (api.open-meteo.com): future days plus `past_days` of recent
  history — serves the scheduled forecast_cache refresh and any activity
  whose date is inside the recent window.
- archive API (archive-api.open-meteo.com): full history, lagging a few
  days behind real time — serves activity enrichment for older dates.

All tests run against recorded fixtures; no test ever touches the live API
(§0/§16.7/§20). The client takes an httpx.AsyncClient so tests inject a
transport and callers share a pooled client.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger("connectors.weather.client")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# §14: what a training-day summary needs, nothing more. Daily fields for the
# cache/snapshot; hourly temperature so an activity snapshot can capture the
# conditions at its start hour.
DAILY_FIELDS = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "precipitation_sum,precipitation_probability_max,"
    "wind_speed_10m_max,weather_code"
)
HOURLY_FIELDS = "temperature_2m,precipitation,weather_code"

# The archive API's publication lag (upstream docs: ~5 days behind real time).
# Enrichment routes dates newer than this to the forecast API's past window.
ARCHIVE_LAG_DAYS = 5


class WeatherError(Exception):
    """Raised when Open-Meteo cannot be reached or returns an error payload."""


class OpenMeteoClient:
    """Thin async client over the two Open-Meteo endpoints.

    `http` is injectable for tests (mock transport); production callers pass
    one shared httpx.AsyncClient per task run.
    """

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http
        self._owns_http = http is None

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            client = self._http or httpx.AsyncClient(timeout=30)
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
            finally:
                if self._owns_http:
                    await client.aclose()
        except httpx.HTTPError as exc:
            raise WeatherError(f"open-meteo request failed ({url}): {exc}") from exc
        if not isinstance(payload, dict):
            raise WeatherError(f"open-meteo returned non-object payload: {payload!r}")
        if payload.get("error"):
            raise WeatherError(
                f"open-meteo error {payload.get('reason', payload.get('code'))}"
            )
        return payload

    @staticmethod
    def _base_params(lat: float, lon: float, timezone: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "daily": DAILY_FIELDS,
            "hourly": HOURLY_FIELDS,
        }
        if timezone:
            params["timezone"] = timezone
        return params

    async def forecast(
        self,
        lat: float,
        lon: float,
        *,
        past_days: int = 0,
        forecast_days: int = 7,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Daily+hourly data for the next `forecast_days` (≤16) and the last
        `past_days` (≤92) — one call covers cache refresh AND recent-past
        activity enrichment."""
        params = self._base_params(lat, lon, timezone)
        params.update(past_days=past_days, forecast_days=forecast_days)
        return await self._get(FORECAST_URL, params)

    async def archive(
        self,
        lat: float,
        lon: float,
        *,
        start_date: str,
        end_date: str,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Daily+hourly history for [start_date, end_date] (ISO dates) —
        activity enrichment for anything older than the archive lag."""
        params = self._base_params(lat, lon, timezone)
        params.update(start_date=start_date, end_date=end_date)
        return await self._get(ARCHIVE_URL, params)
