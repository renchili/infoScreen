#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLIST_SRC="$REPO_DIR/mac/launchagents/com.renchili.infoscreen.schedule-sync.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

if [ ! -f "$PLIST_SRC" ]; then
  echo "missing plist: $PLIST_SRC"
  exit 1
fi

/bin/launchctl bootout "gui/$(id -u)/com.renchili.infoscreen.schedule-sync" 2>/dev/null || true
/bin/launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true

cp "$PLIST_SRC" "$PLIST_DST"

plutil -lint "$PLIST_DST"

: > "$HOME/Library/Logs/infoscreen-schedule-sync.out.log"
: > "$HOME/Library/Logs/infoscreen-schedule-sync.err.log"

/bin/launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
/bin/launchctl kickstart -k "gui/$(id -u)/com.renchili.infoscreen.schedule-sync"

sleep 2

/bin/launchctl print "gui/$(id -u)/com.renchili.infoscreen.schedule-sync" \
  | grep -E 'state =|runs =|last exit code|run interval' -A2 -B2

echo
echo "stdout:"
cat "$HOME/Library/Logs/infoscreen-schedule-sync.out.log" 2>/dev/null || true

echo
echo "stderr:"
cat "$HOME/Library/Logs/infoscreen-schedule-sync.err.log" 2>/dev/null || true
