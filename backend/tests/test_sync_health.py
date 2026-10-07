"""Authenticated and account-scoped sync-health reporting coverage."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.models.integration import Integration
from app.models.lab import FeedState
from app.models.user import AuthCredential, User
from tests.conftest import csrf_headers


@pytest.mark.parametrize('availability', ['permission_denied', 'not_supported', 'not_exposed', 'not_measured', 'pending_sync'])
def test_sync_status_preserves_capability_and_permission_boundaries(availability):
    from app.services.sync_health import _state_from_feed
    now = datetime.now(UTC)
    feed = FeedState(user_id=1, provider='oura', feed='sleep', availability=availability,
        latest_measurement_at=now - timedelta(days=7))
    assert _state_from_feed(feed, now) == availability


@pytest.mark.asyncio
async def test_sync_health_is_private_redacted_and_measurement_staleness_wins(
    db_session, client
):
    owner_id = await db_session.scalar(
        select(AuthCredential.user_id).where(AuthCredential.role == "owner")
    )
    assert owner_id is not None

    # Keep this test independent of any provider fixture created by another
    # test while preserving the migrated schema's real provider constraints.
    await db_session.execute(
        delete(FeedState).where(FeedState.user_id == owner_id)
    )
    await db_session.execute(
        delete(Integration).where(
            Integration.user_id == owner_id,
            Integration.provider.in_(("oura", "strava")),
        )
    )

    another_user = User(name="Private sync-health account")
    db_session.add(another_user)
    await db_session.flush()

    now = datetime.now(UTC)
    old_measurement = now - timedelta(hours=72)
    owner_integration = Integration(
        user_id=owner_id,
        provider="oura",
        status="active",
        credentials_encrypted=b"credential-secret-must-not-leak",
        consecutive_failures=0,
        last_synced_at=now - timedelta(minutes=2),
    )
    no_feed_integration = Integration(
        user_id=owner_id,
        provider="strava",
        status="active",
        credentials_encrypted=b"another-secret",
        last_synced_at=now - timedelta(minutes=3),
    )
    db_session.add_all((owner_integration, no_feed_integration))
    db_session.add_all(
        (
            FeedState(
                user_id=owner_id,
                provider="oura",
                feed="sleep",
                availability="available",
                last_attempt_at=now - timedelta(minutes=1),
                last_success_at=now - timedelta(minutes=1),
                latest_measurement_at=old_measurement,
                cursor={"opaque_cursor": "cursor-secret"},
                details={"exception": "raw exception secret"},
            ),
            FeedState(
                user_id=another_user.id,
                provider="garmin",
                feed="normalization",
                availability="complete",
                cursor={"private": "other-user-cursor"},
                details={"private": "other-user-detail"},
            ),
        )
    )
    await db_session.commit()

    assert (await client.get("/lab/sync-health")).status_code == 401
    login = await client.post(
        "/auth/login",
        json={
            "email": os.environ["OWNER_EMAIL"],
            "password": os.environ["OWNER_PASSWORD"],
        },
    )
    assert login.status_code == 200
    response = await client.get("/lab/sync-health", headers=csrf_headers(client))

    assert response.status_code == 200
    payload = response.json()
    feeds = payload["feeds"]
    assert {row["provider"] for row in feeds} == {"oura", "strava"}
    sleep = next(row for row in feeds if row["provider"] == "oura")
    assert sleep["state"] == "stale"
    assert sleep["stale_after_hours"] == 48
    assert sleep["last_attempt_at"] is not None
    assert sleep["last_success_at"] is not None
    assert sleep["credentials_state"] == "configured"
    assert sleep["has_checkpoint"] is True

    account_sync = next(
        row
        for row in feeds
        if row["provider"] == "strava" and row["feed"] == "account_sync"
    )
    assert account_sync["state"] == "available"
    assert account_sync["latest_measurement_at"] is None
    assert account_sync["last_attempt_at"] is None
    assert account_sync["credentials_state"] == "configured"

    serialized = str(payload)
    for private_value in (
        "cursor-secret",
        "raw exception secret",
        "credential-secret-must-not-leak",
        "another-secret",
        "other-user-cursor",
        "other-user-detail",
    ):
        assert private_value not in serialized
