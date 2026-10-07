"""Small, network-free contracts for the Garmin transport boundary."""

import asyncio

import pytest

from app.connectors.garmin.client import (
    GarminClient,
    GarminConnectClient,
    GarminConnectTransport,
    LiveGarminClient,
)
from app.connectors.garmin.transport import (
    GarminTransport,
    OfficialGarminTransport,
)


class FakeGarminConnect:
    def get_activities(self, start, limit):
        return [{"start": start, "limit": limit}]

    def get_activity_details(self, activity_id):
        assert activity_id == "42"
        return {
            "metricDescriptors": [
                {"key": "directTimestamp"},
                {"key": "directHeartRate"},
                {"key": "unmapped"},
            ],
            "activityDetailMetrics": [
                {"metrics": [1000, 145, "ignored"]},
                {"metrics": [2000, None, 7]},
            ],
        }

    def get_sleep_data(self, day):
        return {"day": day, "kind": "sleep"}

    def get_hrv_data(self, day):
        return {"day": day, "kind": "hrv"}

    def get_stress_data(self, day):
        return {"day": day, "kind": "stress"}

    def get_stats_and_body(self, day):
        return {"day": day, "kind": "stats"}

    def get_body_composition(self, day):
        return {"day": day, "kind": "body_composition"}


class InjectedTransport:
    async def get_activities(self, start, limit):
        return [{"injected": [start, limit]}]

    async def get_activity_samples(self, activity_id):
        return [{"injected_activity_id": activity_id}]

    async def get_sleep_data(self, local_date):
        return {"injected": local_date}

    async def get_hrv_data(self, local_date):
        return {"injected": local_date}

    async def get_stress_data(self, local_date):
        return {"injected": local_date}

    async def get_stats(self, local_date):
        return {"injected": local_date}

    async def get_body_composition(self, local_date):
        return {"injected": local_date}


def test_existing_pipeline_surface_is_the_transport_contract():
    transport = GarminConnectTransport(FakeGarminConnect())
    client = LiveGarminClient(FakeGarminConnect())

    assert isinstance(transport, GarminTransport)
    assert isinstance(client, GarminTransport)
    assert GarminClient is GarminTransport
    assert GarminConnectClient is LiveGarminClient


def test_connect_transport_preserves_the_existing_activity_sample_shape():
    async def run():
        transport = GarminConnectTransport(FakeGarminConnect())
        assert await transport.get_activities(0, 5) == [{"start": 0, "limit": 5}]
        assert await transport.get_activity_samples(42) == [
            {"timestamp": 1000, "heartRate": 145},
            {"timestamp": 2000},
        ]
        assert await transport.get_stats("2026-10-07") == {
            "day": "2026-10-07",
            "kind": "stats",
        }

    asyncio.run(run())


def test_live_client_keeps_transport_dependency_injection():
    async def run():
        client = LiveGarminClient(FakeGarminConnect(), transport=InjectedTransport())
        assert await client.get_activities(2, 3) == [{"injected": [2, 3]}]
        assert await client.get_activity_samples(17) == [
            {"injected_activity_id": 17}
        ]
        assert await client.get_sleep_data("2026-10-07") == {
            "injected": "2026-10-07"
        }

    asyncio.run(run())


def test_official_placeholder_fails_without_fabricating_provider_data():
    transport = OfficialGarminTransport()

    async def run():
        operations = (
            transport.get_activities(0, 1),
            transport.get_activity_samples(1),
            transport.get_sleep_data("2026-10-07"),
            transport.get_hrv_data("2026-10-07"),
            transport.get_stress_data("2026-10-07"),
            transport.get_stats("2026-10-07"),
            transport.get_body_composition("2026-10-07"),
        )
        for operation in operations:
            with pytest.raises(
                NotImplementedError,
                match="approved official credentials.*provider schemas",
            ):
                await operation

    asyncio.run(run())
