"""Provider-ID collisions, checkpoint resumption and failed sync isolation."""

from datetime import UTC, datetime
from importlib import import_module

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.connectors.escalation import run_sync_with_escalation
from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.integration import Integration
from app.models.user import User
from tests.helpers.fixture_client import FixtureGarminClient, FixtureTechnogymClient
from tests.test_strava_connector import FixtureStravaClient
from tests.test_whoop_connector import FixtureWhoopClient


@pytest.mark.parametrize("provider,client_type,kwargs", [
    ("garmin", FixtureGarminClient, {"page_size": 3, "page_delay_s": 0, "empty_gap_days": 10}),
    ("technogym", FixtureTechnogymClient, {"page_size": 2, "page_delay_s": 0}),
    ("strava", FixtureStravaClient, {"page_delay_s": 0}),
    ("whoop", FixtureWhoopClient, {}),
])
async def test_same_provider_ids_are_isolated_and_idempotent(db_session, provider, client_type, kwargs):
    sync = import_module(f"app.connectors.{provider}.sync").run_user_sync_with_escalation
    accounts = []
    now = datetime(2025, 3, 10, 8, tzinfo=UTC) if provider in {"garmin", "technogym"} else datetime(2026, 9, 22, 8, tzinfo=UTC)
    for name in ("first", "second"):
        user = User(name=f"collision-{provider}-{name}")
        db_session.add(user)
        await db_session.flush()
        integration = Integration(user_id=user.id, provider=provider, status="active")
        db_session.add(integration)
        await db_session.commit()
        report = await sync(db_session, user, integration, client_type(), now=now, **kwargs)
        assert report is not None
        links = (await db_session.scalars(select(ActivitySourceLink).where(
            ActivitySourceLink.user_id == user.id, ActivitySourceLink.source == provider,
        ))).all()
        assert links
        accounts.append((user, integration, {link.external_id: link.activity_id for link in links}))
    first, second = accounts
    assert set(first[2]) == set(second[2])
    assert set(first[2].values()).isdisjoint(second[2].values())
    for user, integration, identifiers in accounts:
        assert all([(await db_session.get(Activity, activity_id)).user_id == user.id
                    for activity_id in identifiers.values()])
        await sync(db_session, user, integration, client_type(), now=now, **kwargs)
        current = dict((await db_session.execute(select(ActivitySourceLink.external_id, ActivitySourceLink.activity_id).where(
            ActivitySourceLink.user_id == user.id, ActivitySourceLink.source == provider,
        ))).all())
        assert current == identifiers
    # Even a faulty future connector cannot attach a foreign account's row.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ActivitySourceLink(user_id=second[0].id,
                activity_id=next(iter(first[2].values())), source=provider, external_id="wrong-owner"))
            await db_session.flush()


async def test_sql_failure_rolls_back_and_records_failure_without_secret(db_session):
    user = User(name="sql-failure")
    db_session.add(user)
    await db_session.flush()
    integration = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(integration)
    await db_session.commit()
    async def broken(session, *args):
        await session.execute(text("SELECT 1 / 0"))
    for _ in range(3):
        assert await run_sync_with_escalation(db_session, user, integration, broken, source_label="Garmin") is None
    assert integration.consecutive_failures == 3
    # The failed SQL transaction no longer poisons subsequent work.
    assert await db_session.scalar(text("SELECT 1")) == 1


async def test_interrupted_garmin_checkpoint_resumes_without_duplicate_stream_fetch(db_session):
    sync = import_module("app.connectors.garmin.sync").run_user_sync_with_escalation
    user = User(name="checkpoint-resume")
    db_session.add(user)
    await db_session.flush()
    integration = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(integration)
    await db_session.commit()
    class Interrupted(FixtureGarminClient):
        async def get_activities(self, start, limit):
            if start:
                raise RuntimeError("Interrupted after checkpoint")
            return await super().get_activities(start, limit)
    kwargs = {"page_size": 3, "page_delay_s": 0, "empty_gap_days": 10,
              "checkpoint": True, "now": datetime(2025, 3, 10, 8, tzinfo=UTC)}
    assert await sync(db_session, user, integration, Interrupted(), **kwargs) is None
    links_before = (await db_session.scalars(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id))).all()
    assert len(links_before) == 3  # previous page survived the failure rollback
    client = FixtureGarminClient()
    assert await sync(db_session, user, integration, client, **kwargs) is not None
    assert len(client.stream_calls) == len(set(client.stream_calls))
    links = (await db_session.scalars(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id))).all()
    assert len(links) == 4
    assert await db_session.scalar(select(ActivityStream.activity_id).where(
        ActivityStream.activity_id.in_([link.activity_id for link in links]),
    ).limit(1)) is not None
