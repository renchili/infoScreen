#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/infoscreen}"
PORT="${PORT:-8765}"

echo "== InfoScreen app dir =="
echo "$APP_DIR"

echo
echo "== systemd user services =="
systemctl --user --no-pager --full status infoscreen-http.service 2>/dev/null || true

echo
echo "== timers =="
systemctl --user list-timers --all | grep -E 'infoscreen|NEXT' || true

echo
echo "== last logs: live data =="
journalctl --user -u infoscreen-live-data.service -n 20 --no-pager || true

echo
echo "== last logs: event stream =="
journalctl --user -u infoscreen-event-stream.service -n 20 --no-pager || true

echo
echo "== last logs: photos =="
journalctl --user -u infoscreen-photos.service -n 20 --no-pager || true

echo
echo "== json files =="
cd "$APP_DIR"
for f in schedule.json weather.json market.json event_stream.json photos.json; do
  if [[ -f "$f" ]]; then
    stat -c '%n  size=%s  mtime=%y' "$f"
  else
    echo "MISSING $f"
  fi
done

echo
echo "== HTTP check =="
curl -fsSI "http://127.0.0.1:${PORT}/" | head || true

echo
echo "== quick content check =="
for f in weather.json market.json event_stream.json photos.json; do
  [[ -f "$f" ]] && echo "--- $f" && head -n 8 "$f"
done
