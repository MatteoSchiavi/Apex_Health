"""Gym schedule + watch v2 (Phase 10 v2 — the rethought watch app).

The rethink: the watch shows what ONLY Apex knows — the recurring gym
schedule (overridden by date-specific planned sessions), active supplements,
open alerts, journal streak — NOT readiness/recovery/strain, which Garmin
already renders natively (Training Readiness / Recovery Time / Body Battery).

Covers:
- /schedule CRUD (owner-scoped, CSRF-protected, 404 across users)
- resolution precedence: confirmed-plan sessions override the recurring
  template on their dates; drafts never do
- GET /watch/day + /watch/week (Bearer device-token, owner-local dates)
- structural isolation: a friend's watch token sees the friend's schedule,
  and a friend's session cannot touch owner slots
- the /gym bot surface (today / week / list / set / note / rm)
"""

import os
from datetime import date, datetime, timedelta

from httpx import AsyncClient
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.models.alert import Alert
from app.models.gym import GymScheduleSlot
from app.models.journal import JournalEntry
from app.models.medical import SupplementProtocol
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User
from app.queries.gym import journal_streak, resolve_day
from tests.conftest import reset_owner_auth_state

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


@pytest_asyncio.fixture(autouse=True)
async def _gym_cleanup(db_session):
    """Run AFTER every test in this module: the session-scoped schema is
    shared, and rows created here (notably device_tokens) must not leak into
    sibling modules — test_watch_api pins an exact token count."""
    yield
    from app.models.watch import DeviceToken

    await db_session.execute(delete(JournalEntry))
    await db_session.execute(delete(Alert))
    await db_session.execute(delete(SupplementProtocol))
    await db_session.execute(delete(PlannedSession))
    await db_session.execute(delete(TrainingPlan))
    await db_session.execute(delete(GymScheduleSlot))
    await db_session.execute(delete(DeviceToken))
    await db_session.commit()


async def _clean(db_session: AsyncSession, *user_ids: int) -> None:
    """Session-scoped schema persists across tests — clear the domains this
    suite touches for the users involved (FK roots first)."""
    await db_session.execute(delete(JournalEntry))
    await db_session.execute(delete(Alert))
    await db_session.execute(delete(SupplementProtocol))
    await db_session.execute(delete(PlannedSession))
    await db_session.execute(delete(TrainingPlan))
    await db_session.execute(delete(GymScheduleSlot))
    await db_session.commit()


async def _owner_login(client: AsyncClient, db_session: AsyncSession) -> dict:
    await reset_owner_auth_state(db_session)
    resp = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=CSRF
    )
    assert resp.status_code == 200
    cookies = dict(resp.cookies)
    client.cookies.clear()
    return cookies


