#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/local.env"

if [ -r "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
SURFACE_USER="${SURFACE_USER:-rody}"
: "${SURFACE_HOST:?SURFACE_HOST is required. Run: bash mac/scripts/setup-schedule-sync.sh --host <surface-ip> --user <ssh-user>}"
LOCAL_SCHEDULE_JSON="${LOCAL_SCHEDULE_JSON:-schedule.json}"
REMOTE_SCHEDULE_JSON="${REMOTE_SCHEDULE_JSON:-~/infoscreen/surface/.env/schedule.json}"
LOG_DIR="${LOG_DIR:-$HOME/Library/Logs/infoscreen-sync}"
LOG_FILE="$LOG_DIR/push_schedule.log"

mkdir -p "$LOG_DIR"

case "$REMOTE_SCHEDULE_JSON" in
  ~/*)
    REMOTE_RELATIVE_JSON="${REMOTE_SCHEDULE_JSON#~/}"
    ;;
  *)
    echo "ERROR: REMOTE_SCHEDULE_JSON must be a path below the remote home directory, beginning with ~/" >&2
    exit 1
    ;;
esac

if [[ ! "$REMOTE_RELATIVE_JSON" =~ ^[A-Za-z0-9._/-]+$ ]] || [[ "$REMOTE_RELATIVE_JSON" == *".."* ]]; then
  echo "ERROR: unsafe REMOTE_SCHEDULE_JSON: $REMOTE_SCHEDULE_JSON" >&2
  exit 1
fi

REMOTE_DIR_RELATIVE="${REMOTE_RELATIVE_JSON%/*}"
REMOTE_TMP_RELATIVE="${REMOTE_RELATIVE_JSON}.tmp.$$"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] start"
  echo "SCRIPT_DIR=$SCRIPT_DIR"
  echo "SURFACE_HOST=$SURFACE_HOST"
  echo "REMOTE_SCHEDULE_JSON=$REMOTE_SCHEDULE_JSON"

  cd "$SCRIPT_DIR"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] export schedule"
  "$PYTHON_BIN" export.py "$LOCAL_SCHEDULE_JSON"

  if [ ! -f "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" ]; then
    echo "ERROR: local schedule not found: $SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"
    exit 1
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ensure surface runtime directory"
  ssh -q "${SURFACE_USER}@${SURFACE_HOST}" \
    "mkdir -p -- '$REMOTE_DIR_RELATIVE'"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] upload temporary schedule"
  scp -q "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" \
    "${SURFACE_USER}@${SURFACE_HOST}:${REMOTE_TMP_RELATIVE}"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] publish schedule atomically"
  ssh -q "${SURFACE_USER}@${SURFACE_HOST}" \
    "mv -f -- '$REMOTE_TMP_RELATIVE' '$REMOTE_RELATIVE_JSON'"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync ok"
  echo
} >> "$LOG_FILE" 2>&1
