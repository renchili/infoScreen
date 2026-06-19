#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${INFOSCREEN_CONFIG:-$SCRIPT_DIR/local.env}"

if [ ! -r "$CONFIG_FILE" ]; then
  echo "Missing local config: $CONFIG_FILE" >&2
  echo "Run: bash mac/scripts/setup-schedule-sync.sh --host <ssh-host> --user <ssh-user>" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${PYTHON_BIN:=python3}"
: "${SURFACE_USER:?SURFACE_USER is required in mac/local.env}"
: "${SURFACE_HOST:?SURFACE_HOST is required in mac/local.env}"
: "${REMOTE_SCHEDULE_JSON:=~/infoscreen/schedule.json}"
: "${LOCAL_SCHEDULE_JSON:=schedule.json}"
: "${LOG_DIR:=$HOME/Library/Logs/infoscreen-sync}"

if [ -x "$PYTHON_BIN" ]; then
  PYTHON_CMD="$PYTHON_BIN"
elif command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_CMD="$(command -v "$PYTHON_BIN")"
else
  echo "Python runtime not found: $PYTHON_BIN" >&2
  exit 1
fi

if ! "$PYTHON_CMD" -c 'import EventKit' >/dev/null 2>&1; then
  echo "Python cannot import EventKit: $PYTHON_CMD" >&2
  echo "Run setup again with --python /path/to/python3" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/push_schedule.log"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] start"

  cd "$SCRIPT_DIR"
  "$PYTHON_CMD" export.py "$LOCAL_SCHEDULE_JSON"

  if [ ! -f "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" ]; then
    echo "Generated schedule file missing: $SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"
    exit 1
  fi

  scp -q \
    "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" \
    "${SURFACE_USER}@${SURFACE_HOST}:${REMOTE_SCHEDULE_JSON}"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync ok"
  echo
} >> "$LOG_FILE" 2>&1
