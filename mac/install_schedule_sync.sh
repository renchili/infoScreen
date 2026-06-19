#!/usr/bin/env bash
set -Eeuo pipefail

LABEL="com.renchi.infoscreen.schedule-sync"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/InfoScreen"
PLIST="$LAUNCH_AGENT_DIR/$LABEL.plist"
SYNC_INTERVAL="${INFOSCREEN_SYNC_INTERVAL:-300}"

find_sync_script() {
  if [[ -n "${INFOSCREEN_SCHEDULE_SYNC_SCRIPT:-}" ]]; then
    printf '%s\n' "$INFOSCREEN_SCHEDULE_SYNC_SCRIPT"
    return
  fi

  if [[ $# -gt 0 && -n "${1:-}" ]]; then
    printf '%s\n' "$1"
    return
  fi

  local candidates=()

  while IFS= read -r item; do
    candidates+=("$item")
  done < <(
    find "$SCRIPT_DIR" -maxdepth 1 -type f \
      \( -name '*schedule*sync*.sh' -o -name '*calendar*sync*.sh' -o -name '*schedule*.sh' \) \
      | sort
  )

  if [[ "${#candidates[@]}" -eq 1 ]]; then
    printf '%s\n' "${candidates[0]}"
    return
  fi

  printf 'Unable to auto-detect schedule sync script under %s\n' "$SCRIPT_DIR" >&2
  printf 'Pass it explicitly, for example:\n' >&2
  printf '  bash mac/install_schedule_sync.sh mac/YOUR_SYNC_SCRIPT.sh\n' >&2
  printf 'Or set INFOSCREEN_SCHEDULE_SYNC_SCRIPT=/absolute/path/to/script.sh\n' >&2

  if [[ "${#candidates[@]}" -gt 1 ]]; then
    printf 'Detected multiple candidates:\n' >&2
    printf '  %s\n' "${candidates[@]}" >&2
  fi

  false
}

xml_escape() {
  sed \
    -e 's/&/\&amp;/g' \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g' \
    -e "s/'/\&apos;/g" \
    -e 's/"/\&quot;/g'
}

SYNC_SCRIPT="$(find_sync_script "${1:-}")"

if [[ "$SYNC_SCRIPT" != /* ]]; then
  SYNC_SCRIPT="$REPO_ROOT/$SYNC_SCRIPT"
fi

if [[ ! -f "$SYNC_SCRIPT" ]]; then
  printf 'Sync script does not exist: %s\n' "$SYNC_SCRIPT" >&2
  false
fi

chmod +x "$SYNC_SCRIPT"

mkdir -p "$LAUNCH_AGENT_DIR" "$LOG_DIR"

CMD="cd \"$REPO_ROOT\" && \"$SYNC_SCRIPT\""
CMD_XML="$(printf '%s' "$CMD" | xml_escape)"
REPO_ROOT_XML="$(printf '%s' "$REPO_ROOT" | xml_escape)"
STDOUT_XML="$(printf '%s' "$LOG_DIR/schedule-sync.log" | xml_escape)"
STDERR_XML="$(printf '%s' "$LOG_DIR/schedule-sync.err.log" | xml_escape)"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"\>
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>

  <key>WorkingDirectory</key>
  <string>$REPO_ROOT_XML</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>$CMD_XML</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>$SYNC_INTERVAL</integer>

  <key>StandardOutPath</key>
  <string>$STDOUT_XML</string>

  <key>StandardErrorPath</key>
  <string>$STDERR_XML</string>
</dict>
</plist>
PLIST

plutil -lint "$PLIST"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

printf 'Installed LaunchAgent: %s\n' "$PLIST"
printf 'Repo root: %s\n' "$REPO_ROOT"
printf 'Sync script: %s\n' "$SYNC_SCRIPT"
printf 'Interval seconds: %s\n' "$SYNC_INTERVAL"
