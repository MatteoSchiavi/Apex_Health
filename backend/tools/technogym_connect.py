"""Owner-only manual Technogym connection & sync (§0/§16.7, §11, §23 Phase 6).

Connecting the REAL Technogym account is a human step, performed here or via
the /settings/integrations endpoints — never by automated code and never from
tests:

    cd backend
    uv run python tools/technogym_connect.py start       # prints the authorize URL
    #   -> open it, log into Technogym, approve; the provider redirects to
    #      TECHNOGYM_REDIRECT_URI where the running API completes the flow.
    #   If that redirect is NOT reachable from where the browser runs, paste
    #   the 'code' query parameter from the (failed) redirect URL into:
    uv run python tools/technogym_connect.py complete <code> <state>
    uv run python tools/technogym_connect.py sync        # incremental sync now
    uv run python tools/technogym_connect.py sync --backfill
    uv run python tools/technogym_connect.py status

`complete`/the API callback store the OAuth tokens app-layer-encrypted in
integrations.credentials_encrypted (§17); `start`/`complete` require
TECHNOGYM_CLIENT_ID/SECRET in the environment (§5, §24 — register at
developer.technogym.com first). The password never exists in this flow at
all; refresh tokens rotate automatically on sync.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.connectors.technogym.client import build_live_client
from app.connectors.technogym.flow import (
    OAuthFlowError,
    complete_authorization,
    create_pending_authorization,
)
from app.connectors.technogym.sync import run_user_sync_with_escalation
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json
from app.core.redis import get_redis
from app.models.activity import Activity
from app.models.integration import Integration
from app.models.user import AuthCredential, User


async def _owner(session) -> User:
    cred = await session.scalar(
        select(AuthCredential).where(AuthCredential.role == "owner")
    )
    if cred is None:
        sys.exit("No owner account found — start the API once to bootstrap it (§15).")
    user = await session.get(User, cred.user_id)
    if user is None:  # pragma: no cover
        sys.exit("Owner credential points at a missing user.")
    return user


async def _integration(session, user: User) -> Integration:
    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user.id, Integration.provider == "technogym"
        )
    )
    if integration is None:
        integration = Integration(
            user_id=user.id, provider="technogym", status="active"
        )
        session.add(integration)
        await session.flush()
    return integration


async def cmd_start(args: argparse.Namespace) -> None:
    redis = get_redis()
    try:
        async with sessionmaker() as session:
            user = await _owner(session)
            state, url = await create_pending_authorization(redis, user)
        print("Open this URL, log into Technogym and approve (manual step, §0):")
        print(f"\n  {url}\n")
        print("state (single-use, 10 min):", state)
        print(
            "If the redirect lands somewhere the API cannot serve, copy the "
            "'code' parameter from the redirect URL and run:\n"
            "  uv run python tools/technogym_connect.py complete <code> <state>"
        )
    finally:
        await redis.aclose()


async def cmd_complete(args: argparse.Namespace) -> None:
    redis = get_redis()
    try:
        async with sessionmaker() as session:
            try:
                outcome = await complete_authorization(
                    session, redis, code=args.code, state=args.state
                )
            except OAuthFlowError as exc:
                sys.exit(f"Authorization failed: {exc}")
        print(f"Connected Technogym for user {outcome['user_id']}; tokens stored encrypted.")
        print("Run `uv run python tools/technogym_connect.py sync --backfill` to pull history.")
    finally:
        await redis.aclose()


async def cmd_sync(args: argparse.Namespace) -> None:
    async with sessionmaker() as session:
        user = await _owner(session)
        integration = await _integration(session, user)
        tokens = None
        if integration.credentials_encrypted:
            tokens = decrypt_json(integration.credentials_encrypted)
        try:
            client = build_live_client(tokens)
        except Exception as exc:
            sys.exit(f"Cannot build Technogym client: {exc}\nRun `start`/`complete` first.")
        if args.backfill:
            integration.last_synced_at = None  # §6.3: NULL watermark = full walk
            await session.commit()
        report = await run_user_sync_with_escalation(
            session, user, integration, client
        )
        if report is None:
            sys.exit("Sync failed — see logs; integrations.consecutive_failures incremented.")
        print(
            f"mode={report.mode} pages={report.workout_pages} "
            f"workouts_seen={report.workouts_seen} new={report.new_workouts} "
            f"details={report.details_fetched} "
            f"raw={report.raw_rows_stored} unprocessed={report.raw_rows_unprocessed}"
        )
        for note in report.notes:
            print(f"note: {note}")


async def cmd_status(args: argparse.Namespace) -> None:
    async with sessionmaker() as session:
        user = await _owner(session)
        integration = await _integration(session, user)
        print(
            f"user={user.id} tz={user.timezone} provider=technogym "
            f"status={integration.status} "
            f"credentials={'stored' if integration.credentials_encrypted else 'missing'} "
            f"last_synced_at={integration.last_synced_at} "
            f"consecutive_failures={integration.consecutive_failures}"
        )
        n = await session.scalar(
            select(func.count()).select_from(Activity).where(Activity.user_id == user.id)
        )
        print(f"activities: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="mint the authorize URL + state (owner opens it manually)")
    p_complete = sub.add_parser("complete", help="finish the flow from a pasted code+state")
    p_complete.add_argument("code")
    p_complete.add_argument("state")
    p_sync = sub.add_parser("sync", help="run a sync now (incremental by default)")
    p_sync.add_argument("--backfill", action="store_true", help="re-walk full history (§6.3)")
    sub.add_parser("status", help="show integration state and row counts")
    args = parser.parse_args()

    handlers = {
        "start": cmd_start,
        "complete": cmd_complete,
        "sync": cmd_sync,
        "status": cmd_status,
    }
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
