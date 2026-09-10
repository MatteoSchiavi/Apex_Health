"""Phase 7 client tests — Open-Meteo client (§2, §14, §0/§16.7/§20).

No test touches the live API: the httpx layer is exercised through a mock
transport, error payloads raise WeatherError, and request params carry the
fields the normalizer expects.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.connectors.weather.client import (
    ARCHIVE_URL,
    DAILY_FIELDS,
    FORECAST_URL,
    OpenMeteoClient,
    WeatherError,
)

FIXTURES = Path(__file__).resolve().parents[0] / "fixtures" / "weather"
FORECAST_FIXTURE = json.loads((FIXTURES / "forecast_response.json").read_text())
ARCHIVE_FIXTURE = json.loads((FIXTURES / "archive_response.json").read_text())


def _client(handler) -> OpenMeteoClient:
    return OpenMeteoClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_forecast_returns_fixture_payload_and_sends_expected_params():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=FORECAST_FIXTURE)

    payload = await _client(handler).forecast(
        45.075, 9.725, past_days=1, forecast_days=7, timezone="Europe/Rome"
    )
    assert payload["daily"]["time"][0] == "2025-03-09"
    assert seen["url"].startswith(FORECAST_URL)
    for fragment in DAILY_FIELDS.split(","):
        assert fragment in seen["url"]
    assert "past_days=1" in seen["url"]
    assert "forecast_days=7" in seen["url"]
    assert "timezone=Europe%2FRome" in seen["url"]


async def test_archive_hits_archive_endpoint_with_date_range():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ARCHIVE_FIXTURE)

    payload = await _client(handler).archive(
        45.075, 9.725, start_date="2025-01-10", end_date="2025-01-12"
    )
    assert payload["daily"]["time"] == ["2025-01-10", "2025-01-11", "2025-01-12"]
    assert seen["url"].startswith(ARCHIVE_URL)
    assert "start_date=2025-01-10" in seen["url"]
    assert "end_date=2025-01-12" in seen["url"]


async def test_upstream_error_payload_raises_weather_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": True, "reason": "out of range"})

    with pytest.raises(WeatherError, match="out of range"):
        await _client(handler).forecast(45.0, 9.0)


async def test_http_failure_raises_weather_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(WeatherError, match="503"):
        await _client(handler).forecast(45.0, 9.0)


async def test_non_object_payload_raises_weather_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    with pytest.raises(WeatherError, match="non-object"):
        await _client(handler).forecast(45.0, 9.0)
