#!/usr/bin/env bash
# Apex Health — sync-service auto-restart wrapper.
#
# Restarts the sync-service if it has died. Designed to be called from the
# webDevReview cron (or any other periodic caller) — it checks if port 3005
# is listening, and if not, restarts the service detached via setsid.
#
# Usage: bash mini-services/sync-service/keepalive.sh

set -e

PORT=3005
SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/sync-service.log"

# Check if anything is listening on PORT
if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  echo "[keepalive] sync-service already running on port ${PORT}"
  exit 0
fi

echo "[keepalive] sync-service not running — restarting..."
cd "$SERVICE_DIR"
setsid nohup bun run dev > "$LOG_FILE" 2>&1 < /dev/null &
disown 2>/dev/null || true

# Wait briefly + verify
sleep 3
if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  echo "[keepalive] sync-service started successfully on port ${PORT}"
else
  echo "[keepalive] ERROR: sync-service failed to start"
  tail -5 "$LOG_FILE" 2>/dev/null || true
  exit 1
fi
