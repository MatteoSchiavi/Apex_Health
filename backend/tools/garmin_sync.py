"""Owner-only manual Garmin connection & sync (§0/§16.7, §23 Phase 1).

Connecting the REAL Garmin account is a human step, performed here — never by
automated code and never from tests:

    cd backend
    GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=... \
        uv run python tools/garmin_sync.py connect      # login + full backfill
    uv run python tools/garmin_sync.py sync             # incremental sync now
    uv run python tools/garmin_sync.py sync --backfill  # re-walk full history
    uv run python tools/garmin_sync.py status

`connect` logs in once via the unofficial garminconnect client, stores the
session tokens app-layer-encrypted in integrations.credentials_encrypted
(§17), and immediately backfills full available history (§6.3). Later runs
resume from the stored tokens — the password is never persisted.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.connectors.garmin.client import build_live_client, LiveGarminClient
from app.connectors.garmin.sync import run_user_sync_with_escalation
from app.core.config import get_settings
from app.core.db import sessionmaker
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
    settings = get_settings()
    if not settings.garmin_email or not settings.garmin_password:
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD in the environment first.")

    def _mfa_prompt() -> str:
        # Interactive one-time code (email/authenticator) — connect is a
        # human step, so input() is available exactly when this runs.
        return input("Garmin MFA one-time code: ").strip()

    async with sessionmaker() as session:
        user = await _owner(session)
        integration = await _integration(session, user)
        client = LiveGarminClient.from_password(
            settings.garmin_email, settings.garmin_password, prompt_mfa=_mfa_prompt
        )
        tokens = client.dump_tokens()
        integration.credentials_encrypted = encrypt_json(tokens)
        await session.commit()
        print(f"Connected Garmin for user {user.id}; session tokens stored encrypted.")
        await _run(session, user, integration, client, backfill=True)


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
        await _run(session, user, integration, client, backfill=args.backfill)


async def _run(session, user, integration, client, *, backfill: bool) -> None:
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
    sub.add_parser("connect", help="log in with GARMIN_EMAIL/GARMIN_PASSWORD, store tokens, backfill")
    p_sync = sub.add_parser("sync", help="run a sync now (incremental by default)")
    p_sync.add_argument("--backfill", action="store_true", help="re-walk full history (§6.3)")
    sub.add_parser("status", help="show integration state and row counts")
    args = parser.parse_args()

    handlers = {"connect": cmd_connect, "sync": cmd_sync, "status": cmd_status}
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
