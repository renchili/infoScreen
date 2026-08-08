#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SURFACE_DIR="$REPO_DIR/surface"
SURFACE_ENV_DIR="$SURFACE_DIR/.env"
SURFACE_WEB_DIR="$SURFACE_DIR/web"
MIGRATION_BACKUP_DIR="$SURFACE_ENV_DIR/migration_backup"
SYSTEMD_SOURCE_DIR="$SURFACE_DIR/deploy/systemd/user"
REVIEW_URL="http://127.0.0.1:8765/local-events/studio/"
REVIEW_STATE_URL="http://127.0.0.1:8765/api/local-events/review/state"

mkdir -p "$SYSTEMD_USER_DIR" "$SURFACE_ENV_DIR" "$SURFACE_WEB_DIR"

install_system_dependencies() {
  local packages=()

  command -v python3 >/dev/null 2>&1 || packages+=(python3)
  command -v curl >/dev/null 2>&1 || packages+=(curl)

  if command -v python3 >/dev/null 2>&1; then
    python3 -m pip --version >/dev/null 2>&1 || packages+=(python3-pip)
  else
    packages+=(python3-pip)
  fi

  if ! command -v chromium >/dev/null 2>&1 \
    && ! command -v chromium-browser >/dev/null 2>&1 \
    && ! command -v google-chrome >/dev/null 2>&1 \
    && ! command -v google-chrome-stable >/dev/null 2>&1; then
    packages+=(chromium)
  fi

  if [ "${#packages[@]}" -gt 0 ]; then
    echo "[INSTALL] system packages: ${packages[*]}"
    sudo apt-get update
    sudo apt-get install -y "${packages[@]}"
  fi
}

install_python_dependencies() {
  if python3 - <<'PY'
import pydantic
import playwright

major = int(pydantic.__version__.split(".", 1)[0])
if major != 2:
    raise SystemExit(f"Pydantic 2 is required, found {pydantic.__version__}")
PY
  then
    echo "[OK] Python runtime dependencies already available"
    return
  fi

  echo "[INSTALL] Python runtime dependencies"
  if ! python3 -m pip install --user "pydantic>=2,<3" playwright; then
    python3 -m pip install --user --break-system-packages "pydantic>=2,<3" playwright
  fi

  python3 - <<'PY'
import pydantic
import playwright

major = int(pydantic.__version__.split(".", 1)[0])
if major != 2:
    raise SystemExit(f"Pydantic 2 is required, found {pydantic.__version__}")
print(f"[OK] pydantic={pydantic.__version__}; playwright=available")
PY
}

install_playwright_browser() {
  echo "[INSTALL] Playwright-managed Chromium"
  python3 -m playwright install chromium
  python3 - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    executable = Path(playwright.chromium.executable_path)
    if not executable.is_file():
        raise SystemExit(
            "Playwright Chromium is missing after installation: "
            f"{executable}"
        )
    print(f"[OK] playwright-managed-chromium={executable}")
PY
}

import_graphical_session_environment() {
  local names=()
  local name

  for name in DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR; do
    if [ -n "${!name:-}" ]; then
      names+=("$name")
    fi
  done

  if [ "${#names[@]}" -eq 0 ]; then
    echo "[WARN] no graphical session variables are present; opening the interactive feedback browser requires running this installer from the Surface desktop session" >&2
    return
  fi

  systemctl --user import-environment "${names[@]}"
  if command -v dbus-update-activation-environment >/dev/null 2>&1; then
    dbus-update-activation-environment --systemd "${names[@]}" >/dev/null 2>&1 || true
  fi
  echo "[OK] imported graphical session environment: ${names[*]}"
}

preserve_legacy_path() {
  local source="$1"
  local name="$2"
  local backup="$MIGRATION_BACKUP_DIR/$name"

  mkdir -p "$MIGRATION_BACKUP_DIR"
  if [ -e "$backup" ] || [ -L "$backup" ]; then
    echo "[ERROR] migration conflict: both $source and $backup exist; no data was removed" >&2
    exit 1
  fi

  mv "$source" "$backup"
  echo "[PRESERVE] moved conflicting legacy $name -> surface/.env/migration_backup/$name"
}

move_runtime_file() {
  local name="$1"
  local source="$REPO_DIR/$name"
  local destination="$SURFACE_ENV_DIR/$name"

  if [ ! -f "$source" ]; then
    return
  fi

  if [ ! -e "$destination" ]; then
    mv "$source" "$destination"
    echo "[MIGRATE] moved $name -> surface/.env/$name"
    return
  fi

  if [ -f "$destination" ] && cmp -s "$source" "$destination"; then
    rm -f "$source"
    echo "[CLEAN] removed byte-identical root duplicate $name"
    return
  fi

  preserve_legacy_path "$source" "$name"
}

