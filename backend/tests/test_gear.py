"""Gear tracking acceptance tests (MASTER_SPEC §13, §19, §23 Phase 4).

AC2: a synthetic 15h-since-service gear item fires gear_service_due —
DB-backed alert + push to the linked chat. Plus: §17 idempotency of the
nightly accumulation (re-running never double-counts or re-fires), §13
service logging resets counters and resolves the open alert, and §13
auto-link via discipline_gear_defaults at Garmin ingestion.

No third-party calls — Garmin and Telegram are fixture clients (§0, §20).
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text

from app.connectors.garmin.sync import run_user_sync_with_escalation
from app.core.db import sessionmaker
from app.gear.service import accumulate_gear_usage, auto_link_gear, log_gear_service
from app.models.activity import Activity, ActivitySourceLink
from app.models.alert import Alert
from app.models.gear import ActivityGearLink, DisciplineGearDefault, Gear
from app.models.integration import Integration
from app.models.telegram import TelegramLink
from app.models.user import User
from app.queries import gear_overview
from app.tasks.gear_tasks import _accumulate_all, is_nightly_local_time
from tests.helpers.fixture_client import FixtureGarminClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
)

ROME_NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


async def gear_world(db_session):
    """Owner user + a road_cycling chain with a 15 h service interval."""
    user_id = (
        await db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))
    ).scalar_one()
    discipline_id = (
        await db_session.execute(
            text("SELECT id FROM disciplines WHERE name = 'road_cycling'")
        )
    ).scalar_one()
    gear = Gear(
        user_id=user_id,
        name="Indoor trainer",
        gear_type="endurance",
        service_interval_hours=15,
    )
    db_session.add(gear)
    await db_session.flush()
    return {"user_id": user_id, "discipline_id": discipline_id, "gear": gear}


async def _add_linked_activity(db_session, world, *, days_ago: float, duration_s: int) -> Activity:
    """A synthetic road_cycling activity linked to the world's gear."""
    start = ROME_NOW - timedelta(days=days_ago)
    activity = Activity(
        user_id=world["user_id"],
        discipline_id=world["discipline_id"],
        start_time=start,
        start_tz_offset_minutes=60,
        local_date=start.date(),
        duration_s=duration_s,
        distance_m=None,
    )
    db_session.add(activity)
    await db_session.flush()
    db_session.add(ActivityGearLink(activity_id=activity.id, gear_id=world["gear"].id))
    return activity


async def _fresh_gear(db_session, gear_id: int) -> Gear:
    """Re-read the gear row so accumulated counters come from the DB, not a
    stale identity map."""
    return await db_session.get(Gear, gear_id)


# --------------------------------------------------------------- AC2


async def test_synthetic_15h_gear_fires_service_due_alert(db_session):
    """AC2: 15 h of linked usage against a 15 h interval → gear_service_due
    alert row + Telegram push to the linked chat."""
    client = FixtureTelegramClient()
    world = await gear_world(db_session)
    db_session.add(TelegramLink(user_id=world["user_id"], chat_id=777))
    await _add_linked_activity(db_session, world, days_ago=2.0, duration_s=8 * 3600)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=7 * 3600)
    await db_session.commit()

    gear = await _fresh_gear(db_session, world["gear"].id)
    alert = await accumulate_gear_usage(db_session, gear)
    await db_session.commit()

    assert alert is not None
    assert alert.type == "gear_service_due"
    assert alert.severity == "warning"
    assert float(gear.hours_since_service) == 15.0

    from app.connectors.telegram.alerts import push_alert

    notified = await push_alert(sessionmaker, client, alert)
    assert notified == 1
    (msg,) = client.sent_messages
    assert msg["chat_id"] == 777
    assert "gear_service_due" in msg["text"]
    assert "15 h" in msg["text"]


async def test_accumulation_is_idempotent_no_double_count_no_refire(db_session):
    """§17: re-running the accumulation neither double-counts usage nor
    re-fires the alert for the same crossing."""
    world = await gear_world(db_session)
    await _add_linked_activity(db_session, world, days_ago=2.0, duration_s=8 * 3600)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=7 * 3600)
    await db_session.commit()

    gear = await _fresh_gear(db_session, world["gear"].id)
    first = await accumulate_gear_usage(db_session, gear)
    await db_session.commit()

    gear = await _fresh_gear(db_session, world["gear"].id)
    second = await accumulate_gear_usage(db_session, gear)
    await db_session.commit()

    assert first is not None and second is None
    gear = await _fresh_gear(db_session, world["gear"].id)
    assert float(gear.hours_since_service) == 15.0  # unchanged, not doubled

    alerts = (
        await db_session.scalars(select(Alert).where(Alert.type == "gear_service_due"))
    ).all()
    assert len(alerts) == 1


