from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.connectors.coros import normalize as coros_normalize
from app.connectors.garmin.normalize import NormalizerStats
from app.connectors import reconciliation
from app.models.activity import Activity, ActivitySourceLink


class FakeSession:
    def __init__(self, activity=None, link=None):
        self.activity = activity
        self.link = link
        self.added = []

    async def scalar(self, _statement):
        return self.link

    async def execute(self, _statement, _parameters):
        return None

    async def get(self, model, _identity):
        return self.activity if model is Activity else None

    async def flush(self):
        return None

    def add(self, value):
        self.added.append(value)


def _activity(*, metrics=None):
    return Activity(
        id=41,
        user_id=8,
        discipline_id=3,
        start_time=datetime(2026, 6, 14, 8, 30, tzinfo=timezone.utc),
        start_tz_offset_minutes=0,
        local_date=date(2026, 6, 14),
        duration_s=3600,
        distance_m=9000,
        elevation_gain_m=None,
        avg_hr=150,
        max_hr=175,
        calories=500,
        data_completeness="full",
        source_metrics=metrics or {},
    )


@pytest.mark.asyncio
async def test_new_coros_activity_reconciles_with_existing_window_and_preserves_main(monkeypatch):
    existing = _activity(metrics={"whoop": {"strain": 12.4}})
    session = FakeSession(activity=existing)
    raw = SimpleNamespace(user_id=8, id=902)

    async def candidate(*_args, **_kwargs):
        return existing

    async def main_exists(*_args, **_kwargs):
        return True

    monkeypatch.setattr(coros_normalize, "find_reconcilable_activity", candidate)
    monkeypatch.setattr(reconciliation, "activity_has_other_selected_main", main_exists)

    await coros_normalize.normalize_activity(
        session,
        raw,
        {
            "id": "coros-activity-1",
            "start_time": "2026-06-14T08:30:00Z",
            "duration_s": 3500,
            "distance_m": 10000,
            "elevation_gain_m": 100,
            "avg_hr": 140,
            "sport_type": "running",
            "device_label": "PACE Pro",
        },
        ZoneInfo("UTC"),
        {"running": 3},
        NormalizerStats(),
    )

    links = [item for item in session.added if isinstance(item, ActivitySourceLink)]
    activities = [item for item in session.added if isinstance(item, Activity)]
    assert len(links) == 1
    assert links[0].activity_id == existing.id
    assert links[0].source == "coros"
    assert links[0].raw_ingest_id == raw.id
    assert activities == []
    assert existing.avg_hr == 150
    assert existing.distance_m == 9000
    assert existing.elevation_gain_m == 100  # secondary fills a true gap
    assert existing.source_metrics["whoop"] == {"strain": 12.4}
    assert existing.source_metrics["coros"]["device_label"] == "PACE Pro"


@pytest.mark.asyncio
async def test_linked_coros_refresh_keeps_main_values_nulls_and_other_metrics(monkeypatch):
    activity = _activity(metrics={"whoop": {"strain": 13.1}, "coros": {"old_tag": "kept"}})
    link = SimpleNamespace(activity_id=activity.id, raw_ingest_id=100)
    session = FakeSession(activity=activity, link=link)
    raw = SimpleNamespace(user_id=8, id=903)

    async def main_exists(*_args, **_kwargs):
        return True

    monkeypatch.setattr(coros_normalize, "activity_has_other_selected_main", main_exists)

    await coros_normalize.normalize_activity(
        session,
        raw,
        {
            "id": "coros-activity-1",
            "start_time": "2026-06-14T08:30:00Z",
            "duration_s": 3400,
            "distance_m": 10000,
            "elevation_gain_m": 120,
            "avg_hr": 140,
            "sport_type": "running",
        },
        ZoneInfo("UTC"),
        {"running": 3},
        NormalizerStats(),
    )

    assert link.raw_ingest_id == raw.id
    assert activity.avg_hr == 150
    assert activity.distance_m == 9000
    assert activity.duration_s == 3600
    assert activity.elevation_gain_m == 120
    assert activity.source_metrics["whoop"] == {"strain": 13.1}
    assert activity.source_metrics["coros"] == {"old_tag": "kept", "sport_type": "running"}


@pytest.mark.asyncio
async def test_selected_main_coros_can_replace_secondary_window_values(monkeypatch):
    existing = _activity(metrics={"whoop": {"strain": 12.4}})
    session = FakeSession(activity=existing)
    raw = SimpleNamespace(user_id=8, id=904)

    async def candidate(*_args, **_kwargs):
        return existing

    async def selected_main(*_args, **_kwargs):
        return "coros"

    async def no_other_main(*_args, **_kwargs):
        return False

    monkeypatch.setattr(coros_normalize, "find_reconcilable_activity", candidate)
    monkeypatch.setattr(reconciliation, "selected_main_provider", selected_main)
    monkeypatch.setattr(reconciliation, "activity_has_other_selected_main", no_other_main)

    await coros_normalize.normalize_activity(
        session,
        raw,
        {
            "id": "coros-main-activity",
            "start_time": "2026-06-14T08:31:00Z",
            "duration_s": 3500,
            "distance_m": 10000,
            "avg_hr": 140,
            "sport_type": "running",
        },
        ZoneInfo("UTC"),
        {"running": 3},
        NormalizerStats(),
    )

    assert existing.start_time == datetime(2026, 6, 14, 8, 31, tzinfo=timezone.utc)
    assert existing.duration_s == 3500
    assert existing.distance_m == 10000
    assert existing.avg_hr == 140
    assert existing.source_metrics["whoop"] == {"strain": 12.4}
