#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SURFACE_DIR="$REPO_DIR/surface"
SURFACE_ENV_DIR="$SURFACE_DIR/.env"
SURFACE_WEB_DIR="$SURFACE_DIR/web"

mkdir -p "$SYSTEMD_USER_DIR" "$SURFACE_ENV_DIR" "$SURFACE_WEB_DIR"

move_runtime_file() {
  local name="$1"
  if [ -f "$REPO_DIR/$name" ]; then
    if [ ! -f "$SURFACE_ENV_DIR/$name" ]; then
      mv "$REPO_DIR/$name" "$SURFACE_ENV_DIR/$name"
      echo "[MIGRATE] moved $name -> surface/.env/$name"
    else
      rm -f "$REPO_DIR/$name"
      echo "[CLEAN] removed duplicate root $name"
    fi
  fi
}

move_runtime_dir() {
  local name="$1"
  if [ -d "$REPO_DIR/$name" ]; then
    if [ ! -e "$SURFACE_ENV_DIR/$name" ]; then
      mv "$REPO_DIR/$name" "$SURFACE_ENV_DIR/$name"
      echo "[MIGRATE] moved $name/ -> surface/.env/$name/"
    else
      rm -rf "$REPO_DIR/$name"
      echo "[CLEAN] removed duplicate root $name/"
    fi
  fi
}

# Runtime/state files belong to surface/.env, not repo root.
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

# Remove old root-level Surface runtime/static leftovers after the layout move.
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
      echo "[CLEAN] removed root leftover $file"
    fi
  done

if [ -d "$REPO_DIR/assets" ] && [ -d "$SURFACE_WEB_DIR/assets" ]; then
  rm -rf "$REPO_DIR/assets"
  echo "[CLEAN] removed root leftover assets/"
fi

cp "$REPO_DIR"/deploy/systemd/user/*.service "$SYSTEMD_USER_DIR"/ 2>/dev/null || true
cp "$REPO_DIR"/deploy/systemd/user/*.timer "$SYSTEMD_USER_DIR"/ 2>/dev/null || true

systemctl --user daemon-reload

systemctl --user enable --now infoscreen-http.service
systemctl --user enable --now infoscreen-live-data.timer 2>/dev/null || true
systemctl --user enable --now infoscreen-event-stream.timer 2>/dev/null || true
systemctl --user enable --now infoscreen-local-events.timer 2>/dev/null || true

# Unit files may have changed ExecStart paths, so restart/re-run after daemon-reload.
systemctl --user restart infoscreen-http.service
systemctl --user start infoscreen-live-data.service 2>/dev/null || true
systemctl --user start infoscreen-event-stream.service 2>/dev/null || true
systemctl --user start infoscreen-local-events.service 2>/dev/null || true

printf '\n[CHECK] root Python files:\n'
find "$REPO_DIR" -maxdepth 1 -type f -name '*.py' -print || true
printf '\n[CHECK] root runtime/static leftovers:\n'
find "$REPO_DIR" -maxdepth 1 \( -name 'market.json' -o -name 'market_config.json' -o -name 'event_stream.json' -o -name 'local_event_search_results.json' -o -name 'photos.json' -o -name 'calendar_board.*' -o -name 'local_events.*' -o -name 'market_custom.*' -o -name 'official_source_registry.json' \) -print || true
printf '\n[CHECK] generated local events json:\n'
ls -l "$SURFACE_ENV_DIR/local_event_search_results.json" 2>/dev/null || true

systemctl --user list-timers --all --no-pager | grep -Ei 'infoscreen|live|event|local' || true
systemctl --user status infoscreen-http.service --no-pager -l | sed -n '1,80p'
