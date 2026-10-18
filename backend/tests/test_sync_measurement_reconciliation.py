"""Sync health follows real measurements across empty payloads and backfills."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.integration import Integration
from app.models.lab import FeedState
from app.models.user import User
from app.services.evidence import record_observation, update_feed
from app.services.sync_health import sync_health


NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


async def observation(session, user, value, measured, *, source="stats:today"):
    return await record_observation(
        session, user_id=user.id, metric="resting_hr", value=value, unit="bpm",
        origin="garmin", source_record_id=source, measured_at=measured,
        timezone="UTC", fetched_at=NOW,
    )


@pytest.mark.asyncio
async def test_empty_backfill_does_not_hide_current_measurements_or_cross_accounts(db_session):
    user, other = User(name="Sync evidence"), User(name="Other evidence")
    db_session.add_all([user, other])
    await db_session.flush()
    measured = NOW - timedelta(hours=4)
    await observation(db_session, user, 55, measured)
    await observation(db_session, other, 60, NOW)
    # Legacy caches can say not_measured and point at a null payload's date.
    db_session.add(FeedState(user_id=user.id, provider="garmin", feed="resting_hr",
        availability="not_measured", latest_measurement_at=NOW,
        last_attempt_at=NOW, last_success_at=NOW))
    await db_session.commit()

    result = await sync_health(db_session, user.id, now=NOW)
    assert result["feeds"][0]["state"] == "available"
    assert result["feeds"][0]["latest_measurement_at"] == measured
    assert result["accounts"][0]["latest_measurement_at"] == measured


@pytest.mark.asyncio
async def test_recent_null_payload_cannot_make_old_measurements_fresh(db_session):
    user = User(name="Old evidence")
    db_session.add(user)
    await db_session.flush()
    old = NOW - timedelta(days=4)
    await observation(db_session, user, 55, old, source="stats:old")
    await observation(db_session, user, None, NOW)
    db_session.add(FeedState(user_id=user.id, provider="garmin", feed="resting_hr",
        availability="not_measured", latest_measurement_at=NOW,
        last_attempt_at=NOW, last_success_at=NOW))
    await db_session.commit()

    result = await sync_health(db_session, user.id, now=NOW)
    assert result["feeds"][0]["state"] == "stale"
    assert result["feeds"][0]["latest_measurement_at"] == old
    assert result["accounts"][0]["data_freshness"] == "stale"


@pytest.mark.asyncio
async def test_retracted_measurement_is_not_revived_by_stale_checkpoint(db_session):
    user = User(name="Corrected evidence")
    db_session.add(user)
    await db_session.flush()
    await observation(db_session, user, 55, NOW)
    await observation(db_session, user, None, NOW)
    db_session.add(FeedState(user_id=user.id, provider="garmin", feed="resting_hr",
        availability="available", latest_measurement_at=NOW))
    await db_session.commit()

    result = await sync_health(db_session, user.id, now=NOW)
    assert result["feeds"][0]["state"] == "not_measured"
    assert result["feeds"][0]["latest_measurement_at"] is None
    assert result["accounts"][0]["data_freshness"] == "not_measured"


@pytest.mark.asyncio
async def test_backfill_preserves_attempt_order_and_empty_payload_has_no_measurement(db_session):
    user = User(name="Backfill chronology")
    db_session.add(user)
    await db_session.flush()
    measured = NOW - timedelta(hours=3)
    await update_feed(db_session, user.id, "garmin", "resting_hr", "available", NOW, measured)
    await db_session.flush()
    await update_feed(db_session, user.id, "garmin", "resting_hr", "not_measured",
                      NOW - timedelta(hours=1), NOW)
    row = await db_session.scalar(select(FeedState).where(FeedState.user_id == user.id))
    assert row.last_attempt_at == NOW and row.last_success_at == NOW
    assert row.latest_measurement_at == measured and row.availability == "available"
    await update_feed(db_session, user.id, "garmin", "resting_hr", "not_measured",
                      NOW + timedelta(minutes=1), NOW)
    assert row.latest_measurement_at == measured and row.availability == "available"
    await db_session.commit()


@pytest.mark.asyncio
async def test_account_failure_keeps_checkpoint_separate_from_completed_sync(db_session):
    user = User(name="Partial checkpoint")
    db_session.add(user)
    await db_session.flush()
    attempt = NOW - timedelta(minutes=10)
    await observation(db_session, user, 55, NOW - timedelta(hours=2))
    db_session.add_all([
        Integration(user_id=user.id, provider="garmin", status="active",
                    credentials_encrypted=b"synthetic", consecutive_failures=3),
        FeedState(user_id=user.id, provider="garmin", feed="account_sync",
                  availability="fetch_failed", last_attempt_at=attempt,
                  details={"error_class": "timeout"}),
        FeedState(user_id=user.id, provider="garmin", feed="resting_hr",
                  availability="available", last_attempt_at=NOW, last_success_at=NOW),
    ])
    await db_session.commit()

    account = (await sync_health(db_session, user.id, now=NOW))["accounts"][0]
    assert account["state"] == "partial" and account["has_successful_sync"] is True
    assert account["last_attempt_at"] == attempt
    assert account["last_success_at"] is None
    assert account["error_class"] == "timeout"
