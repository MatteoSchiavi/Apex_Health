"""Explicit bounded historical repair. Does not change observations or decisions.

Run after migrations from backend:
  python -m tools.recompute_features --user-id 1 --start 2026-09-01 --end 2026-10-07
Each target day loads the preceding 28 days; at most 366 dates per invocation.
"""
import argparse
import asyncio
import json
from datetime import date
from app.tasks.feature_engine import _recompute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if args.user_id <= 0 or not 0 <= (args.end - args.start).days <= 365:
        parser.error('A positive user ID and closed range of at most 366 days are required')
    result = asyncio.run(_recompute(args.user_id, args.start.isoformat(), args.end.isoformat()))
    print(json.dumps(result, default=str))


if __name__ == '__main__':
    main()
