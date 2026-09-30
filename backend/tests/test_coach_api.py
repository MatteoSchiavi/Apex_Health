import os
"""Coach API end-to-end: events, context docs, gym plan generation,
in-gym session tracking (next exercise + rest timer), feedback — with the
multi-user isolation law asserted where it matters most."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.gym_detail import GymDayPlan, GymExercise, GymSetLog
from app.models.user import User

CSRF = {"X-CSRF-Token": "test"}
OWNER = (os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])


async def _login(client: AsyncClient, email: str, password: str) -> None:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password}, headers=CSRF
    )
    assert resp.status_code == 200


async def _make_friend(client: AsyncClient, db_session, n: int) -> tuple[User, str, str]:
    """Owner mints an invite; the friend redeems it (§6.4 flow)."""
    from app.auth.invites import create_invite, redeem_invite

    owner = (
        (await db_session.scalars(select(User).order_by(User.id).limit(1))).first()
    )
    invite = await create_invite(db_session, created_by=owner.id)
    email = f"friend{n}@coachtests.dev"  # unique across the whole pytest session
    user, _credential, _invite = await redeem_invite(
        db_session, invite.code, f"Friend {n}", email, "friend-password-1"
    )
    await db_session.commit()
    return user, email, "friend-password-1"


def _event_payload(**over):
    payload = {
        "title": "Ski week Dolomites",
        "kind": "ski",
        # +2 days: inside the default 3-day taper window so the advisor
        # actually adjusts the generated plan
        "starts_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "priority": 1,
        "taper_days": 3,
        "notes": "fresh legs matter",
    }
    payload.update(over)
    return payload


@pytest.fixture(autouse=True)
async def clean_coach_tables(db_session):
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE user_events, user_context_docs, session_feedback, "
            "gym_day_plans, gym_day_exercises, gym_set_logs, gym_schedule_slots, "
            "training_plans, planned_sessions RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


# ------------------------------------------------------------------ events


async def test_event_crud_roundtrip(client: AsyncClient):
    await _login(client, *OWNER)
    created = await client.post("/events", json=_event_payload(), headers=CSRF)
    assert created.status_code == 201
    event_id = created.json()["id"]

    listed = (await client.get("/events")).json()
    ski = next(e for e in listed if e["id"] == event_id)
    assert ski["kind"] == "ski" and ski["priority"] == 1

    updated = await client.patch(
        f"/events/{event_id}", json=_event_payload(title="Ski week moved"), headers=CSRF
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Ski week moved"

    deleted = await client.delete(f"/events/{event_id}", headers=CSRF)
    assert deleted.status_code == 204
    assert (await client.get("/events")).json() == []


async def test_event_rejects_unknown_kind(client: AsyncClient):
    await _login(client, *OWNER)
    resp = await client.post("/events", json=_event_payload(kind="quidditch"), headers=CSRF)
    assert resp.status_code == 422


async def test_events_are_user_scoped(client: AsyncClient, db_session):
    """Foreign event ids answer 404, never leak (§22 isolation law)."""
    await _login(client, *OWNER)
    event_id = (await client.post("/events", json=_event_payload(), headers=CSRF)).json()["id"]

    friend, email, password = await _make_friend(client, db_session, 1)
    client.cookies.clear()
    await _login(client, email, password)
    assert (await client.get("/events")).json() == []
    foreign = await client.patch(
        f"/events/{event_id}", json=_event_payload(title="hijack"), headers=CSRF
    )
    assert foreign.status_code == 404
    foreign_delete = await client.delete(f"/events/{event_id}", headers=CSRF)
    assert foreign_delete.status_code == 404


# ------------------------------------------------------------ context docs


async def test_context_doc_put_and_get(client: AsyncClient):
    await _login(client, *OWNER)
    put = await client.put(
        "/context-docs/injuries",
        json={"content": "Left knee aches after long skis. Prefer low impact when sore."},
        headers=CSRF,
    )
    assert put.status_code == 200
    docs = (await client.get("/context-docs")).json()
    assert docs[0]["doc_kind"] == "injuries"
    assert "Left knee" in docs[0]["content"]
    # upsert replaces content
    await client.put("/context-docs/injuries", json={"content": "updated"}, headers=CSRF)
    docs = (await client.get("/context-docs")).json()
    assert len(docs) == 1 and docs[0]["content"] == "updated"


async def test_context_doc_rejects_unknown_kind(client: AsyncClient):
    await _login(client, *OWNER)
    resp = await client.put("/context-docs/secret", json={"content": "x"}, headers=CSRF)
    assert resp.status_code == 422


# --------------------------------------------------------------- gym plans


async def test_generate_plan_applies_taper_and_tracks_sets(client: AsyncClient, db_session):
    """The owner requirement end-to-end: ski race Saturday -> no leg-hammering
    today; then the in-gym tracker (next exercise, set logging, rest timer)."""
    await _login(client, *OWNER)
    # priority-1 ski event in 2 days, inside its taper window
    await client.post("/events", json=_event_payload(), headers=CSRF)

    generated = await client.post(f"/gym/plan/{date.today().isoformat()}/generate", headers=CSRF)
    assert generated.status_code == 200
    body = generated.json()
    assert body["source"] == "ai"  # advisor adjusted something
    assert "taper" in body["adjustment_note"]
    exercises = body["exercises"]
    assert exercises
    assert all(ex["name"] for ex in exercises)
    leg_heavy = [
        ex for ex in exercises if ex["muscle_group"] == "legs" and ex["impact_level"] == "high"
    ]
    assert leg_heavy == []  # no high-impact leg work inside the taper window

    plan_id = body["plan_id"]
    confirm = await client.post(f"/gym/plan/{date.today().isoformat()}/confirm", headers=CSRF)
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "confirmed"

    # in-gym tracker: first exercise, log sets, rest timer value
    nxt = await client.get(f"/gym/session/{plan_id}/next")
    assert nxt.status_code == 200
    first = nxt.json()
    assert first["exercise"] is not None
    assert first["reps_target"]
    target = first["exercise"]

    for set_number in range(1, target["sets"] + 1):
        logged = await client.post(
            f"/gym/session/{plan_id}/log",
            json={
                "gym_day_exercise_id": target["gym_day_exercise_id"],
                "set_number": set_number,
                "reps_done": 10,
                "weight_kg": 60.0,
            },
            headers=CSRF,
        )
        assert logged.status_code == 200
        assert logged.json()["rest_seconds"] == target["rest_seconds"]

    # after the last set, the exercise is complete -> next points elsewhere
    after = (await client.get(f"/gym/session/{plan_id}/next")).json()
    assert after["exercise"]["gym_day_exercise_id"] != target["gym_day_exercise_id"]

    logs = (await db_session.scalars(select(GymSetLog))).all()
    assert len(logs) == target["sets"]
    plan = (await db_session.scalars(select(GymDayPlan))).one()
    assert plan.status == "confirmed"


async def test_generate_is_idempotent_per_day(client: AsyncClient):
    await _login(client, *OWNER)
    first = await client.post(f"/gym/plan/{date.today().isoformat()}/generate", headers=CSRF)
    second = await client.post(f"/gym/plan/{date.today().isoformat()}/generate", headers=CSRF)
    assert first.json()["plan_id"] == second.json()["plan_id"]


async def test_plan_endpoints_are_user_scoped(client: AsyncClient, db_session):
    await _login(client, *OWNER)
    plan_id = (
        await client.post(f"/gym/plan/{date.today().isoformat()}/generate", headers=CSRF)
    ).json()["plan_id"]

    friend, email, password = await _make_friend(client, db_session, 2)
    client.cookies.clear()
    await _login(client, email, password)
    assert (await client.get(f"/gym/session/{plan_id}/next")).status_code == 404
    log = await client.post(
        f"/gym/session/{plan_id}/log",
        json={"gym_day_exercise_id": 1, "set_number": 1, "reps_done": 10},
        headers=CSRF,
    )
    assert log.status_code == 404


# ---------------------------------------------------------------- feedback


async def test_feedback_roundtrip_drives_soreness_rules(client: AsyncClient):
    await _login(client, *OWNER)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    posted = await client.post(
        "/gym/feedback",
        json={
            "date": yesterday,
            "activity_kind": "ski",
            "rpe": 8,
            "soreness": ["knees"],
            "injury_flag": False,
            "notes": "knees a little achy",
        },
        headers=CSRF,
    )
    assert posted.status_code == 201
    listed = (await client.get("/gym/feedback")).json()
    assert listed and listed[0]["soreness"] == ["knees"]

    # generate today's plan -> the advisor must reflect the knee note
    generated = await client.post(f"/gym/plan/{date.today().isoformat()}/generate", headers=CSRF)
    note = generated.json()["adjustment_note"]
    assert "knees" in note
    exercises = generated.json()["exercises"]
    assert all(
        not (ex["movement_pattern"] == "plyo" and ex["muscle_group"] == "legs")
        for ex in exercises
    )


# --------------------------------------------------- context doc isolation


async def test_context_docs_are_user_scoped(client: AsyncClient, db_session):
    await _login(client, *OWNER)
    await client.put("/context-docs/goals", json={"content": "Sub-40 10k this year"}, headers=CSRF)
    friend, email, password = await _make_friend(client, db_session, 3)
    client.cookies.clear()
    await _login(client, email, password)
    assert (await client.get("/context-docs")).json() == []
