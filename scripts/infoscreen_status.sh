#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/infoscreen}"
PORT="${PORT:-8765}"
RUNTIME_DIR="$APP_DIR/surface/.env"

age() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "missing"
    return
  fi
  local now mtime diff
  now=$(date +%s)
  mtime=$(stat -c %Y "$f")
  diff=$((now - mtime))
  if (( diff < 60 )); then
    printf '%ss' "$diff"
  else
    printf '%sm%ss' $((diff / 60)) $((diff % 60))
  fi
}

echo "== InfoScreen app dir =="
echo "$APP_DIR"
echo "runtime: $RUNTIME_DIR"

echo
echo "== systemd user services =="
systemctl --user --no-pager --full status infoscreen-http.service 2>/dev/null || true

echo
echo "== timers =="
systemctl --user list-timers --all | grep -E 'infoscreen|NEXT' || true

echo
echo "== unit files =="
systemctl --user list-unit-files | grep -E 'infoscreen|UNIT FILE' || true

echo
echo "== last logs: live data =="
journalctl --user -u infoscreen-live-data.service -n 40 --no-pager || true

echo
echo "== last logs: event stream =="
journalctl --user -u infoscreen-event-stream.service -n 40 --no-pager || true

echo
echo "== last logs: local events =="
journalctl --user -u infoscreen-local-events.service -n 30 --no-pager || true

echo
echo "== last logs: photos =="
journalctl --user -u infoscreen-photos.service -n 30 --no-pager || true

echo
echo "== runtime json files =="
for f in schedule.json weather.json market.json event_stream.json local_event_search_results.json photos.json sync_status.json; do
  path="$RUNTIME_DIR/$f"
  if [[ -f "$path" ]]; then
    printf '%-34s age=%-12s ' "$f" "$(age "$path")"
    stat -c 'size=%s mtime=%y' "$path"
  else
    echo "MISSING $path"
  fi
done

echo
echo "== HTTP check =="
curl -fsSI "http://127.0.0.1:${PORT}/" | head || true

echo
echo "== API/runtime HEAD check =="
for f in weather.json market.json event_stream.json local_event_search_results.json photos.json; do
  printf '%-34s ' "$f"
  curl -fsSI "http://127.0.0.1:${PORT}/$f" | awk 'BEGIN{ORS=" "} /^HTTP|^Last-Modified|^Content-Length/{print}' || true
  echo
done

echo
echo "== quick content check =="
for f in weather.json market.json event_stream.json local_event_search_results.json photos.json; do
  path="$RUNTIME_DIR/$f"
  [[ -f "$path" ]] && echo "--- $path" && head -n 12 "$path"
done
