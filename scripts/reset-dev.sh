#!/usr/bin/env bash
# Recreate local dev DB/Redis state from a clean slate (MASTER_SPEC §16.6):
# "tears down and recreates the local dev DB/Redis state from nothing".
#
# Docker mode (host with Docker): compose down -v, bring up db+redis, migrate.
# Direct mode (no Docker, e.g. user-space stack): drop/recreate DATABASE_URL's
# database via asyncpg, migrate, flush Redis.
#
# The owner account is re-bootstrapped automatically at the next API startup (§15).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then set -a; source .env; set +a; fi
: "${DATABASE_URL:?DATABASE_URL must be set (copy .env.example to .env)}"
: "${REDIS_URL:?REDIS_URL must be set}"

if [ "${1:-}" != "-f" ]; then
  read -rp "This destroys local dev DB and Redis state. Continue? [y/N] " answer
  case "$answer" in
    [yY]*) ;;
    *) echo "aborted"; exit 1 ;;
  esac
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "=== Docker mode ==="
  docker compose -f infra/docker-compose.yml down -v
  docker compose -f infra/docker-compose.yml up -d db redis
  echo "waiting for db + redis health..."
  for _ in $(seq 1 60); do
    if [ "$(docker compose -f infra/docker-compose.yml ps --format '{{.Health}}' db redis | grep -c healthy)" = "2" ]; then
      break
    fi
    sleep 1
  done
else
  echo "=== Direct mode (no Docker daemon) ==="
  (cd backend && uv run python tools/reset_direct.py)
fi

echo "=== applying migrations ==="
(cd backend && uv run alembic upgrade head)

echo "=== reset complete ==="
