#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash mac/scripts/setup-schedule-sync.sh \
    --host <ssh-host> \
    --user <ssh-user> \
    [--remote-path <remote-schedule-path>] \
    [--python <python-with-eventkit>] \
    [--interval <seconds>]

The script writes local-only configuration to mac/local.env and creates a
LaunchAgent under ~/Library/LaunchAgents. Neither file is committed to Git.
EOF
}

find_eventkit_python() {
  local requested="$1"
  local configured="$2"
  local candidate resolved

  for candidate in \
    "$requested" \
    "$configured" \
    python3 \
    python3.14 \
    python3.13 \
    python3.12 \
    python3.11
  do
    [ -n "$candidate" ] || continue

    if [ -x "$candidate" ]; then
      resolved="$candidate"
    elif command -v "$candidate" >/dev/null 2>&1; then
      resolved="$(command -v "$candidate")"
    else
      continue
    fi

    if "$resolved" -c 'import EventKit' >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  return 1
}

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
MAC_DIR="$REPO_DIR/mac"
CONFIG_FILE="$MAC_DIR/local.env"
SYNC_SCRIPT="$MAC_DIR/sync_schedule.sh"
PLIST_FILE="$HOME/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist"

HOST=""
USER_NAME=""
REMOTE_PATH=""
REQUESTED_PYTHON=""
INTERVAL="120"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --remote-path)
      REMOTE_PATH="${2:-}"
      shift 2
      ;;
    --python)
      REQUESTED_PYTHON="${2:-}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
  echo "--interval must be a positive integer." >&2
  exit 1
fi

if [ -r "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

HOST="${HOST:-${SURFACE_HOST:-}}"
USER_NAME="${USER_NAME:-${SURFACE_USER:-}}"
REMOTE_PATH="${REMOTE_PATH:-${REMOTE_SCHEDULE_JSON:-~/infoscreen/schedule.json}}"

if [ -z "$HOST" ] && [ -t 0 ]; then
  read -r -p "Surface SSH host: " HOST
fi

if [ -z "$USER_NAME" ] && [ -t 0 ]; then
  read -r -p "Surface SSH user: " USER_NAME
fi

if [ -z "$HOST" ] || [ -z "$USER_NAME" ]; then
  echo "Both --host and --user are required." >&2
  usage >&2
  exit 1
fi

PYTHON_BIN="$(find_eventkit_python "$REQUESTED_PYTHON" "${PYTHON_BIN:-}" || true)"

if [ -z "$PYTHON_BIN" ]; then
  echo "No Python runtime with EventKit was found." >&2
  echo "Install/configure one, then run again with --python /path/to/python3." >&2
  exit 1
fi

LOCAL_LOG_DIR="$HOME/Library/Logs/infoscreen-sync"
mkdir -p "$HOME/Library/LaunchAgents" "$LOCAL_LOG_DIR"

{
  printf 'PYTHON_BIN=%q\n' "$PYTHON_BIN"
  printf 'SURFACE_USER=%q\n' "$USER_NAME"
  printf 'SURFACE_HOST=%q\n' "$HOST"
  printf 'REMOTE_SCHEDULE_JSON=%q\n' "$REMOTE_PATH"
  printf 'LOCAL_SCHEDULE_JSON=%q\n' "schedule.json"
  printf 'LOG_DIR=%q\n' "$LOCAL_LOG_DIR"
} > "$CONFIG_FILE"

chmod 600 "$CONFIG_FILE"

"$PYTHON_BIN" - \
  "$PLIST_FILE" \
  "$SYNC_SCRIPT" \
  "$LOCAL_LOG_DIR/launchd.out.log" \
  "$LOCAL_LOG_DIR/launchd.err.log" \
  "$INTERVAL" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
sync_script = sys.argv[2]
stdout_path = sys.argv[3]
stderr_path = sys.argv[4]
interval = int(sys.argv[5])

payload = {
    "Label": "com.renchili.infoscreen.schedule-sync",
    "ProgramArguments": ["/bin/bash", sync_script],
    "RunAtLoad": True,
    "StartInterval": interval,
    "StandardOutPath": stdout_path,
    "StandardErrorPath": stderr_path,
}

with plist_path.open("wb") as handle:
    plistlib.dump(payload, handle)
PY

plutil -lint "$PLIST_FILE"

UID_VALUE="$(id -u)"
LABEL="com.renchili.infoscreen.schedule-sync"

/bin/launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "gui/$UID_VALUE" "$PLIST_FILE"
/bin/launchctl kickstart -k "gui/$UID_VALUE/$LABEL"

echo "Installed LaunchAgent: $PLIST_FILE"
echo "Local config: $CONFIG_FILE"
echo "Manual test: bash $SYNC_SCRIPT"
