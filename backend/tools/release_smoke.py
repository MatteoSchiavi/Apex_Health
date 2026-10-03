"""Exercise the deployed backend with synthetic accounts on a disposable stack.

Requires --allow-test-writes; use only against an isolated release-test
deployment. Adds a friend account and one CSV activity to each account.
Credentials come from the process environment and are never printed.
"""

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


async def main(base_url):
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as owner:
        assert (await owner.get("/health")).status_code == 200
        assert (await owner.get("/me")).status_code == 401
        response = await owner.post("/auth/login", json={
            "email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"],
        })
        assert response.status_code == 200
        assert (await owner.get("/me")).json()["role"] == "owner"
        assert (await owner.get("/dashboard/overview")).status_code == 200
        assert (await owner.put("/me", json={"units": "metric"})).status_code == 403
        csv = "sport,start_time,duration_s,distance_m\nRunning,2026-09-15T07:30:00Z,600,1000\n"
        filename = f"release-{uuid4().hex}.csv"
        for expected in (1, 0):
            response = await owner.post("/imports/csv", headers=csrf(owner), files={"file": (filename, csv, "text/csv")})
            assert response.status_code == 200
            assert response.json()["activities_upserted"] == expected
        activities = (await owner.get("/activities?limit=100")).json()["items"]
        assert activities
        activity_id = activities[0]["id"]
        invite = await owner.post("/settings/invites", headers=csrf(owner), json={"expires_in_days": 1})
        assert invite.status_code == 201
        async with httpx.AsyncClient(base_url=base_url, timeout=20) as friend:
            redeemed = await friend.post("/auth/invite/redeem", json={
                "code": invite.json()["code"], "name": "Release smoke friend",
                "email": f"release-{uuid4().hex}@example.com",
                "password": secrets.token_urlsafe(24) + "aA1!",
            })
            assert redeemed.status_code == 201
            assert (await friend.get(f"/activities/{activity_id}")).status_code == 404
            assert (await friend.post("/settings/invites", headers=csrf(friend), json={})).status_code == 403
            imported = await friend.post("/imports/csv", headers=csrf(friend), files={"file": (filename, csv, "text/csv")})
            assert imported.status_code == 200
            assert imported.json()["activities_upserted"] == 1
            friend_activities = (await friend.get("/activities")).json()["items"]
            assert len(friend_activities) == 1
            assert friend_activities[0]["id"] != activity_id
            assert (await friend.post("/auth/logout", headers=csrf(friend))).status_code == 204
            assert (await friend.get("/me")).status_code == 401
    print("RELEASE SMOKE: PASSED — auth, CSRF, invitations, roles, CSV idempotency and account isolation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-test-writes", action="store_true")
    args = parser.parse_args()
    if not args.allow_test_writes:
        parser.error("Use --allow-test-writes only for a disposable test deployment")
    asyncio.run(main(args.base_url))
