#!/usr/bin/env python3
"""Validate every Grafana panel SQL against the live dev database.

Extracts rawSql from each dashboard JSON, substitutes Grafana macros
($__timeFilter, $__timeGroupAlias, $user, ${metric}, ${budget}) with
literals, and executes each query via psql. Prints a PASS/FAIL table.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

DASH_DIR = Path("/home/z/apex-health-clone/grafana/dashboards")
PSQL = ["psql", "-h", "127.0.0.1", "-p", "5433", "-U", "hcc", "-d", "hcc",
        "-v", "ON_ERROR_STOP=1", "-X", "-q"]


def substitute(sql: str) -> str:
    sql = sql.replace("$user", "1")
    sql = sql.replace("${metric}", "Vitamin D (25-OH)")
    sql = sql.replace("${budget}", "0.25")
    sql = re.sub(r"\$__timeFilter\(([^()]+(?:\([^()]*\))?[^()]*)\)",
                 r"\1 BETWEEN now() - interval '90 days' AND now()", sql)
    sql = re.sub(r"\$__timeGroupAlias\(([^,]+),'([^']+)'\)",
                 r"date_trunc('day', \1)", sql)
    return sql


def main() -> int:
    failures = 0
    total = 0
    for f in sorted(DASH_DIR.glob("*.json")):
        dash = json.loads(f.read_text())
        for p in dash.get("panels", []):
            for t in p.get("targets", []):
                raw = t.get("rawSql")
                if not raw:
                    continue
                total += 1
                sql = substitute(raw)
                r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
                ok = r.returncode == 0
                if not ok:
                    failures += 1
                name = f"{f.stem} :: {p['title']} [{t['refId']}]"
                print(f"{'PASS' if ok else 'FAIL'}  {name}")
                if not ok:
                    err = (r.stderr or "").strip().splitlines()
                    print("      " + (err[-1] if err else "unknown error"))
                    print("      SQL: " + sql[:160])
    print(f"\n{total - failures}/{total} panel queries pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