async def _mint_token(client: AsyncClient, cookies: dict, name: str) -> dict:
    resp = await client.post(
        "/watch/tokens", json={"name": name}, headers=CSRF, cookies=cookies
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _owner_id(db_session: AsyncSession) -> int:
    from app.models.user import AuthCredential

    return (
        await db_session.scalars(
            select(AuthCredential.user_id).where(AuthCredential.role == "owner")
        )
    ).first()


async def _local_today(db_session: AsyncSession, user_id: int) -> date:
    tz = ZoneInfo((await db_session.get(User, user_id)).timezone)
    return datetime.now(tz).date()


# ------------------------------------------------------------- /schedule CRUD


async def test_schedule_crud_roundtrip(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)

    created = await client.post(
        "/schedule",
        json={"weekday": 0, "start_time": "18:00", "title": "Push Day",
              "description": "Bench 4x8 · Incline 3x10"},
        headers=CSRF, cookies=owner,
    )
    assert created.status_code == 201, created.text
    slot = created.json()
    assert slot["weekday"] == 0 and slot["start_time"] == "18:00"
    assert slot["active"] is True

    listed = (await client.get("/schedule", cookies=owner)).json()
    assert [s["id"] for s in listed] == [slot["id"]]

    patched = await client.patch(
        f"/schedule/{slot['id']}",
        json={"start_time": "19:30", "active": False},
        headers=CSRF, cookies=owner,
    )
    assert patched.status_code == 200
    assert patched.json()["start_time"] == "19:30"
    assert patched.json()["active"] is False

    deleted = await client.delete(f"/schedule/{slot['id']}", headers=CSRF, cookies=owner)
    assert deleted.status_code == 204
    assert (await client.get("/schedule", cookies=owner)).json() == []


async def test_schedule_validation_rejects_bad_input(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)

    bad_weekday = await client.post(
        "/schedule", json={"weekday": 7, "start_time": "18:00", "title": "X"},
        headers=CSRF, cookies=owner,
    )
    assert bad_weekday.status_code == 422
    bad_time = await client.post(
        "/schedule", json={"weekday": 0, "start_time": "25:99", "title": "X"},
        headers=CSRF, cookies=owner,
    )
    assert bad_time.status_code == 422
    bad_title = await client.post(
        "/schedule", json={"weekday": 0, "start_time": "18:00", "title": ""},
        headers=CSRF, cookies=owner,
    )
    assert bad_title.status_code == 422


async def test_schedule_requires_auth_and_csrf(client: AsyncClient, db_session):
    await _clean(db_session)
    # unauthenticated read
    assert (await client.get("/schedule")).status_code in (401, 403)
    owner = await _owner_login(client, db_session)
    # authenticated but missing CSRF header on a mutating call
    no_csrf = await client.post(
        "/schedule", json={"weekday": 0, "start_time": "18:00", "title": "X"},
        cookies=owner,
    )
    assert no_csrf.status_code in (401, 403)


# ---------------------------------------------------------- resolution rules


async def test_recurring_slot_fills_any_matching_weekday(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)
    user_id = await _owner_id(db_session)
    local_today = await _local_today(db_session, user_id)

    await client.post(
        "/schedule",
        json={"weekday": local_today.weekday(), "start_time": "07:00", "title": "Easy 5k"},
        headers=CSRF, cookies=owner,
    )
    resp = await client.get("/watch/day", headers=await _bearer(client, owner))
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == local_today.isoformat()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["title"] == "Easy 5k"
    assert body["sessions"][0]["source"] == "schedule"


async def _bearer(client: AsyncClient, cookies: dict) -> dict:
    minted = await _mint_token(client, cookies, name="test-watch")
    return {"Authorization": f"Bearer {minted['token']}"}


async def test_confirmed_plan_overrides_recurring_slot(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)
    user_id = await _owner_id(db_session)
    local_today = await _local_today(db_session, user_id)

    # recurring slot on a NON-today weekday of the same week: that day falls
    # back to the template, today is overridden by the plan
    slot_weekday = 0 if local_today.weekday() != 0 else 1
    await client.post(
        "/schedule",
        json={"weekday": slot_weekday, "start_time": "18:00", "title": "Push Day"},
        headers=CSRF, cookies=owner,
    )
    plan = TrainingPlan(
        user_id=user_id, created_by="ai",
        week_start=local_today - timedelta(days=local_today.weekday()),
        status="confirmed",
    )
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        PlannedSession(
            training_plan_id=plan.id, date=local_today,
            session_type="easy aerobic", target_duration_min=45,
            description="Z2 treadmill",
        )
    )
    await db_session.commit()

    day = (await client.get("/watch/day", headers=await _bearer(client, owner))).json()
    assert len(day["sessions"]) == 1
    assert day["sessions"][0] == {
        "title": "easy aerobic", "source": "plan", "start": None, "duration": 45,
        "notes": "Z2 treadmill",
    }

    # tomorrow's-slot check: the slot's own weekday inside this week view
    week = (await client.get("/watch/week", headers=await _bearer(client, owner))).json()
    assert len(week["days"]) == 7
    assert week["days"][0]["date"] == (local_today - timedelta(days=local_today.weekday())).isoformat()
    template_day = week["days"][slot_weekday]
    assert template_day["weekday"] == slot_weekday
    assert [s["title"] for s in template_day["sessions"]] == ["Push Day"]


