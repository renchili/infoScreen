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

json_summary() {
  local path="$1"
  python3 - "$path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"json=INVALID error={type(exc).__name__}:{exc}")
    raise SystemExit(0)

if isinstance(payload, list):
    print(f"json=OK rows={len(payload)}")
    raise SystemExit(0)

if not isinstance(payload, dict):
    print(f"json=OK type={type(payload).__name__}")
    raise SystemExit(0)

parts = ["json=OK"]
for key in ("status", "updated_at", "last_attempt_at", "last_success_at", "source"):
    value = payload.get(key)
    if value not in (None, ""):
        parts.append(f"{key}={value}")
error = payload.get("error")
if error:
    parts.append(f"error={str(error).replace(chr(10), ' ')[:300]}")
items = payload.get("items")
if isinstance(items, list):
    parts.append(f"items={len(items)}")
print(" ".join(parts))
PY
}

unit_result() {
  local unit="$1"
  echo "--- $unit"
  systemctl --user show "$unit" \
    --property=LoadState \
    --property=ActiveState \
    --property=SubState \
    --property=Result \
    --property=ExecMainStatus \
    --property=ExecMainStartTimestamp \
    --property=ExecMainExitTimestamp \
    --no-pager 2>/dev/null || true
}

echo "== InfoScreen app dir =="
echo "$APP_DIR"
echo "runtime: $RUNTIME_DIR"

echo
echo "== systemd user services =="
systemctl --user --no-pager --full status infoscreen-http.service 2>/dev/null || true

echo
echo "== producer results =="
unit_result infoscreen-live-data.service
unit_result infoscreen-event-stream.service
unit_result infoscreen-local-events.service

echo
echo "== timers =="
systemctl --user list-timers --all --no-pager | grep -E 'infoscreen|NEXT' || true

echo
echo "== unit files =="
systemctl --user list-unit-files --no-pager | grep -E 'infoscreen|UNIT FILE' || true

echo
echo "== last logs: live data =="
journalctl --user -u infoscreen-live-data.service -n 120 --no-pager || true

echo
echo "== last logs: event stream =="
journalctl --user -u infoscreen-event-stream.service -n 80 --no-pager || true

echo
echo "== last logs: local events =="
journalctl --user -u infoscreen-local-events.service -n 60 --no-pager || true

echo
echo "== last logs: photos =="
journalctl --user -u infoscreen-photos.service -n 40 --no-pager || true

echo
echo "== runtime json files =="
for f in schedule.json weather.json market.json event_stream.json local_event_search_results.json photos.json sync_status.json; do
  path="$RUNTIME_DIR/$f"
  if [[ -f "$path" ]]; then
    printf '%-34s age=%-12s ' "$f" "$(age "$path")"
    stat -c 'size=%s mtime=%y' "$path"
    printf '  '
    json_summary "$path"
  else
    echo "MISSING $path"
  fi
done

echo
echo "== HTTP check =="
curl -fsSI "http://127.0.0.1:${PORT}/" | head || true

echo
echo "== API/runtime HEAD check =="
for f in schedule.json weather.json market.json event_stream.json local_event_search_results.json photos.json; do
  printf '%-34s ' "$f"
  curl -fsSI "http://127.0.0.1:${PORT}/$f" | awk 'BEGIN{ORS=" "} /^HTTP|^Last-Modified|^Content-Length|^Cache-Control/{print}' || true
  echo
done

echo
echo "== live payload diagnosis =="
for f in schedule.json weather.json market.json; do
  printf '%-34s ' "$f"
  curl -fsS "http://127.0.0.1:${PORT}/$f?_=$(date +%s)" \
    | python3 -c '
import json,sys
try:
    payload=json.load(sys.stdin)
except Exception as exc:
    print(f"INVALID_RESPONSE {type(exc).__name__}: {exc}")
    raise SystemExit(0)
if isinstance(payload,list):
    print(f"rows={len(payload)}")
else:
    values=[]
    for key in ("status","updated_at","last_attempt_at","last_success_at","error"):
        value=payload.get(key)
        if value not in (None,""):
            values.append(f"{key}={str(value)[:300]}")
    print(" ".join(values) or "no status fields")
' || true
done

echo
echo "== quick content check =="
for f in schedule.json weather.json market.json event_stream.json local_event_search_results.json photos.json; do
  path="$RUNTIME_DIR/$f"
  [[ -f "$path" ]] && echo "--- $path" && head -n 16 "$path"
done

echo
echo "== recovery pointers =="
echo "Weather/Market: journalctl --user -u infoscreen-live-data.service -n 200 --no-pager"
echo "Weather/Market: systemctl --user start infoscreen-live-data.service"
echo "Calendar (run on Mac): tail -n 200 ~/Library/Logs/infoscreen-sync/push_schedule.log"
echo "Calendar (run on Mac): cat ~/Library/Logs/infoscreen-sync/schedule_sync_status.json"
echo "Calendar (run on Mac): launchctl print gui/\$(id -u)/com.renchili.infoscreen.schedule-sync"
