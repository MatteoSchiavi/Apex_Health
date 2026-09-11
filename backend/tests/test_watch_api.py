"""Connect IQ watch backend (§23 Phase 10).

Covers the token lifecycle (mint once / list / soft-revoke, per-user),
the Bearer-authed /watch/today data path (readiness/recovery/strain for the
TOKEN OWNER's LOCAL date, §17), stale-day honesty, the empty-history case,
and structural isolation: a friend's watch token can only ever resolve to
the friend's own daily_features row.
"""

import os
from datetime import date, datetime, UTC
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.features import DailyFeature
from app.models.user import User
from tests.conftest import reset_owner_auth_state

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


async def _owner_login(client: AsyncClient, db_session: AsyncSession) -> dict:
    await reset_owner_auth_state(db_session)
    resp = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=CSRF
    )
    assert resp.status_code == 200
    cookies = dict(resp.cookies)
    client.cookies.clear()
    return cookies


async def _mint_token(client: AsyncClient, cookies: dict, name: str = "fenix") -> dict:
    resp = await client.post(
        "/watch/tokens", json={"name": name}, headers=CSRF, cookies=cookies
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _clear_daily_features(db_session: AsyncSession, *user_ids: int) -> None:
    """Test isolation: the session-scoped schema is NOT re-migrated between
    tests, so feature rows leak across tests. Clear the involved users'
    daily_features before arranging state (PK is (user_id, date))."""
    from sqlalchemy import delete

    await db_session.execute(delete(DailyFeature).where(DailyFeature.user_id.in_(user_ids)))
    await db_session.commit()


async def _seed_today_features(db_session: AsyncSession, user_id: int, **scores) -> date:
    tz = ZoneInfo(
        (await db_session.get(User, user_id)).timezone
    )
    local_today = datetime.now(tz).date()
    db_session.add(
        DailyFeature(
            user_id=user_id,
            date=local_today,
            readiness_score=Decimal(str(scores.get("readiness", 82.5))),
            recovery_score=Decimal(str(scores.get("recovery", 61.0))),
            strain_score=Decimal(str(scores.get("strain", 14.2))),
            data_completeness=scores.get("completeness", "full"),
        )
    )
    await db_session.commit()
    return local_today


async def test_mint_list_revoke_lifecycle(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)

    minted = await _mint_token(client, owner, name="fr965")
    assert len(minted["token"]) >= 32  # 256-bit urlsafe — not guessable
    assert minted["name"] == "fr965"

    listed = (await client.get("/watch/tokens", cookies=owner)).json()
    assert len(listed) == 1
    assert listed[0]["revoked_at"] is None
    assert "token" not in listed[0]  # plaintext never comes back

    # Raw token must not be stored verbatim (same rule as sessions, §22.2).
    from sqlalchemy import text

    rows = await db_session.execute(text("SELECT token_hash FROM device_tokens"))
    hashes = [r[0] for r in rows.fetchall()]
    assert minted["token"] not in hashes

    revoked = await client.delete(
        f"/watch/tokens/{minted['id']}", headers=CSRF, cookies=owner
    )
    assert revoked.status_code == 204
    listed = (await client.get("/watch/tokens", cookies=owner)).json()
    assert listed[0]["revoked_at"] is not None


async def test_watch_today_returns_scores_for_local_today(
    client: AsyncClient, db_session
):
    owner = await _owner_login(client, db_session)
    minted = await _mint_token(client, owner)
    await _clear_daily_features(db_session, 1)
    local_today = await _seed_today_features(
        db_session, minted.get("user_id") or 1, readiness=82.5, recovery=61.0, strain=14.2
    )

    resp = await client.get(
        "/watch/today", headers={"Authorization": f"Bearer {minted['token']}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["readiness"] == 82.5
    assert body["recovery"] == 61.0
    assert body["strain"] == 14.2
    assert body["as_of_date"] == local_today.isoformat()
    assert body["stale"] is False
    assert body["data_completeness"] == "full"

    # last_used_at got stamped by the data call.
    listed = (await client.get("/watch/tokens", cookies=owner)).json()
    assert listed[0]["last_used_at"] is not None


async def test_watch_today_is_stale_honest_when_today_not_scored(
    client: AsyncClient, db_session
):
    owner = await _owner_login(client, db_session)
    minted = await _mint_token(client, owner)

    await _clear_daily_features(db_session, 1)
    tz = ZoneInfo("Europe/Rome")
    yesterday = datetime.now(tz).date()  # will shift the row to a past date below
    from datetime import timedelta

    past = yesterday - timedelta(days=1)
    db_session.add(
        DailyFeature(
            user_id=1, date=past,
            readiness_score=Decimal("71.0"), recovery_score=Decimal("55.0"),
            strain_score=Decimal("18.0"), data_completeness="partial",
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/watch/today", headers={"Authorization": f"Bearer {minted['token']}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["readiness"] == 71.0
    assert body["as_of_date"] == past.isoformat()
    assert body["stale"] is True  # the glance must not claim this is today


async def test_watch_today_with_no_history_returns_nulls(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    minted = await _mint_token(client, owner)

    await _clear_daily_features(db_session, 1)

    resp = await client.get(
        "/watch/today", headers={"Authorization": f"Bearer {minted['token']}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["readiness"] is None
    assert body["recovery"] is None
    assert body["strain"] is None
    assert body["stale"] is True


async def test_bad_missing_and_revoked_tokens_are_401(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    minted = await _mint_token(client, owner)

    assert (await client.get("/watch/today")).status_code == 401
    assert (
        await client.get("/watch/today", headers={"Authorization": "Bearer nope"})
    ).status_code == 401

    await client.delete(f"/watch/tokens/{minted['id']}", headers=CSRF, cookies=owner)
    revoked = await client.get(
        "/watch/today", headers={"Authorization": f"Bearer {minted['token']}"}
    )
    assert revoked.status_code == 401  # revocation is immediate, not eventual


async def test_friend_watch_token_sees_only_friend_data(client: AsyncClient, db_session):
    """Structural isolation: mint a token for a FRIEND, seed both parties'
    daily_features, and prove the token resolves the friend's row only."""
    owner = await _owner_login(client, db_session)
    invite = (
        await client.post("/settings/invites", json={}, headers=CSRF, cookies=owner)
    ).json()["code"]
    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": invite, "name": "Watch Friend",
            "email": "watch@friend.example", "password": "a-strong-password-w",
        },
        headers=CSRF,
    )
    assert redeem.status_code == 201
    friend_id = redeem.json()["user_id"]
    client.cookies.clear()
    await _clear_daily_features(db_session, friend_id, 1)

    # Friend mints their OWN token with their OWN session.
    friend_mint = await client.post(
        "/watch/tokens", json={"name": "watch"}, headers=CSRF,
        cookies=dict(redeem.cookies),
    )
    assert friend_mint.status_code == 201
    friend_token = friend_mint.json()["token"]

    today = await _seed_today_features(db_session, friend_id, readiness=64.0)
    await _seed_today_features(db_session, 1, readiness=99.9)  # owner's row

    resp = await client.get(
        "/watch/today", headers={"Authorization": f"Bearer {friend_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == friend_id
    assert body["readiness"] == 64.0  # friend's values, never the owner's 99.9
    assert body["as_of_date"] == today.isoformat()


async def test_tokens_are_per_user_listing_and_revocation(client: AsyncClient, db_session):
    from sqlalchemy import delete

    from app.models.watch import DeviceToken

    await db_session.execute(delete(DeviceToken))
    await db_session.commit()

    owner = await _owner_login(client, db_session)
    invite = (
        await client.post("/settings/invites", json={}, headers=CSRF, cookies=owner)
    ).json()["code"]
    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": invite, "name": "List Friend",
            "email": "list@friend.example", "password": "a-strong-password-l",
        },
        headers=CSRF,
    )
    friend_cookies = dict(redeem.cookies)
    client.cookies.clear()

    owner_token = await _mint_token(client, owner)
    friend_token = await _mint_token(client, friend_cookies)

    # Owner's list shows only the owner's token.
    owner_list = (await client.get("/watch/tokens", cookies=owner)).json()
    assert [t["id"] for t in owner_list] == [owner_token["id"]]

    # Friend cannot revoke (or even see) the owner's token — 404, not 403.
    resp = await client.delete(
        f"/watch/tokens/{owner_token['id']}", headers=CSRF, cookies=friend_cookies
    )
    assert resp.status_code == 404
