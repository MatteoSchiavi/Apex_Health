"""Owner Garmin API connection and sync. Keys are entered with a hidden prompt.

    uv run python tools/garmin_sync.py connect
    uv run python tools/garmin_sync.py sync
    uv run python tools/garmin_sync.py sync --backfill
    uv run python tools/garmin_sync.py status

No password login, shared credentials or plaintext token cache is supported.
"""

import argparse
import asyncio
from getpass import getpass
from datetime import date
import sys

from sqlalchemy import func, select, text, update

from app.connectors.garmin.client import build_live_client
from app.connectors.garmin.sync import run_user_sync_with_escalation
from app.core.config import get_settings
from app.core.db import sessionmaker, engine
from app.core.encryption import decrypt_json, encrypt_json
from app.models.activity import Activity
from app.models.integration import Integration
from app.models.user import AuthCredential, User
from app.models.wellness import DailyBiometric, SleepSession


async def _owner(session) -> User:
    cred = await session.scalar(select(AuthCredential).where(AuthCredential.role == "owner"))
    if cred is None:
        sys.exit("No owner account found — start the API once to bootstrap it (§15).")
    user = await session.get(User, cred.user_id)
    if user is None:  # pragma: no cover
        sys.exit("Owner credential points at a missing user.")
    return user


async def _integration(session, user: User) -> Integration:
    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user.id, Integration.provider == "garmin"
        )
    )
    if integration is None:
        integration = Integration(user_id=user.id, provider="garmin", status="active")
        session.add(integration)
        await session.flush()
    return integration


async def cmd_connect(args: argparse.Namespace) -> None:
    from app.connectors.garmin.personal import GarminPersonalClient
    from app.api.integrations import _lock_garmin_connection
    key = getpass("Garmin API key (hidden): ").strip()
    if not key:
        sys.exit("A Garmin API key is required.")
    client = GarminPersonalClient({"auth_type": "personal_api_key", "api_key": key})
    key = ""
    client.history_start = args.from_date
    try:
        async with sessionmaker() as session:
            user = await _owner(session)
            await _lock_garmin_connection(session, user.id)
            await client.authenticate()
            integration = await _integration(session, user)
            integration.credentials_encrypted = encrypt_json(client.dump_tokens())
            integration.status = "active"
            integration.consecutive_failures = 0
            await session.commit()
            print("Garmin API key verified and stored encrypted. Imported history retained.")
            await _run(session, user, integration, client, backfill=True)
    finally:
        await client.aclose()


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
            sys.exit(f"Cannot build Garmin client: {exc}\nRun `connect` first.")
        client.history_start = args.from_date
        try:
            await _run(session, user, integration, client, backfill=args.backfill or args.from_date is not None)
        finally:
            await client.aclose()


async def _run(session, user, integration, client, *, backfill: bool) -> None:
    import hashlib
    lock = int.from_bytes(hashlib.sha256(f"sync:garmin:{user.id}".encode()).digest()[:8], "big", signed=True)
    async with engine.connect() as connection:
        if not await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock}):
            sys.exit("A Garmin API sync is already running; retry when it finishes.")
        original = integration.credentials_encrypted
        integration_id, user_id = integration.id, user.id
        try:
            await _run_locked(session, user, integration, client, backfill=backfill)
        finally:
            try:
                await session.execute(update(Integration).where(
                    Integration.id == integration_id, Integration.user_id == user_id,
                    Integration.status == "active", Integration.credentials_encrypted == original,
                ).values(credentials_encrypted=encrypt_json(client.dump_tokens())))
                await session.commit()
            finally:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock})


async def _run_locked(session, user, integration, client, *, backfill: bool) -> None:
    if backfill:
        integration.last_synced_at = None  # §6.3: NULL last_synced_at = full walk
        await session.commit()
    settings = get_settings()
    report = await run_user_sync_with_escalation(
        session,
        user,
        integration,
        client,
        page_size=settings.garmin_activity_page_size,
        page_delay_s=settings.garmin_page_delay_seconds,
        empty_gap_days=settings.garmin_backfill_empty_gap_days,
        checkpoint=True,  # live runs: normalize+commit per page — kill-safe
    )
    if report is None:
        sys.exit("Sync failed — see logs; integrations.consecutive_failures incremented.")
    print(
        f"mode={report.mode} pages={report.activity_pages} "
        f"activities_seen={report.activities_seen} new={report.new_activities} "
        f"streams={report.streams_fetched} days={report.wellness_days} "
        f"raw={report.raw_rows_stored} unprocessed={report.raw_rows_unprocessed}"
    )
    for note in report.notes:
        print(f"note: {note}")


async def cmd_status(args: argparse.Namespace) -> None:
    async with sessionmaker() as session:
        user = await _owner(session)
        integration = await _integration(session, user)
        print(
            f"user={user.id} tz={user.timezone} provider=garmin "
            f"status={integration.status} "
            f"credentials={'stored' if integration.credentials_encrypted else 'missing'} "
            f"last_synced_at={integration.last_synced_at} "
            f"consecutive_failures={integration.consecutive_failures}"
        )
        for label, model in (
            ("activities", Activity),
            ("sleep_sessions", SleepSession),
            ("daily_biometrics", DailyBiometric),
        ):
            n = await session.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))
            print(f"{label}: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_connect = sub.add_parser("connect", help="verify a Garmin API key entered through a hidden prompt")
    p_connect.add_argument("--from-date", type=date.fromisoformat, help="scan wellness from this inclusive date without stopping at empty gaps")
    p_sync = sub.add_parser("sync", help="run a sync now (incremental by default)")
    p_sync.add_argument("--backfill", action="store_true", help="re-walk full history (§6.3)")
    p_sync.add_argument("--from-date", type=date.fromisoformat, help="scan wellness from this inclusive date without stopping at empty gaps")
    sub.add_parser("status", help="show integration state and row counts")
    args = parser.parse_args()

    handlers = {"connect": cmd_connect, "sync": cmd_sync, "status": cmd_status}
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
