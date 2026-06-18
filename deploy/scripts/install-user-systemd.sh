#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$SYSTEMD_USER_DIR"

cp "$REPO_DIR"/deploy/systemd/user/*.service "$SYSTEMD_USER_DIR"/ 2>/dev/null || true
cp "$REPO_DIR"/deploy/systemd/user/*.timer "$SYSTEMD_USER_DIR"/ 2>/dev/null || true

systemctl --user daemon-reload

systemctl --user enable --now infoscreen-http.service
systemctl --user enable --now infoscreen-live-data.timer 2>/dev/null || true
systemctl --user enable --now infoscreen-event-stream.timer 2>/dev/null || true
systemctl --user enable --now infoscreen-local-events.timer 2>/dev/null || true

systemctl --user restart infoscreen-http.service

systemctl --user list-timers --all --no-pager | grep -Ei 'infoscreen|live|event|local' || true
systemctl --user status infoscreen-http.service --no-pager -l | sed -n '1,60p'
