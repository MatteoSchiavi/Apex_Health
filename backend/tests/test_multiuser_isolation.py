"""Multi-user data isolation (§15, §23 Phase 9 AC).

"A friend redeems an invite, logs in ... and sees only their own data."

The AC is asserted BOTH directions and at every user-scoped surface the API
currently serves (labs, gear, integrations): the friend sees only friend
rows and gets 404 (not 403) when addressing the owner's row IDs directly —
404 denies existence, so user IDs and row ownership stay unguessable from
the outside (same convention the single-user API already used).
"""

import os
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gear import Gear
from app.models.medical import LabPanel
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
    client.cookies.clear()  # jar must not leak cookies into later "unauthenticated" probes
    return cookies


async def _create_friend_with_data(
    client: AsyncClient, db_session: AsyncSession, label: str
) -> tuple[dict, int]:
    """Redeem an invite into a friend account and seed one lab panel + one
    gear item owned by that friend. Returns (cookies, user_id)."""
    owner = await _owner_login(client, db_session)
    mint = await client.post("/settings/invites", json={}, headers=CSRF, cookies=owner)
    assert mint.status_code == 201
    code = mint.json()["code"]

    redeem = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": f"Friend {label}",
            "email": f"{label}@friend.example",
            "password": f"a-strong-password-{label}",
        },
        headers=CSRF,
    )
    assert redeem.status_code == 201, redeem.text
    user_id = redeem.json()["user_id"]
    friend_cookies = dict(redeem.cookies)
    client.cookies.clear()  # keep every later call's identity explicit

    session = db_session
    session.add(
        LabPanel(
            user_id=user_id,
            date=date.today(),
            panel_type="blood",
            ferritin_ng_ml=55,
        )
    )
    session.add(
        Gear(user_id=user_id, name=f"{label}'s road bike", gear_type="bike", active=True)
    )
    await session.commit()
    return friend_cookies, user_id


async def _seed_owner_data(db_session: AsyncSession) -> tuple[int, int]:
    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT user_id FROM auth_credentials WHERE role = 'owner'")
    )
    owner_id = row.scalar_one()
    db_session.add(
        LabPanel(
            user_id=owner_id,
            date=date.today(),
            panel_type="blood",
            ferritin_ng_ml=18,  # owner-side low-ferritin story stays intact
        )
    )
    db_session.add(
        Gear(user_id=owner_id, name="Owner's TT bike", gear_type="bike", active=True)
    )
    await db_session.commit()
    return owner_id


async def test_friend_sees_only_their_own_data(client: AsyncClient, db_session):
    owner_cookies = await _owner_login(client, db_session)
    owner_id = await _seed_owner_data(db_session)
    friend_cookies, friend_id = await _create_friend_with_data(
        client, db_session, "alice"
    )

    # --- Labs: friend sees exactly one panel — their own. ---
    friend_labs = await client.get("/labs", cookies=friend_cookies)
    assert friend_labs.status_code == 200
    labs = friend_labs.json()
    assert len(labs) == 1
    assert labs[0]["ferritin"] == 55

    # --- Direct row access to the owner's lab panel is a 404, not a leak. ---
    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT id FROM lab_panels WHERE user_id = :u"), {"u": owner_id}
    )
    owner_lab_id = row.scalar_one()
    assert (
        await client.get(f"/labs/{owner_lab_id}", cookies=friend_cookies)
    ).status_code == 404

    # --- Gear: same story. ---
    friend_gear = await client.get("/gear", cookies=friend_cookies)
    assert friend_gear.status_code == 200
    gear = friend_gear.json()
    assert len(gear) == 1
    assert gear[0]["name"] == "alice's road bike"

    row = await db_session.execute(
        text("SELECT id FROM gear WHERE user_id = :u"), {"u": owner_id}
    )
    owner_gear_id = row.scalar_one()
    assert (
        await client.get(f"/gear/{owner_gear_id}", cookies=friend_cookies)
    ).status_code == 404
    assert (
        await client.post(
            f"/gear/{owner_gear_id}/service",
            json={"service_type": "chain"},
            headers=CSRF,
            cookies=friend_cookies,
        )
    ).status_code == 404

    # --- Owner-only settings stay closed to the friend. ---
    assert (
        await client.get("/settings/invites", cookies=friend_cookies)
    ).status_code == 403

    # --- Reverse direction: the owner sees ONLY owner rows too. ---
    owner_labs = await client.get("/labs", cookies=owner_cookies)
    assert owner_labs.status_code == 200
    assert all(p["ferritin"] != 55 for p in owner_labs.json())

    row = await db_session.execute(
        text("SELECT id FROM lab_panels WHERE user_id = :u"), {"u": friend_id}
    )
    friend_lab_id = row.scalar_one()
    assert (
        await client.get(f"/labs/{friend_lab_id}", cookies=owner_cookies)
    ).status_code == 404


async def test_two_friends_are_isolated_from_each_other(client: AsyncClient, db_session):
    alice_cookies, _ = await _create_friend_with_data(client, db_session, "bob1")
    carol_cookies, _ = await _create_friend_with_data(client, db_session, "carol")

    alice_gear = (await client.get("/gear", cookies=alice_cookies)).json()
    assert len(alice_gear) == 1
    assert "bob1" in alice_gear[0]["name"]

    # Carol cannot touch Alice's gear by ID either.
    from sqlalchemy import text

    row = await db_session.execute(text("SELECT id, user_id, name FROM gear"))
    all_gear = {r[0]: (r[1], r[2]) for r in row.fetchall()}
    alice_gear_id = next(
        gid for gid, (_uid, name) in all_gear.items() if "bob1" in name
    )
    resp = await client.post(
        f"/gear/{alice_gear_id}/service",
        json={"service_type": "chain"},
        headers=CSRF,
        cookies=carol_cookies,
    )
    assert resp.status_code == 404


async def test_sessions_are_per_account_logging_out_does_not_kill_the_other(
    client: AsyncClient, db_session
):
    owner_cookies = await _owner_login(client, db_session)
    mint = await client.post("/settings/invites", json={}, headers=CSRF, cookies=owner_cookies)
    code = mint.json()["code"]
    friend = await client.post(
        "/auth/invite/redeem",
        json={
            "code": code,
            "name": "Session",
            "email": "session@friend.example",
            "password": "a-strong-password-x",
        },
        headers=CSRF,
    )
    friend_cookies = friend.cookies

    # Both principals hold live sessions simultaneously.
    assert (await client.get("/labs", cookies=owner_cookies)).status_code == 200
    assert (await client.get("/labs", cookies=friend_cookies)).status_code == 200

    # Friend logs out; owner's session is unaffected.
    await client.post("/auth/logout", headers=CSRF, cookies=friend_cookies)
    assert (await client.get("/labs", cookies=friend_cookies)).status_code == 401
    assert (await client.get("/labs", cookies=owner_cookies)).status_code == 200
