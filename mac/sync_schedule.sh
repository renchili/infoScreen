#!/bin/bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PYTHON_BIN="/Users/rody/homebrew/opt/python@3.14/bin/python3.14"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SURFACE_USER="rody"
SURFACE_HOST="10.168.1.207"

LOCAL_SCHEDULE_JSON="schedule.json"
REMOTE_SCHEDULE_JSON="/home/rody/infoscreen/schedule.json"

LOG_DIR="/Users/rody/infoscreen-sync"
LOG_FILE="$LOG_DIR/push_schedule.log"

mkdir -p "$LOG_DIR"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] start"
  echo "SCRIPT_DIR=$SCRIPT_DIR"

  cd "$SCRIPT_DIR"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] export schedule"
  "$PYTHON_BIN" export.py "$LOCAL_SCHEDULE_JSON"

  if [ ! -f "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" ]; then
    echo "ERROR: local schedule not found: $SCRIPT_DIR/$LOCAL_SCHEDULE_JSON"
    exit 1
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] push schedule to surface"
  scp -q "$SCRIPT_DIR/$LOCAL_SCHEDULE_JSON" "${SURFACE_USER}@${SURFACE_HOST}:${REMOTE_SCHEDULE_JSON}"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync ok"
  echo
} >> "$LOG_FILE" 2>&1
