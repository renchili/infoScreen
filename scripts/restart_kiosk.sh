#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8765}"
URL="http://127.0.0.1:${PORT}/?v=$(date +%s)"

pkill chromium 2>/dev/null || true
pkill chromium-browser 2>/dev/null || true
sleep 1

exec chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  "$URL"