async def test_below_threshold_never_fires(db_session):
    world = await gear_world(db_session)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=14 * 3600)
    await db_session.commit()
    gear = await _fresh_gear(db_session, world["gear"].id)
    assert await accumulate_gear_usage(db_session, gear) is None
    gear = await _fresh_gear(db_session, world["gear"].id)
    assert float(gear.hours_since_service) == 14.0


async def test_service_log_resets_counters_and_resolves_alert(db_session):
    """§13: logging a service resets the counters; the open alert is
    acknowledged so a FUTURE crossing can fire again."""
    world = await gear_world(db_session)
    await _add_linked_activity(db_session, world, days_ago=2.0, duration_s=8 * 3600)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=7 * 3600)
    await db_session.commit()

    gear = await _fresh_gear(db_session, world["gear"].id)
    fired = await accumulate_gear_usage(db_session, gear)
    await db_session.commit()
    assert fired is not None

    gear = await _fresh_gear(db_session, world["gear"].id)
    await log_gear_service(
        db_session,
        gear=gear,
        service_type="full overhaul",
        performed_at=ROME_NOW - timedelta(hours=12),
        notes="chain + cassette",
    )
    await db_session.commit()

    gear = await _fresh_gear(db_session, world["gear"].id)
    assert float(gear.hours_since_service) == 0

    # usage AFTER the service is what counts now: a 16 h block re-crosses
    await _add_linked_activity(db_session, world, days_ago=0.25, duration_s=16 * 3600)
    await db_session.commit()
    gear = await _fresh_gear(db_session, world["gear"].id)
    assert await accumulate_gear_usage(db_session, gear) is not None
    gear = await _fresh_gear(db_session, world["gear"].id)
    assert float(gear.hours_since_service) == 16.0

    alerts = (
        await db_session.scalars(
            select(Alert).where(Alert.type == "gear_service_due").order_by(Alert.id)
        )
    ).all()
    assert [a.acknowledged for a in alerts] == [True, False]


async def test_km_interval_crosses_independently(db_session):
    world = await gear_world(db_session)
    km_gear = Gear(
        user_id=world["user_id"],
        name="Road bike",
        gear_type="endurance",
        service_interval_km=100,
    )
    db_session.add(km_gear)
    await db_session.flush()
    start = ROME_NOW - timedelta(days=1)
    activity = Activity(
        user_id=world["user_id"],
        discipline_id=world["discipline_id"],
        start_time=start,
        start_tz_offset_minutes=60,
        local_date=start.date(),
        duration_s=3600,
        distance_m=120_000.0,
    )
    db_session.add(activity)
    await db_session.flush()
    db_session.add(ActivityGearLink(activity_id=activity.id, gear_id=km_gear.id))
    await db_session.commit()

    fresh = await _fresh_gear(db_session, km_gear.id)
    alert = await accumulate_gear_usage(db_session, fresh)
    assert alert is not None
    assert "km" in alert.message


# ------------------------------------------------- ingestion auto-link (§13)


async def test_auto_link_gear_is_idempotent(db_session):
    world = await gear_world(db_session)
    db_session.add(
        DisciplineGearDefault(
            user_id=world["user_id"],
            discipline_id=world["discipline_id"],
            gear_id=world["gear"].id,
        )
    )
    start = ROME_NOW - timedelta(days=1)
    activity = Activity(
        user_id=world["user_id"],
        discipline_id=world["discipline_id"],
        start_time=start,
        start_tz_offset_minutes=60,
        local_date=start.date(),
        duration_s=3600,
    )
    db_session.add(activity)
    await db_session.flush()

    assert await auto_link_gear(
        db_session,
        user_id=world["user_id"],
        discipline_id=world["discipline_id"],
        activity_id=activity.id,
    ) == 1
    await db_session.commit()
    # re-linking (e.g. a re-normalized activity) adds nothing
    assert await auto_link_gear(
        db_session,
        user_id=world["user_id"],
        discipline_id=world["discipline_id"],
        activity_id=activity.id,
    ) == 0
    links = (await db_session.scalars(select(ActivityGearLink))).all()
    assert len(links) == 1


