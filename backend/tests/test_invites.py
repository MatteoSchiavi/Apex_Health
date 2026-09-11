"""Invite flow + owner settings API (§15, §18, §23 Phase 9).

Covers: minting (owner-only), redemption (code -> friend account + session),
the failure modes (unknown/used/expired code, email taken, weak password),
revocation of unused invites, and the /settings/users/{id}/ai-tier owner gate.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
    client.cookies.clear()  # jar must not leak the owner cookie into later probes
    return cookies


async def _mint(client: AsyncClient, owner_cookies: dict, **payload) -> dict:
    resp = await client.post(
        "/settings/invites",
        json=payload or None,
        headers=CSRF,
        cookies=owner_cookies,
    )
    return resp


async def test_owner_mints_and_lists_invite(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    resp = await _mint(client, owner, expires_in_days=14)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"]
    assert len(body["code"]) >= 20  # 128-bit urlsafe — not guessable
    assert body["used_by"] is None
    assert body["expired"] is False

    listed = await client.get("/settings/invites", cookies=owner)
    assert listed.status_code == 200
    assert any(i["code"] == body["code"] for i in listed.json())


async def test_invite_minting_is_owner_only(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]

    # An unauthenticated stranger cannot mint.
    assert (
        await client.post("/settings/invites", json={}, headers=CSRF)
    ).status_code == 401

    # A friend (redeemed account) cannot mint either.
    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Friend",
            "email": "friend1@apexhealth.dev",
            "password": "correct-horse-battery",
        },
        headers=CSRF,
    )
    assert redeem.status_code == 201
    friend_cookies = dict(redeem.cookies)
    client.cookies.clear()  # every later call carries its identity explicitly

    denied = await client.post(
        "/settings/invites", json={}, headers=CSRF, cookies=friend_cookies
    )
    assert denied.status_code == 403
    assert "Owner" in denied.json()["detail"]

    # And friends cannot even list invites.
    listed = await client.get("/settings/invites", cookies=friend_cookies)
    assert listed.status_code == 403


async def test_friend_redeems_logs_in_and_uses_the_session(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]

    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Marco",
            "email": "marco@friend.example",
            "password": "a-strong-password-9",
        },
        headers=CSRF,
    )
    assert redeem.status_code == 201
    body = redeem.json()
    assert body["role"] == "friend"
    assert body["ai_access_tier"] == "cheap_only"

    # Same hardened cookie contract as login (§22.2).
    set_cookie = redeem.headers["set-cookie"]
    assert "hcc_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie

    # The session actually works — friend sees their own (empty) labs list.
    labs = await client.get("/labs", cookies=dict(redeem.cookies))
    assert labs.status_code == 200
    assert labs.json() == []


async def test_invite_code_cannot_be_redeemed_twice(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]

    first = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "First",
            "email": "first@friend.example",
            "password": "a-strong-password-1",
        },
        headers=CSRF,
    )
    assert first.status_code == 201

    second = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Second",
            "email": "second@friend.example",
            "password": "a-strong-password-2",
        },
        headers=CSRF,
    )
    assert second.status_code == 400
    assert "not valid" in second.json()["detail"]

    # No stray account was created for the failed attempt.
    from sqlalchemy import text

    rows = await db_session.execute(
        text("SELECT email FROM auth_credentials WHERE email = 'second@friend.example'")
    )
    assert rows.fetchall() == []


async def test_unknown_and_expired_codes_are_rejected_uniformly(
    client: AsyncClient, db_session
):
    owner = await _owner_login(client, db_session)

    unknown = await client.post(
        "/auth/invite/redeem",
        json={
            "code": "xxxxxxxxxxxxxxxxxxxx",
            "name": "Ghost",
            "email": "ghost@friend.example",
            "password": "a-strong-password-3",
        },
        headers=CSRF,
    )
    assert unknown.status_code == 400

    # Expire an otherwise valid invite directly in the DB.
    code = (await _mint(client, owner)).json()["code"]
    from sqlalchemy import update

    from app.models.user import Invite

    await db_session.execute(
        update(Invite)
        .where(Invite.code == code)
        .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()

    expired = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Late",
            "email": "late@friend.example",
            "password": "a-strong-password-4",
        },
        headers=CSRF,
    )
    assert expired.status_code == 400
    assert expired.json()["detail"] == unknown.json()["detail"]  # no oracle


async def test_redeem_rejects_already_registered_email_but_keeps_invite(
    client: AsyncClient, db_session
):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]

    clash = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Impostor",
            "email": OWNER_EMAIL,  # the owner's email
            "password": "a-strong-password-5",
        },
        headers=CSRF,
    )
    assert clash.status_code == 409

    listed = await client.get("/settings/invites", cookies=owner)
    mine = [i for i in listed.json() if i["code"] == code]
    assert len(mine) == 1
    assert mine[0]["used_by"] is None

    # The invite still works for its intended recipient.
    good = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Real",
            "email": "real@friend.example",
            "password": "a-strong-password-6",
        },
        headers=CSRF,
    )
    assert good.status_code == 201


async def test_weak_password_is_rejected_by_validation(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]

    weak = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Weak",
            "email": "weak@friend.example",
            "password": "short",
        },
        headers=CSRF,
    )
    assert weak.status_code == 422


async def test_unused_invite_can_be_revoked_used_one_cannot(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]
    listed = await client.get("/settings/invites", cookies=owner)
    invite_id = next(i["id"] for i in listed.json() if i["code"] == code)

    assert (
        await client.delete(f"/settings/invites/{invite_id}", headers=CSRF, cookies=owner)
    ).status_code == 204
    assert (
        await client.delete(f"/settings/invites/{invite_id}", headers=CSRF, cookies=owner)
    ).status_code == 404

    # A used invite is redemption history — irrevocable.
    code2 = (await _mint(client, owner)).json()["code"]
    await client.post(
        "/auth/invite/redeem",
        json={
            "code": code2,
            "name": "Used",
            "email": "used@friend.example",
            "password": "a-strong-password-7",
        },
        headers=CSRF,
    )
    listed = await client.get("/settings/invites", cookies=owner)
    used_id = next(i["id"] for i in listed.json() if i["code"] == code2)
    resp = await client.delete(f"/settings/invites/{used_id}", headers=CSRF, cookies=owner)
    assert resp.status_code == 409


async def test_ai_tier_update_is_owner_only_and_validated(client: AsyncClient, db_session):
    owner = await _owner_login(client, db_session)
    code = (await _mint(client, owner)).json()["code"]
    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Tiered",
            "email": "tiered@friend.example",
            "password": "a-strong-password-8",
        },
        headers=CSRF,
    )
    friend_id = redeem.json()["user_id"]
    friend_cookies = dict(redeem.cookies)
    client.cookies.clear()

    # Friend cannot change their own tier.
    denied = await client.patch(
        f"/settings/users/{friend_id}/ai-tier",
        json={"ai_access_tier": "full"},
        headers=CSRF,
        cookies=friend_cookies,
    )
    assert denied.status_code == 403

    # Owner raises it.
    raised = await client.patch(
        f"/settings/users/{friend_id}/ai-tier",
        json={"ai_access_tier": "full"},
        headers=CSRF,
        cookies=owner,
    )
    assert raised.status_code == 200
    assert raised.json()["ai_access_tier"] == "full"

    # Invalid tier -> validation error, not a silent no-op.
    bad = await client.patch(
        f"/settings/users/{friend_id}/ai-tier",
        json={"ai_access_tier": "unlimited"},
        headers=CSRF,
        cookies=owner,
    )
    assert bad.status_code == 422

    # Unknown user -> 404.
    missing = await client.patch(
        "/settings/users/999999/ai-tier",
        json={"ai_access_tier": "full"},
        headers=CSRF,
        cookies=owner,
    )
    assert missing.status_code == 404

    # Owner's own tier is fixed.
    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT user_id FROM auth_credentials WHERE role = 'owner'")
    )
    owner_id = row.scalar_one()
    own = await client.patch(
        f"/settings/users/{owner_id}/ai-tier",
        json={"ai_access_tier": "cheap_only"},
        headers=CSRF,
        cookies=owner,
    )
    assert own.status_code == 409