move_runtime_dir() {
  local name="$1"
  local source="$REPO_DIR/$name"
  local destination="$SURFACE_ENV_DIR/$name"

  if [ ! -d "$source" ]; then
    return
  fi

  if [ ! -e "$destination" ]; then
    mv "$source" "$destination"
    echo "[MIGRATE] moved $name/ -> surface/.env/$name/"
    return
  fi

  preserve_legacy_path "$source" "$name"
}

verify_http_service() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "$REVIEW_URL" >/tmp/infoscreen-local-event-review.html 2>/dev/null \
      && grep -q "LOCAL EVENT REVIEW" /tmp/infoscreen-local-event-review.html; then
      break
    fi
    sleep 1
  done

  if ! curl -fsS "$REVIEW_URL" >/tmp/infoscreen-local-event-review.html \
    || ! grep -q "LOCAL EVENT REVIEW" /tmp/infoscreen-local-event-review.html; then
    echo "[ERROR] Local Event Review did not become available at $REVIEW_URL" >&2
    systemctl --user status infoscreen-http.service --no-pager -l >&2 || true
    journalctl --user -u infoscreen-http.service -n 120 --no-pager >&2 || true
    exit 1
  fi

  if ! curl -fsS "$REVIEW_STATE_URL" \
    | python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload.get("ok") is True; assert isinstance(payload.get("sources"), list)' ; then
    echo "[ERROR] Local Event Review state API is unavailable: $REVIEW_STATE_URL" >&2
    systemctl --user status infoscreen-http.service --no-pager -l >&2 || true
    journalctl --user -u infoscreen-http.service -n 120 --no-pager >&2 || true
    exit 1
  fi

  echo "[READY] dashboard: http://127.0.0.1:8765/"
  echo "[READY] Local Event Review: $REVIEW_URL"
}

install_system_dependencies
install_python_dependencies
install_playwright_browser
import_graphical_session_environment

for file in \
  schedule.json \
  weather.json \
  market.json \
  market_config.json \
  event_stream.json \
  local_event_search_results.json \
  photos.json \
  sync_status.json
do
  move_runtime_file "$file"
done

for dir in photos public_photos logs; do
  move_runtime_dir "$dir"
done

for file in \
  serve_infoscreen.py \
  fetch_live_data.py \
  fetch_event_stream.py \
  build_photos_json.py \
  search_local_events.py \
  event_extract.py \
  rebuild_ddg_event_cache.py \
  calendar_board.css \
  calendar_board.js \
  local_events.css \
  local_events.js \
  market_custom.css \
  market_custom.js \
  official_source_registry.json
do
  if [ -f "$REPO_DIR/$file" ]; then
    rm -f "$REPO_DIR/$file"
    echo "[CLEAN] removed root source leftover $file"
  fi
done

if [ -d "$REPO_DIR/assets" ] && [ -d "$SURFACE_WEB_DIR/assets" ]; then
  rm -rf "$REPO_DIR/assets"
  echo "[CLEAN] removed root source leftover assets/"
fi

cp "$REPO_DIR"/surface/deploy/systemd/user/*.service "$SYSTEMD_USER_DIR"/
cp "$REPO_DIR"/surface/deploy/systemd/user/*.timer "$SYSTEMD_USER_DIR"/

systemctl --user daemon-reload
systemctl --user enable --now infoscreen-http.service
systemctl --user enable --now infoscreen-live-data.timer
systemctl --user enable --now infoscreen-event-stream.timer
systemctl --user enable --now infoscreen-local-events.timer

systemctl --user restart infoscreen-http.service
systemctl --user start infoscreen-live-data.service
systemctl --user start infoscreen-event-stream.service
systemctl --user start --no-block infoscreen-local-events.service

printf '\n[CHECK] root Python files:\n'
find "$REPO_DIR" -maxdepth 1 -type f -name '*.py' -print || true
printf '\n[CHECK] root runtime/static leftovers:\n'
find "$REPO_DIR" -maxdepth 1 \( -name 'market.json' -o -name 'market_config.json' -o -name 'event_stream.json' -o -name 'local_event_search_results.json' -o -name 'photos.json' -o -name 'calendar_board.*' -o -name 'local_events.*' -o -name 'market_custom.*' -o -name 'official_source_registry.json' \) -print || true
printf '\n[CHECK] generated local events json:\n'
ls -l "$SURFACE_ENV_DIR/local_event_search_results.json" 2>/dev/null || true

systemctl --user list-timers --all --no-pager | grep -Ei 'infoscreen|live|event|local' || true
systemctl --user status infoscreen-http.service --no-pager -l | sed -n '1,80p'
verify_http_service
