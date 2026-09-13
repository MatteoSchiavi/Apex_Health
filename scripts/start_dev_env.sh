#!/usr/bin/env bash
# Apex Health — user-space dev environment launcher (no Docker, no root).
#
# Starts PostgreSQL 16 (TimescaleDB + pgvector) and Redis from extracted
# package trees, on the project's canonical non-default ports:
#   PG :5433, Redis :6380
#
# Layout (override any of these via environment):
#   PG_ROOT      where the postgresql-16 debs were extracted
#                (usr/lib/postgresql/16/bin must exist underneath)
#   REDIS_ROOT   where the redis debs were extracted (usr/bin/redis-server)
#   PGDATA       database cluster directory
#   REDISDATA    redis persistence directory
#
# First run initializes the cluster (initdb) and creates the `hcc` role and
# database. Re-running is safe — everything is idempotent.
#
# Where do the package trees come from? scripts/rebuild_pg_redis.sh
# downloads and extracts them. See docs/INSTALL.md §5a for the full recipe.
set -euo pipefail

PG_ROOT="${PG_ROOT:-$HOME/pgsql}"
REDIS_ROOT="${REDIS_ROOT:-$HOME/redis}"
PGDATA="${PGDATA:-$HOME/pgdata}"
REDISDATA="${REDISDATA:-$HOME/redisdata}"
PGPORT="${PGPORT:-5433}"
REDISPORT="${REDISPORT:-6380}"

PG_BIN="$PG_ROOT/usr/lib/postgresql/16/bin"

export LD_LIBRARY_PATH="${PG_ROOT}/usr/lib/x86_64-linux-gnu:${PG_ROOT}/usr/lib:${REDIS_ROOT}/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PATH="$PG_BIN:${REDIS_ROOT}/usr/bin:$PATH"

pg_ok() {
  "$PG_BIN/pg_isready" -h localhost -p "$PGPORT" >/dev/null 2>&1
}

redis_ok() {
  "$REDIS_ROOT/usr/bin/redis-cli" -p "$REDISPORT" ping >/dev/null 2>&1
}

# ---------- PostgreSQL ----------
if pg_ok; then
  echo "postgres: already running on :$PGPORT"
else
  if [ ! -x "$PG_BIN/postgres" ]; then
    echo "postgres binaries not found at $PG_BIN — run scripts/rebuild_pg_redis.sh first" >&2
    exit 1
  fi
  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "postgres: initializing data dir at $PGDATA"
    initdb -D "$PGDATA" -U hcc --auth=trust --encoding=UTF8 --locale=C.UTF-8 >/dev/null
    cat >> "$PGDATA/postgresql.conf" <<EOF
port = $PGPORT
listen_addresses = 'localhost'
unix_socket_directories = '$PGDATA'
shared_preload_libraries = 'timescaledb'
max_connections = 60
shared_buffers = 256MB
jit = off
EOF
  fi
  pg_ctl -D "$PGDATA" -l "$PGDATA/postgres.log" -w start
  pg_ok && echo "postgres: started on :$PGPORT" || { echo "postgres: FAILED to start"; tail -20 "$PGDATA/postgres.log"; exit 1; }
fi

# Ensure hcc role + db exist (idempotent)
if ! psql -h localhost -p "$PGPORT" -U hcc -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='hcc'" | grep -q 1; then
  psql -h localhost -p "$PGPORT" -U hcc -d postgres -c "CREATE ROLE hcc LOGIN SUPERUSER" >/dev/null
fi
if ! psql -h localhost -p "$PGPORT" -U hcc -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='hcc'" | grep -q 1; then
  createdb -h localhost -p "$PGPORT" -U hcc hcc
  echo "created database hcc"
fi

# ---------- Redis ----------
if redis_ok; then
  echo "redis: already running on :$REDISPORT"
else
  if [ ! -x "$REDIS_ROOT/usr/bin/redis-server" ]; then
    echo "redis binaries not found at $REDIS_ROOT/usr/bin — run scripts/rebuild_pg_redis.sh first" >&2
    exit 1
  fi
  mkdir -p "$REDISDATA"
  "$REDIS_ROOT/usr/bin/redis-server" \
    --port "$REDISPORT" --bind 127.0.0.1 --daemonize yes \
    --dir "$REDISDATA" --save 60 1 --logfile "$REDISDATA/redis.log"
  redis_ok && echo "redis: started on :$REDISPORT" || { echo "redis: FAILED to start"; tail -20 "$REDISDATA/redis.log"; exit 1; }
fi

echo "dev env ready: postgresql://hcc@localhost:$PGPORT/hcc | redis://localhost:$REDISPORT/0"
