"""Calendar endpoints expose complete, account-scoped month ranges."""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.auth.invites import create_invite, redeem_invite
from app.models.coach import UserEvent
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User


@pytest.fixture(autouse=True)
async def clean_calendar_rows(db_session):
    await db_session.execute(
        text("TRUNCATE user_events, training_plans, planned_sessions RESTART IDENTITY CASCADE")
    )
    await db_session.commit()


async def owner_login(client):
    response = await client.post(
        "/auth/login",
        json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]},
    )
    assert response.status_code == 200, response.text


async def friend_account(db_session):
    owner = await db_session.scalar(select(User).order_by(User.id).limit(1))
    invite = await create_invite(db_session, created_by=owner.id)
    email = f"calendar-{uuid4().hex}@example.com"
    friend, _, _ = await redeem_invite(
        db_session, invite.code, "Calendar Friend", email, "friend-password-1"
    )
    return friend, email


async def test_events_range_includes_past_and_spanning_month_but_not_other_accounts(
    client, db_session
):
    await owner_login(client)
    owner = await db_session.scalar(select(User).order_by(User.id).limit(1))
    friend, friend_email = await friend_account(db_session)
    db_session.add_all([
        UserEvent(
            user_id=owner.id, title="Past event", kind="race",
            starts_at=datetime(2025, 2, 10, 12, tzinfo=UTC), priority=2,
            taper_days=0,
        ),
        UserEvent(
            user_id=owner.id, title="Spanning event", kind="trip",
            starts_at=datetime(2025, 1, 30, 12, tzinfo=UTC),
            ends_at=datetime(2025, 2, 2, 12, tzinfo=UTC),
            priority=2, taper_days=0,
        ),
        UserEvent(
            user_id=owner.id, title="Outside range", kind="race",
            starts_at=datetime(2025, 3, 1, 12, tzinfo=UTC),
            priority=2, taper_days=0,
        ),
        UserEvent(
            user_id=friend.id, title="Friend private event", kind="race",
            starts_at=datetime(2025, 2, 11, 12, tzinfo=UTC),
            priority=2, taper_days=0,
        ),
    ])
    await db_session.commit()

    response = await client.get("/events?start=2025-02-01&end=2025-02-28")
    assert response.status_code == 200, response.text
    assert [row["title"] for row in response.json()] == ["Spanning event", "Past event"]
    assert all(row["bucket"] == "past" for row in response.json())

    client.cookies.clear()
    login = await client.post(
        "/auth/login", json={"email": friend_email, "password": "friend-password-1"}
    )
    assert login.status_code == 200, login.text
    friend_rows = (await client.get("/events?start=2025-02-01&end=2025-02-28")).json()
    assert [row["title"] for row in friend_rows] == ["Friend private event"]


async def test_events_range_rejects_incomplete_reversed_and_excessive_ranges(client):
    await owner_login(client)
    for query in (
        "start=2025-02-01",
        "end=2025-02-28",
        "start=2025-02-28&end=2025-02-01",
        "start=2025-01-01&end=2026-01-03",
        "start=not-a-date&end=2025-02-28",
    ):
        response = await client.get(f"/events?{query}")
        assert response.status_code == 422, (query, response.text)


async def test_schedule_calendar_only_includes_own_confirmed_active_completed_plans(
    client, db_session
):
    await owner_login(client)
    owner = await db_session.scalar(select(User).order_by(User.id).limit(1))
    friend, friend_email = await friend_account(db_session)
    week_start = date(2025, 2, 3)
    for status in ("draft", "confirmed", "active", "completed"):
        plan = TrainingPlan(
            user_id=owner.id, created_by="manual", week_start=week_start,
            status=status,
        )
        db_session.add(plan)
        await db_session.flush()
        db_session.add(PlannedSession(
            training_plan_id=plan.id, date=date(2025, 2, 10),
            session_type=status, target_duration_min=45, description=f"{status} ride",
        ))
    outside = TrainingPlan(
        user_id=owner.id, created_by="manual", week_start=week_start,
        status="confirmed",
    )
    db_session.add(outside)
    await db_session.flush()
    db_session.add(PlannedSession(
        training_plan_id=outside.id, date=date(2025, 3, 1),
        session_type="outside",
    ))
    foreign = TrainingPlan(
        user_id=friend.id, created_by="manual", week_start=week_start,
        status="confirmed",
    )
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(PlannedSession(
        training_plan_id=foreign.id, date=date(2025, 2, 10),
        session_type="friend private",
    ))
    await db_session.commit()

    response = await client.get("/schedule/calendar?start=2025-02-01&end=2025-02-28")
    assert response.status_code == 200, response.text
    assert [row["session_type"] for row in response.json()["sessions"]] == [
        "confirmed", "active", "completed"
    ]
    assert all(row["date"] == "2025-02-10" for row in response.json()["sessions"])

    client.cookies.clear()
    login = await client.post(
        "/auth/login", json={"email": friend_email, "password": "friend-password-1"}
    )
    assert login.status_code == 200, login.text
    friend_rows = (await client.get("/schedule/calendar?start=2025-02-01&end=2025-02-28")).json()["sessions"]
    assert [row["session_type"] for row in friend_rows] == ["friend private"]


async def test_schedule_calendar_rejects_invalid_ranges(client):
    await owner_login(client)
    for query in (
        "start=2025-02-28&end=2025-02-01",
        "start=2025-01-01&end=2026-01-03",
        "start=2025-02-01",
    ):
        response = await client.get(f"/schedule/calendar?{query}")
        assert response.status_code == 422, (query, response.text)
