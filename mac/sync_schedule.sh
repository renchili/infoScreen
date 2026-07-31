#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

usage() {
  cat <<'EOF'
Usage:
  bash mac/sync_schedule.sh \
    --surface-host <ssh-host> \
    --surface-user <ssh-user> \
    --remote-path <remote-schedule-path> \
    [--python <python-with-eventkit>] \
    [--local-json <filename>] \
    [--log-dir <directory>]

Command-line arguments are the authoritative runtime configuration. Legacy
mac/local.env and environment variables are read only as backward-compatible
fallbacks for manual execution.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/local.env"
DEFAULT_LOG_DIR="$HOME/Library/Logs/infoscreen-sync"
PRECONFIG_LOG_FILE="$DEFAULT_LOG_DIR/push_schedule.log"

mkdir -p "$DEFAULT_LOG_DIR"
exec >> "$PRECONFIG_LOG_FILE" 2>&1

CURRENT_STAGE="load legacy configuration"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SURFACE_USER="${SURFACE_USER:-rody}"
SURFACE_HOST="${SURFACE_HOST:-}"
LOCAL_SCHEDULE_JSON="${LOCAL_SCHEDULE_JSON:-schedule.json}"
REMOTE_SCHEDULE_JSON="${REMOTE_SCHEDULE_JSON:-}"
LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"
LOG_FILE="$PRECONFIG_LOG_FILE"
STATUS_FILE="$DEFAULT_LOG_DIR/schedule_sync_status.json"

write_local_status() {
  local state="$1"
  local detail="$2"
  "$PYTHON_BIN" - "$STATUS_FILE" "$state" "$CURRENT_STAGE" "$detail" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "status": sys.argv[2],
    "stage": sys.argv[3],
    "detail": sys.argv[4],
}
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY
}

on_error() {
  local exit_code="$1"
  local line="$2"
  local command="$3"
  trap - ERR
  local detail="exit=$exit_code line=$line command=$command"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync failed stage=$CURRENT_STAGE $detail"
  write_local_status "ERR" "$detail" || true
  exit "$exit_code"
}

trap 'on_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

echo "[$(date '+%Y-%m-%d %H:%M:%S')] start"
echo "SCRIPT_DIR=$SCRIPT_DIR"

if [ -r "$CONFIG_FILE" ]; then
  # Legacy fallback only. setup-schedule-sync.sh no longer creates this file.
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
SURFACE_USER="${SURFACE_USER:-rody}"
SURFACE_HOST="${SURFACE_HOST:-}"
LOCAL_SCHEDULE_JSON="${LOCAL_SCHEDULE_JSON:-schedule.json}"
REMOTE_SCHEDULE_JSON="${REMOTE_SCHEDULE_JSON:-}"
LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"

CURRENT_STAGE="parse arguments"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --surface-host|--host)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      SURFACE_HOST="$2"
      shift 2
      ;;
    --surface-user|--user)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      SURFACE_USER="$2"
      shift 2
      ;;
    --remote-path)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      REMOTE_SCHEDULE_JSON="$2"
      shift 2
      ;;
    --python)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      PYTHON_BIN="$2"
      shift 2
      ;;
    --local-json)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      LOCAL_SCHEDULE_JSON="$2"
      shift 2
      ;;
    --log-dir)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "ERROR: $1 requires a value" >&2
        usage >&2
        exit 2
      fi
      LOG_DIR="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REMOTE_SCHEDULE_JSON="${REMOTE_SCHEDULE_JSON:-~/infoscreen/surface/.env/schedule.json}"
LOG_FILE="$LOG_DIR/push_schedule.log"
STATUS_FILE="$LOG_DIR/schedule_sync_status.json"
mkdir -p "$LOG_DIR"

if [ "$LOG_FILE" != "$PRECONFIG_LOG_FILE" ]; then
  exec >> "$LOG_FILE" 2>&1
fi