async def test_garmin_ingestion_autolinks_default_gear(db_session):
    """Full fixture sync: the road_biking activity inherits the road_cycling
    default; the running activity does not."""
    user = User(name="gear-athlete", timezone="Europe/Rome")
    db_session.add(user)
    await db_session.flush()
    integration = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(integration)

    cycling_id = (
        await db_session.execute(
            text("SELECT id FROM disciplines WHERE name = 'road_cycling'")
        )
    ).scalar_one()
    bike = Gear(
        user_id=user.id, name="Race bike", gear_type="endurance", service_interval_km=500
    )
    db_session.add(bike)
    await db_session.flush()
    db_session.add(
        DisciplineGearDefault(user_id=user.id, discipline_id=cycling_id, gear_id=bike.id)
    )
    await db_session.commit()

    report = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(),
        page_size=3, page_delay_s=0.0, empty_gap_days=10, now=ROME_NOW,
    )
    assert report is not None

    # activity 7102 is the only road_biking fixture (7200 s, 48.2 km)
    linked = (
        await db_session.execute(
            select(ActivitySourceLink.external_id, ActivityGearLink.gear_id)
            .join(ActivityGearLink, ActivityGearLink.activity_id == ActivitySourceLink.activity_id)
            .where(ActivitySourceLink.source == "garmin")
        )
    ).all()
    assert linked == [("7102", bike.id)]

    run_activity_id = await db_session.scalar(
        select(ActivitySourceLink.activity_id).where(ActivitySourceLink.external_id == "7101")
    )
    run_links = await db_session.scalar(
        select(func.count()).select_from(ActivityGearLink).where(
            ActivityGearLink.activity_id == run_activity_id
        )
    )
    assert run_links == 0


# ------------------------------------------------------- nightly task (§19)


def test_gear_task_dispatch_guard():
    rome = ZoneInfo("Europe/Rome")
    assert is_nightly_local_time(datetime(2025, 4, 12, 1, 15, tzinfo=UTC), rome)
    assert not is_nightly_local_time(datetime(2025, 4, 12, 0, 15, tzinfo=UTC), rome)
    assert not is_nightly_local_time(datetime(2025, 4, 12, 2, 15, tzinfo=UTC), rome)


async def test_nightly_gear_task_fires_alert_pushes_and_is_idempotent(
    db_session, monkeypatch
):
    """The §19 task end-to-end against a synthetic 15 h world: alert row +
    push on the first 03:15-local dispatch, quiet on the re-run (§17)."""
    world = await gear_world(db_session)
    await _add_linked_activity(db_session, world, days_ago=2.0, duration_s=8 * 3600)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=7 * 3600)
    await db_session.commit()

    client = FixtureTelegramClient()

    # a configured token flips the task into pushing after commit — with the
    # fixture client swapped in for the live one, so the REAL push_alert path
    # is exercised and no network call can happen (§0/§20)
    monkeypatch.setattr(
        "app.tasks.gear_tasks.get_settings",
        lambda: SimpleNamespace(telegram_bot_token="fixture-token"),
    )
    monkeypatch.setattr(
        "app.connectors.telegram.client.LiveTelegramClient",
        lambda bot_token: client,
    )

    # 03:15 Rome = 02:15Z in March (CET, UTC+1)
    result = await _accumulate_all(now_iso="2025-03-10T02:15:00+00:00")

    assert result[str(world["user_id"])] == {"gear_checked": 1, "alerts_fired": 1}
    alerts = (
        await db_session.scalars(select(Alert).where(Alert.type == "gear_service_due"))
    ).all()
    assert len(alerts) == 1
    assert client.sent_messages == []  # no linked chat yet — row first, no crash

    # link a chat, resolve the alert via a service log, then cross again:
    # the second crossing fires AND pushes to the linked chat
    db_session.add(TelegramLink(user_id=world["user_id"], chat_id=777))
    await log_gear_service(
        db_session,
        gear=await _fresh_gear(db_session, world["gear"].id),
        service_type="wipe down",
        performed_at=ROME_NOW - timedelta(hours=12),
    )
    await _add_linked_activity(db_session, world, days_ago=0.25, duration_s=16 * 3600)
    await db_session.commit()
    client.sent_messages.clear()
    result = await _accumulate_all(now_iso="2025-03-10T02:15:00+00:00")
    assert result[str(world["user_id"])] == {"gear_checked": 1, "alerts_fired": 1}
    assert [(m["chat_id"], "gear_service_due" in m["text"]) for m in client.sent_messages] == [
        (777, True)
    ]

    # idempotent re-run: nothing new, nothing pushed
    client.sent_messages.clear()
    result = await _accumulate_all(now_iso="2025-03-10T02:15:00+00:00")
    assert result[str(world["user_id"])] == {"gear_checked": 1, "alerts_fired": 0}
    assert client.sent_messages == []


async def test_gear_overview_uses_orm_models(db_session):
    """§8.2 get_gear_status read (bot /gear command source) reflects usage."""
    world = await gear_world(db_session)
    await _add_linked_activity(db_session, world, days_ago=1.0, duration_s=15 * 3600)
    await db_session.commit()
    gear = await _fresh_gear(db_session, world["gear"].id)
    await accumulate_gear_usage(db_session, gear)
    await db_session.commit()

    items = await gear_overview(db_session, world["user_id"])
    assert len(items) == 1
    assert items[0]["name"] == "Indoor trainer"
    assert items[0]["usage_pct"] == pytest.approx(100.0)
