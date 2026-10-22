"""Exercise the deployed backend with synthetic accounts on a disposable stack.

Requires --allow-test-writes; use only against an isolated release-test
deployment. Adds a friend account, CSV activities and a synthetic training plan.
Credentials come from the process environment and are never printed.
"""

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path
from datetime import UTC, datetime
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


async def first_plan(friend, owner):
    """Exercise a new athlete's consent, plan and completion with real persistence."""
    ai = (await friend.get("/athlete/ai")).json()
    assert ai["consent"] is None and ai["effective_access"] == "disabled"
    assert (await friend.post("/coach/chats", headers=csrf(friend), json={"text": "Synthetic boundary check"})).status_code == 403
    profile = await friend.put("/athlete/profile", headers=csrf(friend), json={
        "expected_revision": 0, "training_focus": ["running"],
        "context": {"main_goal": "Synthetic first plan", "onboarding_step": 5},
    })
    assert profile.status_code == 200
    assert (await friend.get("/athlete/profile")).json()["revision"] == 1
    assert (await friend.get("/athlete/ai")).json()["consent"] is None
    assert (await friend.put("/me", headers=csrf(friend), json={"timezone": "UTC"})).status_code == 200
    day = datetime.now(UTC).date().isoformat()
    uploaded = await friend.post("/lab/documents", headers=csrf(friend), files={
        "file": ("synthetic-plan.txt", b"Synthetic plan: easy run for 20 minutes.", "text/plain"),
    })
    assert uploaded.status_code == 201
    document = uploaded.json()
    reviewed = await friend.post(f"/lab/documents/{document['id']}/confirm", headers=csrf(friend), json={
        "content_hash": document["content_hash"], "reviewed_text": document["excerpt"],
    })
    assert reviewed.status_code == 200
    drafted = await friend.post(f"/lab/documents/{document['id']}/plan-drafts", headers=csrf(friend), json={
        "expected_document_revision": reviewed.json()["revision"],
        "structure": {"title": "Synthetic friend first plan", "starts_on": day, "ends_on": day,
                      "sessions": [{"date": day, "discipline": "running", "duration_min": 20}]},
    })
    assert drafted.status_code == 201
    draft = drafted.json()
    assert not (await friend.get(f"/athlete/day?date={day}")).json()["sessions"]
    confirm_path = f"/lab/plan-drafts/{draft['id']}/confirm"
    payload = {"payload_hash": draft["payload_hash"]}
    assert (await owner.post(confirm_path, headers=csrf(owner), json=payload)).status_code == 404
    assert (await owner.get(f"/lab/documents/{document['id']}/original")).status_code == 404
    assert (await friend.post(confirm_path, headers=csrf(friend), json=payload)).status_code == 200
    sessions = (await friend.get(f"/athlete/day?date={day}")).json()["sessions"]
    assert len(sessions) == 1 and sessions[0]["discipline"] == "running"
    workout_id = sessions[0]["id"]
    workout_path = f"/athlete/planned-sessions/{workout_id}/workout"
    assert (await friend.get(workout_path)).json()["editable"]
    checkin = {"planned_session_id": workout_id, "expected_revision": 0,
               "status": "completed", "rpe": 4, "note": "Synthetic completion"}
    saved = await friend.put("/athlete/checkins", headers=csrf(friend), json=checkin)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert (await friend.put("/athlete/checkins", headers=csrf(friend), json=checkin)).json()["id"] == saved.json()["id"]
    conflict = await friend.put("/athlete/checkins", headers=csrf(friend), json={**checkin, "note": "Stale edit"})
    assert conflict.status_code == 409
    refreshed = (await friend.get(f"/athlete/day?date={day}")).json()["sessions"][0]
    assert refreshed["status"] == "completed" and refreshed["checkin"]["note"] == checkin["note"]
    assert not (await friend.get(workout_path)).json()["editable"]


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
            await first_plan(friend, owner)
            assert (await friend.post("/auth/logout", headers=csrf(friend))).status_code == 204
            assert (await friend.get("/me")).status_code == 401
    print("RELEASE SMOKE: PASSED — auth, CSRF, invitations, roles, CSV idempotency, account isolation, consent, plan activation and completion")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-test-writes", action="store_true")
    args = parser.parse_args()
    if not args.allow_test_writes:
        parser.error("Use --allow-test-writes only for a disposable test deployment")
    asyncio.run(main(args.base_url))
