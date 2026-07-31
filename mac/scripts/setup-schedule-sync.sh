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

Calendar data is exported on the Mac and pushed to the Surface runtime env.
The default remote path is /home/<ssh-user>/infoscreen/surface/.env/schedule.json.

The LaunchAgent stores the resolved host, user, Python runtime, remote path,
and log directory directly in ProgramArguments. It does not depend on shell
exports or a generated mac/local.env file after installation.
EOF
}

find_eventkit_python() {
  local requested="$1"
  local candidate resolved

  for candidate in \
    "$requested" \
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

# Read an existing file only to migrate old installations into plist arguments.
# This script never writes the file, and the installed LaunchAgent does not need it.
if [ -r "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

HOST="${SURFACE_HOST:-}"
USER_NAME="${SURFACE_USER:-}"
LEGACY_REMOTE_PATH="${REMOTE_SCHEDULE_JSON:-~/infoscreen/surface/.env/schedule.json}"
REMOTE_PATH="$LEGACY_REMOTE_PATH"
REQUESTED_PYTHON="${PYTHON_BIN:-}"
INTERVAL="120"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host|--surface-host)
      HOST="${2:-}"
      shift 2
      ;;
    --user|--surface-user)
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

if [[ ! "$USER_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Unsafe SSH user: $USER_NAME" >&2
  exit 1
fi

if [[ ! "$HOST" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "Unsafe SSH host: $HOST" >&2
  exit 1
fi

# Replace the historical default with an explicit absolute Linux home path.
# A custom ~/ path remains supported and is passed through unchanged.
if [ "$REMOTE_PATH" = "~/infoscreen/surface/.env/schedule.json" ]; then
  REMOTE_PATH="/home/${USER_NAME}/infoscreen/surface/.env/schedule.json"
fi

case "$REMOTE_PATH" in
  /*|"~/"*)
    ;;
  *)
    echo "--remote-path must be absolute or begin with ~/" >&2
    exit 1
    ;;
esac

if [[ "$REMOTE_PATH" == *".."* ]]; then
  echo "Unsafe remote path: $REMOTE_PATH" >&2
  exit 1
fi

PYTHON_BIN="$(find_eventkit_python "$REQUESTED_PYTHON" || true)"

if [ -z "$PYTHON_BIN" ]; then
  echo "No Python runtime with EventKit was found." >&2
  echo "Install/configure one, then run again with --python /path/to/python3." >&2
  exit 1
fi

LOCAL_LOG_DIR="$HOME/Library/Logs/infoscreen-sync"
mkdir -p "$HOME/Library/LaunchAgents" "$LOCAL_LOG_DIR"

"$PYTHON_BIN" - \
  "$PLIST_FILE" \
  "$SYNC_SCRIPT" \
  "$PYTHON_BIN" \
  "$HOST" \
  "$USER_NAME" \
  "$REMOTE_PATH" \
  "$LOCAL_LOG_DIR" \
  "$LOCAL_LOG_DIR/launchd.out.log" \
  "$LOCAL_LOG_DIR/launchd.err.log" \
  "$INTERVAL" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
sync_script = sys.argv[2]
python_bin = sys.argv[3]
host = sys.argv[4]
user = sys.argv[5]
remote_path = sys.argv[6]
log_dir = sys.argv[7]
stdout_path = sys.argv[8]
stderr_path = sys.argv[9]
interval = int(sys.argv[10])

payload = {
    "Label": "com.renchili.infoscreen.schedule-sync",
    "ProgramArguments": [
        "/bin/bash",
        sync_script,
        "--python",
        python_bin,
        "--surface-host",
        host,
        "--surface-user",
        user,
        "--remote-path",
        remote_path,
        "--local-json",
        "schedule.json",
        "--log-dir",
        log_dir,
    ],
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
echo "Remote schedule path: $REMOTE_PATH"
echo "Runtime configuration is stored in LaunchAgent ProgramArguments."
if [ -r "$CONFIG_FILE" ]; then
  echo "Legacy config was read for migration only: $CONFIG_FILE"
fi
printf 'Manual test: bash %q --python %q --surface-host %q --surface-user %q --remote-path %q --local-json %q --log-dir %q\n' \
  "$SYNC_SCRIPT" \
  "$PYTHON_BIN" \
  "$HOST" \
  "$USER_NAME" \
  "$REMOTE_PATH" \
  "schedule.json" \
  "$LOCAL_LOG_DIR"
