"""Owned comparison edits, stale-save conflict, audit and provider preservation."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import insert, select

from app.core.config import get_settings
from app.models.activity import Activity, ActivitySourceLink, ActivityStream, Discipline
from app.models.lab import ChangeAudit
from app.models.user import User
from app.services.sport_progress import aerobic_trend
from tests.conftest import csrf_headers, login
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401

CONTEXT = {"route_id": "River loop clockwise", "terrain": "paved", "indoor": True, "time_convention": "elapsed", "effort_type": "easy"}


async def create_activity(session, user_id=1, *, at=None):
    at = at or datetime(2026, 10, 12, 10, tzinfo=UTC)
    discipline_id = await session.scalar(select(Discipline.id).where(Discipline.name == "running"))
    assert discipline_id is not None
    activity = Activity(user_id=user_id, discipline_id=discipline_id, start_time=at, local_date=at.date(),
                        start_tz_offset_minutes=0, duration_s=3600, distance_m=10000,
                        source_metrics={"strava": {"private": "preserve-this", "moving_time_s": 3500}})
    session.add(activity)
    await session.flush()
    session.add(ActivitySourceLink(user_id=user_id, activity_id=activity.id, source="strava", external_id=f"context-{activity.id}"))
    await session.commit()
    return activity


async def authenticate(client):
    settings = get_settings()
    assert (await login(client, settings.owner_email, settings.owner_password)).status_code == 200


async def test_auth_ownership_save_conflict_and_atomic_audit(client, db_session):
    activity = await create_activity(db_session)
    endpoint = f"/activities/{activity.id}/comparison-context"
    assert (await client.get(endpoint)).status_code == 401
    await authenticate(client)
    original = (await client.get(endpoint)).json()
    assert original["providers"] == ["strava"] and "preserve-this" not in str(original)
    body = {"provider": "strava", "expected_revision": original["revision"], "context": CONTEXT, "reviewed": True}
    assert (await client.put(endpoint, json={**body, "reviewed": False}, headers=csrf_headers(client))).status_code == 422
    assert (await client.put(endpoint, json={**body, "provider": "garmin"}, headers=csrf_headers(client))).status_code == 422
    saved = await client.put(endpoint, json=body, headers=csrf_headers(client))
    assert saved.status_code == 200, saved.text
    assert saved.json()["assertions"][0]["context"] == CONTEXT
    assert saved.json()["revision"] != original["revision"]
    assert (await client.put(endpoint, json=body, headers=csrf_headers(client))).status_code == 409
    await db_session.refresh(activity)
    assert activity.source_metrics["strava"] == {"private": "preserve-this", "moving_time_s": 3500}
    audit = (await db_session.scalars(select(ChangeAudit).where(ChangeAudit.user_id == 1, ChangeAudit.action == "activity_comparison_context_saved"))).all()
    assert len(audit) == 1 and audit[0].payload["activity_id"] == activity.id
    assert "preserve-this" not in str(audit[0].payload)
    other = User(name="Other comparison athlete")
    db_session.add(other)
    await db_session.flush()
    private = await create_activity(db_session, other.id)
    private_endpoint = f"/activities/{private.id}/comparison-context"
    assert (await client.get(private_endpoint)).status_code == 404
    assert (await client.put(private_endpoint, json=body, headers=csrf_headers(client))).status_code == 404
    removed = await client.put(endpoint, json={**body, "expected_revision": saved.json()["revision"], "context": None}, headers=csrf_headers(client))
    assert removed.status_code == 200 and removed.json()["assertions"] == []
    await db_session.refresh(activity)
    assert activity.source_metrics == {"strava": {"private": "preserve-this", "moving_time_s": 3500}}


async def test_owned_annotation_workflow_unlocks_real_measured_steady_comparison(client, db_session):
    earlier = await create_activity(db_session, at=datetime(2026, 10, 5, 10, tzinfo=UTC))
    current = await create_activity(db_session)
    for activity, speed in ((earlier, 3.0), (current, 3.15)):
        await db_session.execute(insert(ActivityStream), [{"activity_id": activity.id, "t_offset_s": second,
            "hr": 120, "speed": speed} for second in range(3601)])
    await db_session.commit()
    streams = {}
    for activity in (earlier, current):
        streams[activity.id] = (await db_session.scalars(select(ActivityStream).where(
            ActivityStream.activity_id == activity.id).order_by(ActivityStream.t_offset_s))).all()
    disciplines = {earlier.id: "running", current.id: "running"}
    # These imported activities already contain measured speed/HR but lacked
    # explicit route/session intent. No weather or stream data is fabricated by
    # the save: the indoor assertion only supplies the missing comparison keys.
    assert aerobic_trend([earlier, current], streams, disciplines, "UTC")["value"] is None
    await authenticate(client)
    for activity in (earlier, current):
        endpoint = f"/activities/{activity.id}/comparison-context"
        previous = await client.get(endpoint)
        assert previous.status_code == 200
        result = await client.put(endpoint, json={"provider": "strava", "context": CONTEXT,
            "reviewed": True, "expected_revision": previous.json()["revision"]}, headers=csrf_headers(client))
        assert result.status_code == 200, result.text
        assert result.json()["assertions"][0]["provenance"]["verified"] is False
        await db_session.refresh(activity)
        assert activity.weather_snapshot is None
    comparison = aerobic_trend([earlier, current], streams, disciplines, "UTC")
    assert comparison["value"]["reference_activity_id"] == earlier.id
    assert comparison["value"]["current_activity_id"] == current.id
    assert round(comparison["value"]["speed_change_pct"], 4) == 5
