"""Replay retained Oura sleep records after the corrected v2 mapper.

Operator command; no upstream calls or deletion of original raw records.
  python -m tools.replay_oura --user-id 1 --start 2026-09-01 --end 2026-10-07
Scope is provider scoring days; at most 366 dates / 10,000 raw records.
"""
import argparse
import asyncio
import json
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.oura.normalize import normalize_raw_row
from app.core.db import sessionmaker
from app.features.engine import compute_user_range
from app.models.integration import RawIngest
from app.models.user import AuthCredential, User
from app.services.evidence import scope_lock


async def replay(session, user, start, end):
    if not 0 <= (end - start).days <= 365:
        raise ValueError("A closed range of at most 366 days is required")
    await scope_lock(session, user.id, "changes")
    credential = await session.get(AuthCredential, user.id)
    if credential and credential.disabled:
        raise ValueError("The account is disabled")
    rows = (await session.scalars(select(RawIngest).where(
        RawIngest.user_id == user.id, RawIngest.source == "oura",
        RawIngest.payload_type.in_(("daily_sleep", "sleep")),
        RawIngest.raw_json["day"].astext.between(str(start), str(end)),
    ).order_by(RawIngest.fetched_at, RawIngest.id).limit(10001))).all()
    if len(rows) > 10000:
        raise ValueError("More than 10,000 raw records; choose a smaller range")
    stats = NormalizerStats()
    for raw in rows:
        await normalize_raw_row(session, raw, raw.raw_json, ZoneInfo(user.timezone), stats)
        raw.processed = True
    return {"replayed": len(rows), "sleep_upserted": stats.sleep_upserted, "hrv_upserted": stats.hrv_upserted}


async def run(user_id, start, end):
    async with sessionmaker() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise ValueError("Account does not exist")
        result = await replay(session, user, start, end)
        await session.commit()
        result["recomputed"] = await compute_user_range(session, user, start, end)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if args.user_id <= 0 or not 0 <= (args.end - args.start).days <= 365:
        parser.error("A positive user ID and closed range of at most 366 days are required")
    print(json.dumps(asyncio.run(run(args.user_id, args.start, args.end)), default=str))


if __name__ == "__main__":
    main()