if [ -z "$SURFACE_HOST" ]; then
  detail="SURFACE_HOST is required. Pass --surface-host <surface-ip> or reinstall the LaunchAgent."
  echo "ERROR: $detail" >&2
  write_local_status "ERR" "$detail" || true
  exit 1
fi

: "${SURFACE_HOST:?SURFACE_HOST is required. Run: bash mac/scripts/setup-schedule-sync.sh --host <surface-ip> --user <ssh-user>}"

if [[ ! "$SURFACE_USER" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: unsafe Surface user: $SURFACE_USER" >&2
  exit 1
fi

if [[ ! "$SURFACE_HOST" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "ERROR: unsafe Surface host: $SURFACE_HOST" >&2
  exit 1
fi

case "$REMOTE_SCHEDULE_JSON" in
  /*)
    REMOTE_RELATIVE_JSON="$REMOTE_SCHEDULE_JSON"
    ;;
  "~/"*)
    REMOTE_RELATIVE_JSON="${REMOTE_SCHEDULE_JSON#\~/}"
    ;;
  *)
    echo "ERROR: REMOTE_SCHEDULE_JSON must be an absolute path or begin with ~/" >&2
    exit 1
    ;;
esac

if [[ ! "$REMOTE_RELATIVE_JSON" =~ ^/?[A-Za-z0-9._/-]+$ ]] || [[ "$REMOTE_RELATIVE_JSON" == *".."* ]]; then
  echo "ERROR: unsafe REMOTE_SCHEDULE_JSON: $REMOTE_SCHEDULE_JSON" >&2
  exit 1
fi

REMOTE_DIR_RELATIVE="${REMOTE_RELATIVE_JSON%/*}"
REMOTE_TMP_RELATIVE="${REMOTE_RELATIVE_JSON}.tmp.$$"

echo "PYTHON_BIN=$PYTHON_BIN"
echo "SURFACE_HOST=$SURFACE_HOST"
echo "SURFACE_USER=$SURFACE_USER"
echo "REMOTE_SCHEDULE_JSON=$REMOTE_SCHEDULE_JSON"
echo "CONFIG_SOURCE=arguments-with-legacy-fallback"

cd "$SCRIPT_DIR"

CURRENT_STAGE="export EventKit schedule"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CURRENT_STAGE"
"$PYTHON_BIN" export.py "$LOCAL_SCHEDULE_JSON"

if [ ! -f "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" ]; then
  echo "ERROR: local schedule not found: $SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"
  exit 1
fi

CURRENT_STAGE="validate local schedule JSON"
ROW_COUNT="$($PYTHON_BIN - "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(payload, list):
    raise SystemExit("schedule payload must be a JSON array")
for index, row in enumerate(payload):
    if not isinstance(row, dict):
        raise SystemExit(f"schedule row {index} must be an object")
print(len(payload))
PY
)"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] local schedule valid rows=$ROW_COUNT"

CURRENT_STAGE="ensure Surface runtime directory"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CURRENT_STAGE"
ssh -q "${SURFACE_USER}@${SURFACE_HOST}" \
  "mkdir -p -- '$REMOTE_DIR_RELATIVE'"

CURRENT_STAGE="upload temporary schedule"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CURRENT_STAGE"
scp -q "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" \
  "${SURFACE_USER}@${SURFACE_HOST}:${REMOTE_TMP_RELATIVE}"

CURRENT_STAGE="publish schedule atomically"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CURRENT_STAGE"
ssh -q "${SURFACE_USER}@${SURFACE_HOST}" \
  "mv -f -- '$REMOTE_TMP_RELATIVE' '$REMOTE_RELATIVE_JSON'"

CURRENT_STAGE="verify published schedule"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CURRENT_STAGE"
ssh -q "${SURFACE_USER}@${SURFACE_HOST}" \
  "test -s '$REMOTE_RELATIVE_JSON' && python3 -m json.tool '$REMOTE_RELATIVE_JSON' >/dev/null"

CURRENT_STAGE="complete"
write_local_status "OK" "published rows=$ROW_COUNT to $REMOTE_SCHEDULE_JSON"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync ok rows=$ROW_COUNT"
echo