async def test_draft_plan_never_overrides(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)
    user_id = await _owner_id(db_session)
    local_today = await _local_today(db_session, user_id)

    await client.post(
        "/schedule",
        json={"weekday": local_today.weekday(), "start_time": "18:00", "title": "Push Day"},
        headers=CSRF, cookies=owner,
    )
    plan = TrainingPlan(
        user_id=user_id, created_by="ai",
        week_start=local_today - timedelta(days=local_today.weekday()),
        status="draft",
    )
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        PlannedSession(training_plan_id=plan.id, date=local_today, session_type="secret draft")
    )
    await db_session.commit()

    sessions = await resolve_day(db_session, user_id, local_today)
    assert [s["title"] for s in sessions] == ["Push Day"]


# ------------------------------------------------------- /watch/day payload


async def test_watch_day_carries_supplements_alerts_streak(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)
    user_id = await _owner_id(db_session)
    local_today = await _local_today(db_session, user_id)

    db_session.add_all(
        [
            SupplementProtocol(
                user_id=user_id, supplement_name="Creatine", dose="5 g",
                schedule_cron="0 8 * * *", active=True, start_date=local_today,
            ),
            SupplementProtocol(
                user_id=user_id, supplement_name="Ended Thing", dose="1",
                active=True, start_date=local_today - timedelta(days=30),
                end_date=local_today - timedelta(days=5),
            ),
            Alert(user_id=user_id, type="lab", severity="warning",
                  message="Ferritin trending low", acknowledged=False),
            Alert(user_id=user_id, type="sync", severity="info",
                  message="Technogym sync failed", acknowledged=True),
            JournalEntry(user_id=user_id, date=local_today, mood_score=7.0),
            JournalEntry(user_id=user_id, date=local_today - timedelta(days=1), mood_score=6.0),
        ]
    )
    await db_session.commit()

    resp = await client.get("/watch/day", headers=await _bearer(client, owner))
    assert resp.status_code == 200
    body = resp.json()
    assert [s["name"] for s in body["supplements"]] == ["Creatine"]  # ended one excluded
    assert body["alerts"]["count"] == 1
    assert body["alerts"]["items"][0]["message"] == "Ferritin trending low"
    assert body["journal_streak"] == 2

    # unauthenticated / garbage token
    assert (await client.get("/watch/day")).status_code == 401
    assert (
        await client.get("/watch/day", headers={"Authorization": "Bearer nope"})
    ).status_code == 401


# ----------------------------------------------------------------- isolation


