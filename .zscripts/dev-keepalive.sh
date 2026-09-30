#!/usr/bin/env bash
# Apex Health — dev server keepalive.
# Checks if port 3000 is listening; if not, restarts the dev server.
set -e
PORT=3000
if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  echo "[dev-keepalive] dev server already running on port ${PORT}"
  exit 0
fi
echo "[dev-keepalive] dev server not running — restarting..."
cd /home/z/my-project
setsid nohup bun run dev > /tmp/dev-fg.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 12
if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
  echo "[dev-keepalive] dev server started successfully on port ${PORT}"
else
  echo "[dev-keepalive] ERROR: dev server failed to start"
  tail -5 /tmp/dev-fg.log 2>/dev/null || true
  exit 1
fi
