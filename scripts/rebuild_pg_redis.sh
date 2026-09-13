#!/usr/bin/env bash
# Apex Health — fetch + extract the user-space PostgreSQL/Redis package trees.
#
# Downloads official .deb packages in parallel range chunks (fast on
# throttled links), then extracts them WITHOUT root into:
#   $HOME/pgsql  (PostgreSQL 16 + TimescaleDB + pgvector)
#   $HOME/redis  (Redis 8)
# Start the services afterwards with scripts/start_dev_env.sh.
#
# This path exists for hosts where you have no Docker and no root — the
# Docker path (infra/docker-compose.yml) is the primary install; see
# docs/INSTALL.md §4/§5a for when to prefer which.
set -uo pipefail

APTROOT="${APT_ROOT:-$HOME/apt-cache}"
PGROOT="${PG_ROOT:-$HOME/pgsql}"
REDISROOT="${REDIS_ROOT:-$HOME/redis}"
DL=$APTROOT/dl
CHUNKS="${CHUNKS:-10}"
mkdir -p "$DL"

PG="https://apt.postgresql.org/pub/repos/apt"
DEB="http://deb.debian.org/debian"

declare -A URLS=(
  [postgresql-16_16.15-1.pgdg13+2_amd64.deb]="$PG/pool/main/p/postgresql-16/postgresql-16_16.15-1.pgdg13%2B2_amd64.deb"
  [postgresql-client-16_16.15-1.pgdg13+2_amd64.deb]="$PG/pool/main/p/postgresql-client-16/postgresql-client-16_16.15-1.pgdg13%2B2_amd64.deb"
  [libpq5_18.6-1.pgdg13+2_amd64.deb]="$PG/pool/main/p/postgresql-18/libpq5_18.6-1.pgdg13%2B2_amd64.deb"
  [postgresql-16-timescaledb_2.30.0+dfsg-1.pgdg13+1_amd64.deb]="$PG/pool/main/t/timescaledb/postgresql-16-timescaledb_2.30.0%2Bdfsg-1.pgdg13%2B1_amd64.deb"
  [postgresql-16-pgvector_0.8.6-1.pgdg13+1_amd64.deb]="$PG/pool/main/p/pgvector/postgresql-16-pgvector_0.8.6-1.pgdg13%2B1_amd64.deb"
  [redis-server_8.0.2-3+deb13u2_amd64.deb]="$DEB/pool/main/r/redis/redis-server_8.0.2-3%2Bdeb13u2_amd64.deb"
  [redis-tools_8.0.2-3+deb13u2_amd64.deb]="$DEB/pool/main/r/redis/redis-tools_8.0.2-3%2Bdeb13u2_amd64.deb"
  [liblzf1_3.6-4+b4_amd64.deb]="$DEB/pool/main/libl/liblzf/liblzf1_3.6-4%2Bb4_amd64.deb"
)

fetch() {
  # fetch <url> <out> — parallel range chunks with single-stream fallback.
  local url="$1" out="$2" size chunks chunk_size i start end
  size=$(curl -sSI "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}' | tail -1)
  if [ -z "$size" ] || [ "$size" -lt 2000000 ]; then
    curl -sS -o "$out" "$url"
    return
  fi
  chunks="$CHUNKS"
  chunk_size=$(( size / chunks + 1 ))
  for i in $(seq 0 $(( chunks - 1 ))); do
    start=$(( i * chunk_size ))
    end=$(( start + chunk_size - 1 ))
    [ "$end" -ge "$size" ] && end=$(( size - 1 ))
    [ "$start" -gt "$end" ] && break
    curl -sS -r "$start-$end" -o "$out.part$i" "$url" &
  done
  wait
  : > "$out"
  for i in $(seq 0 $(( chunks - 1 ))); do
    [ -s "$out.part$i" ] && cat "$out.part$i" >> "$out" && rm -f "$out.part$i"
  done
  got=$(wc -c < "$out")
  if [ "$got" != "$size" ]; then
    echo "size mismatch ($got != $size) — single-stream fallback" >&2
    curl -sS -o "$out" "$url"
  fi
}

cd "$DL"
for f in "${!URLS[@]}"; do
  if [ -s "$f" ]; then echo "have $f"; continue; fi
  echo "== fetching $f =="
  fetch "${URLS[$f]}" "$f"
done
ls -1 *.deb
echo "== extracting =="
rm -rf "$PGROOT" "$REDISROOT"
mkdir -p "$PGROOT" "$REDISROOT"
for deb in postgresql-16_*.deb postgresql-client-16_*.deb libpq5_*.deb \
           postgresql-16-timescaledb_*.deb postgresql-16-pgvector_*.deb; do
  dpkg -x "$deb" "$PGROOT"
done
for deb in redis-server_*.deb redis-tools_*.deb liblzf1_*.deb; do
  dpkg -x "$deb" "$REDISROOT"
done
echo "EXTRACT_OK"
ls "$PGROOT/usr/lib/postgresql/16/bin/postgres" "$REDISROOT/usr/bin/redis-server"