async def test_friend_token_and_slots_are_isolated(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    await _clean(db_session)

    # friend account via the invite flow
    mint = await client.post("/settings/invites", json={}, headers=CSRF, cookies=owner)
    code = mint.json()["code"]
    redeem = await client.post(
        "/auth/invite/redeem",
        json={"code": code, "name": "Gym Friend", "email": "gym.friend@example.com",
              "password": "a-strong-password-gym"},
        headers=CSRF,
    )
    assert redeem.status_code == 201
    friend_id = redeem.json()["user_id"]
    friend_cookies = dict(redeem.cookies)
    client.cookies.clear()

    local_today = await _local_today(db_session, friend_id)

    owner_slot = (await client.post(
        "/schedule", json={"weekday": local_today.weekday(), "start_time": "18:00",
                           "title": "Owner Secret Session"},
        headers=CSRF, cookies=owner,
    )).json()
    friend_slot = (await client.post(
        "/schedule", json={"weekday": local_today.weekday(), "start_time": "07:00",
                           "title": "Friend Mobility"},
        headers=CSRF, cookies=friend_cookies,
    )).json()

    # friend's list shows only the friend's slot
    friend_list = (await client.get("/schedule", cookies=friend_cookies)).json()
    assert [s["id"] for s in friend_list] == [friend_slot["id"]]

    # cross-user PATCH/DELETE answer 404 (no existence leak)
    assert (
        await client.patch(f"/schedule/{owner_slot['id']}", json={"title": "hijack"},
                           headers=CSRF, cookies=friend_cookies)
    ).status_code == 404
    assert (
        await client.delete(f"/schedule/{owner_slot['id']}", headers=CSRF, cookies=friend_cookies)
    ).status_code == 404

    # the friend's WATCH sees the friend's schedule — never the owner's
    friend_day = (
        await client.get("/watch/day", headers=await _bearer(client, friend_cookies))
    ).json()
    assert [s["title"] for s in friend_day["sessions"]] == ["Friend Mobility"]

    owner_day = (
        await client.get("/watch/day", headers=await _bearer(client, owner))
    ).json()
    assert [s["title"] for s in owner_day["sessions"]] == ["Owner Secret Session"]


# ----------------------------------------------------------------- /gym bot


async def test_gym_bot_roundtrip():
    from app.connectors.telegram.handlers import handle_update
    from tests.helpers.telegram import (
        FixtureTelegramClient, bot_context, clean_bot_tables,  # noqa: F401
        load_update, sent_texts, with_text,
    )
    from app.models.telegram import TelegramLink
    from app.models.user import AuthCredential

    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        async with ctx.sessionmaker() as session:
            owner = (
                await session.scalars(
                    select(AuthCredential.user_id).where(AuthCredential.role == "owner")
                )
            ).first()
            session.add(TelegramLink(user_id=owner, chat_id=42))
            await session.execute(delete(GymScheduleSlot))  # schema persists across tests
            await session.commit()

        await handle_update(ctx, with_text(load_update("text_plan_today"),
                                           "/gym set Mon 18:00 Push Day"))
        first = sent_texts(client)[-1]
        assert "Added #" in first and "Mon 18:00 Push Day" in first
        import re

        slot_id = re.search(r"#(\d+)", first).group(1)

        await handle_update(ctx, with_text(load_update("text_plan_today"),
                                           f"/gym note {slot_id} Bench 4x8 · Incline 3x10"))
        assert "Bench 4x8" in sent_texts(client)[-1]

        await handle_update(ctx, with_text(load_update("text_plan_today"), "/gym list"))
        listing = sent_texts(client)[-1]
        assert f"#{slot_id} Mon 18:00 Push Day" in listing and "Bench 4x8" in listing

        await handle_update(ctx, with_text(load_update("text_plan_today"), "/gym week"))
        week = sent_texts(client)[-1]
        assert "Mon 18:00 Push Day" in week and "— rest" in week

        await handle_update(ctx, with_text(load_update("text_plan_today"),
                                           f"/gym rm {slot_id}"))
        assert sent_texts(client)[-1] == "Removed."

        await handle_update(ctx, with_text(load_update("text_plan_today"), "/gym"))
        assert "rest day" in sent_texts(client)[-1].lower()


async def test_journal_streak_counts_yesterday_when_today_missing(db_session):
    user_id = await _owner_id(db_session)
    today = await _local_today(db_session, user_id)
    await db_session.execute(delete(JournalEntry).where(JournalEntry.user_id == user_id))
    db_session.add_all(
        [
            JournalEntry(user_id=user_id, date=today - timedelta(days=1)),
            JournalEntry(user_id=user_id, date=today - timedelta(days=2)),
        ]
    )
    await db_session.commit()
    assert await journal_streak(db_session, user_id, today) == 2
    db_session.add(JournalEntry(user_id=user_id, date=today))
    await db_session.commit()
    assert await journal_streak(db_session, user_id, today) == 3
