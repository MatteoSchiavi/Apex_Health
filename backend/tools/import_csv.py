"""CSV import CLI (owner convenience): python -m tools.import_csv --file path

The API route (POST /imports/csv, session-auth multipart) is the friends
surface; this CLI exists for the owner's own bulk backfills over SSH.

    cd backend && PYTHONPATH=. python -m tools.import_csv --file ~/health.csv
"""

import argparse
import asyncio
import json

from sqlalchemy import select

from app.core.db import sessionmaker
from app.services.csv_import import import_csv
from app.models.user import User


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import a health CSV (workouts or daily metrics).")
    parser.add_argument("--file", required=True, help="path to the CSV file")
    parser.add_argument("--email", default=None, help="target account email (default: owner)")
    args = parser.parse_args()

    with open(args.file, "rb") as fh:
        content = fh.read()

    async with sessionmaker() as session:
        from app.models.user import AuthCredential

        if args.email:
            cred = await session.scalar(
                select(AuthCredential).where(AuthCredential.email == args.email)
            )
        else:
            cred = await session.scalar(
                select(AuthCredential).where(AuthCredential.role == "owner")
            )
        if cred is None:
            raise SystemExit(
                "no matching account — pass --email or bootstrap the owner first"
            )
        target = await session.get(User, cred.user_id)
        if target is None:  # pragma: no cover
            raise SystemExit("credential row has no user")
        report = await import_csv(
            session, target.id, args.file, content, target.timezone
        )
        await session.commit()
        print(json.dumps({"user": target.id, **report.as_dict()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
