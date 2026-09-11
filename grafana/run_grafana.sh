#!/usr/bin/env bash
# Start the temporary Grafana UI against the local dev database.
#
#   grafana/run_grafana.sh          # start (idempotent)
#   grafana/run_grafana.sh stop     # stop
#   grafana/run_grafana.sh status
#
# Requires: the user-space dev stack running (PG :5433, Redis :6380) via
# scripts/start_dev_env.sh, and the Grafana tarball extracted (downloads it
# if missing). Demo data: backend/tools/seed_demo_data.py.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRAFANA_DIST="${GRAFANA_DIST:-/home/z/grafana-dist}"
RUNTIME="${GRAFANA_RUNTIME:-/home/z/grafana-runtime}"
PORT="${GRAFANA_PORT:-3001}"
PSQL_BIN="${PSQL_BIN:-psql}"
DB_ARGS=("-h" "127.0.0.1" "-p" "5433" "-U" "hcc" "-d" "hcc")
TARBALL_URL="https://dl.grafana.com/oss/release/grafana-11.6.3.linux-amd64.tar.gz"

case "${1:-start}" in
  stop)
    if [ -f "$RUNTIME/grafana.pid" ]; then
      kill "$(cat "$RUNTIME/grafana.pid")" 2>/dev/null && echo "grafana stopped" || echo "not running"
      rm -f "$RUNTIME/grafana.pid"
    else
      echo "no pid file — not running?"
    fi
    exit 0
    ;;
  status)
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo "grafana UP on :$PORT"
    else
      echo "grafana DOWN"
      exit 1
    fi
    ;;
esac

if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "grafana already running on :$PORT"
  exit 0
fi

if [ ! -x "$GRAFANA_DIST/bin/grafana" ]; then
  echo "grafana dist missing — downloading $TARBALL_URL"
  mkdir -p "$GRAFANA_DIST" /tmp/grafana-dl
  # dl.grafana.com throttles per connection: pull in parallel ranges.
  LEN=$(curl -sI "$TARBALL_URL" | rg -io 'content-length: \d+' | rg -o '\d+' | tr -d '\r' | head -1)
  N=16; CH=$(( (LEN + N - 1) / N ))
  for i in $(seq 0 $((N-1))); do
    S=$((i*CH)); E=$(( S+CH-1 )); [ $E -ge $LEN ] && E=$((LEN-1))
    curl -fsSL -r "$S-$E" -o "/tmp/grafana-dl/part$i" "$TARBALL_URL" &
  done
  wait
  cat /tmp/grafana-dl/part* > /tmp/grafana-dl/g.tar.gz
  tar -xzf /tmp/grafana-dl/g.tar.gz -C "$GRAFANA_DIST" --strip-components=1
  rm -rf /tmp/grafana-dl
fi

mkdir -p "$RUNTIME/data" "$RUNTIME/logs" "$RUNTIME/plugins"

echo "ensuring grafana_ro role + SELECT grants"
"$PSQL_BIN" "${DB_ARGS[@]}" -f "$REPO_ROOT/grafana/sql/bootstrap.sql" >/dev/null

nohup "$GRAFANA_DIST/bin/grafana" server \
  --homepath "$GRAFANA_DIST" \
  --config "$REPO_ROOT/grafana/grafana.ini" \
  >> "$RUNTIME/logs/grafana.log" 2>&1 &
echo $! > "$RUNTIME/grafana.pid"

for i in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "grafana UP on http://127.0.0.1:$PORT (pid $(cat "$RUNTIME/grafana.pid"))"
    # make the Overview dashboard the org home + pin dark theme
    curl -fsS -u admin:apex-demo -X PUT "http://127.0.0.1:$PORT/api/org/preferences" \
      -H 'Content-Type: application/json' \
      -d '{"homeDashboardUID":"apex-overview","theme":"dark"}' >/dev/null || true
    exit 0
  fi
  sleep 1
done
echo "grafana failed to start — tail of log:"
tail -20 "$RUNTIME/logs/grafana.log"
exit 1
