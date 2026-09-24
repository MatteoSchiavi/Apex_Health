import os
"""Challenges & rankings tests: metric math from seeded canonical data,
leaderboard ordering (times ASC, volumes DESC), isolation, records."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.activity import Activity, Discipline
from app.models.challenge import Challenge, ChallengeMember
from app.models.user import User
from app.models.wellness import DailyBiometric, SleepSession
from app.queries.rankings import compute_metric, global_records, leaderboard

CSRF = {"X-CSRF-Token": "test"}
OWNER = (os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


async def _login(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": OWNER[0], "password": OWNER[1]},
        headers=CSRF,
    )
    assert resp.status_code == 200


async def _make_user(db_session, name: str, seed: bool = True) -> User:
    user = User(name=name)
    db_session.add(user)
    await db_session.flush()
    if seed:
        # two activities: a 5k run (1500s) and a 60min ride at 130 bpm
        run_discipline = (
            await db_session.scalars(
                select(Discipline).where(Discipline.name == "running")
            )
        ).one()
        db_session.add(
            Activity(
                user_id=user.id,
                discipline_id=run_discipline.id,
                start_time=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
                start_tz_offset_minutes=120,
                local_date=date(2026, 9, 20),
                duration_s=1500,
                distance_m=5010,
                avg_hr=160,
            )
        )
        db_session.add(
            Activity(
                user_id=user.id,
                discipline_id=None,
                start_time=datetime(2026, 9, 21, 9, 0, tzinfo=UTC),
                start_tz_offset_minutes=120,
                local_date=date(2026, 9, 21),
                duration_s=3600,
                distance_m=28000,
                avg_hr=130,
                training_load=95,
            )
        )
        db_session.add(
            DailyBiometric(user_id=user.id, date=date(2026, 9, 21), steps=12000)
        )
        db_session.add(
            SleepSession(
                user_id=user.id,
                local_date=date(2026, 9, 21),
                start_time=datetime(2026, 9, 20, 23, 0, tzinfo=UTC),
                end_time=datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
                total_sleep_s=25200,
                sleep_score=88.0,
            )
        )
    await db_session.commit()
    return user


@pytest.fixture(autouse=True)
async def clean_challenge_tables(db_session):
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE activities, activity_source_links, daily_biometrics, "
            "sleep_sessions, challenges, challenge_members, integrations "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def test_compute_metric_values(db_session):
    user = await _make_user(db_session, "metric-athlete")
    assert await compute_metric(db_session, user.id, "activities_count", start=None, end=None) == 2
    assert await compute_metric(db_session, user.id, "distance_m", start=None, end=None) == 5010 + 28000
    assert await compute_metric(db_session, user.id, "steps", start=None, end=None) == 12000
    assert await compute_metric(db_session, user.id, "training_load_sum", start=None, end=None) == 95
    # intensity minutes: both activities ride above the moderate-HR proxy
    # (ride 60 min at 130 bpm + run 25 min at 160 bpm)
    assert await compute_metric(db_session, user.id, "intensity_minutes", start=None, end=None) == 85.0
    assert await compute_metric(db_session, user.id, "sleep_score_avg", start=None, end=None) == 88.0
    assert await compute_metric(db_session, user.id, "5k_time_s", start=None, end=None) == 1500


async def test_leaderboard_orders_times_and_volumes(db_session):
    fast = await _make_user(db_session, "fast")
    slow = await _make_user(db_session, "slow", seed=False)
    slow_activity = await db_session.scalar(select(Activity).where(Activity.user_id == fast.id, Activity.duration_s == 1500))
    # give slow a 5k at 1800s
    run_discipline = (
        await db_session.scalars(select(Discipline).where(Discipline.name == "running"))
    ).one()
    db_session.add(
        Activity(
            user_id=slow.id,
            discipline_id=run_discipline.id,
            start_time=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
            start_tz_offset_minutes=120,
            local_date=date(2026, 9, 20),
            duration_s=1800,
            distance_m=5000,
        )
    )
    await db_session.commit()

    challenge = Challenge(name="5k record", metric="5k_time_s", period="all_time", created_by=fast.id)
    db_session.add(challenge)
    await db_session.flush()
    db_session.add(ChallengeMember(challenge_id=challenge.id, user_id=fast.id))
    db_session.add(ChallengeMember(challenge_id=challenge.id, user_id=slow.id))
    await db_session.commit()

    board = await leaderboard(db_session, challenge, NOW)
    assert board["entries"][0]["display_name"] == "fast"  # lowest time wins
    assert board["entries"][0]["rank"] == 1
    assert board["entries"][1]["value"] == 1800


async def test_leaderboard_ranks_missing_data_last(db_session):
    owner = (await db_session.scalars(select(User).order_by(User.id).limit(1))).first()
    athlete = await _make_user(db_session, "has-data")
    challenge = Challenge(name="Steps", metric="steps", period="all_time", created_by=owner.id)
    db_session.add(challenge)
    await db_session.flush()
    db_session.add(ChallengeMember(challenge_id=challenge.id, user_id=owner.id))
    db_session.add(ChallengeMember(challenge_id=challenge.id, user_id=athlete.id))
    await db_session.commit()
    board = await leaderboard(db_session, challenge, NOW)
    # SUM metrics report 0.0 (not None) for members with no data — the owner
    # ranks last either way; None (rank-exempt) only happens for MIN/AVG
    # metrics like 5k_time_s / sleep_score_avg.
    assert board["entries"][-1]["user_id"] == owner.id
    assert board["entries"][-1]["value"] in (None, 0.0)
    assert board["entries"][0]["user_id"] == athlete.id


async def test_challenge_api_flow(client: AsyncClient, db_session):
    await _login(client)
    created = await client.post(
        "/challenges",
        json={"name": "September steps", "metric": "steps", "period": "monthly"},
        headers=CSRF,
    )
    assert created.status_code == 201
    challenge_id = created.json()["id"]

    # owner auto-joins
    members = (await db_session.scalars(select(ChallengeMember))).all()
    assert len(members) == 1

    listed = (await client.get("/challenges")).json()
    assert any(c["id"] == challenge_id for c in listed)

    detail = await client.get(f"/challenges/{challenge_id}")
    assert detail.status_code == 200
    assert detail.json()["metric"] == "steps"

    left = await client.post(f"/challenges/{challenge_id}/leave", headers=CSRF)
    assert left.status_code == 200
    joined = await client.post(f"/challenges/{challenge_id}/join", headers=CSRF)
    assert joined.status_code == 200


async def test_challenge_api_rejects_unknown_metric(client: AsyncClient):
    await _login(client)
    resp = await client.post(
        "/challenges", json={"name": "x", "metric": "vibes"}, headers=CSRF
    )
    assert resp.status_code == 422


async def test_rankings_endpoint_global_records(client: AsyncClient, db_session):
    await _make_user(db_session, "records-athlete")
    await _login(client)
    resp = await client.get("/rankings", params={"metric": "distance_m"})
    assert resp.status_code == 200
    entries = resp.json()
    assert entries and entries[0]["rank"] == 1
    assert entries[0]["value"] == 5010 + 28000
