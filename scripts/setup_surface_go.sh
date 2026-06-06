#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/infoscreen}"
PORT="${PORT:-8765}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

cd "$APP_DIR"

mkdir -p "$APP_DIR/photos" "$APP_DIR/public_photos" "$HOME/.config/systemd/user" "$HOME/.config/autostart"

if command -v apt >/dev/null 2>&1; then
  echo "[INFO] Installing runtime packages with apt"
  sudo apt update
  sudo apt install -y python3 curl ca-certificates ffmpeg imagemagick chromium || true
fi

chmod +x "$APP_DIR/fetch_live_data.py" 2>/dev/null || true
chmod +x "$APP_DIR/fetch_event_stream.py" 2>/dev/null || true
chmod +x "$APP_DIR/build_photos_json.py" 2>/dev/null || true

cat > "$HOME/.config/systemd/user/infoscreen-http.service" <<EOF
[Unit]
Description=InfoScreen local HTTP server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_BIN -m http.server $PORT --bind 0.0.0.0
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

cat > "$HOME/.config/systemd/user/infoscreen-live-data.service" <<EOF
[Unit]
Description=Fetch InfoScreen weather and market data
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_BIN $APP_DIR/fetch_live_data.py
EOF

cat > "$HOME/.config/systemd/user/infoscreen-live-data.timer" <<'EOF'
[Unit]
Description=Run InfoScreen live data fetch every 5 minutes

[Timer]
OnBootSec=20
OnUnitActiveSec=5min
Unit=infoscreen-live-data.service

[Install]
WantedBy=timers.target
EOF

cat > "$HOME/.config/systemd/user/infoscreen-event-stream.service" <<EOF
[Unit]
Description=Fetch InfoScreen multilingual news stream
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_BIN $APP_DIR/fetch_event_stream.py
EOF

cat > "$HOME/.config/systemd/user/infoscreen-event-stream.timer" <<'EOF'
[Unit]
Description=Run InfoScreen news stream fetch every 5 minutes

[Timer]
OnBootSec=40
OnUnitActiveSec=5min
Unit=infoscreen-event-stream.service

[Install]
WantedBy=timers.target
EOF

cat > "$HOME/.config/systemd/user/infoscreen-photos.service" <<EOF
[Unit]
Description=Build InfoScreen photo manifest

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_BIN $APP_DIR/build_photos_json.py
EOF

cat > "$HOME/.config/systemd/user/infoscreen-photos.timer" <<'EOF'
[Unit]
Description=Refresh InfoScreen photo manifest every 5 minutes

[Timer]
OnBootSec=30
OnUnitActiveSec=5min
Unit=infoscreen-photos.service

[Install]
WantedBy=timers.target
EOF

cat > "$HOME/.config/autostart/infoscreen-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=InfoScreen Kiosk
Exec=sh -c 'sleep 5; chromium --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble http://127.0.0.1:$PORT/?v=\$(date +%%s)'
X-GNOME-Autostart-enabled=true
EOF

systemctl --user daemon-reload
systemctl --user enable --now infoscreen-http.service
systemctl --user enable --now infoscreen-live-data.timer
systemctl --user enable --now infoscreen-event-stream.timer
systemctl --user enable --now infoscreen-photos.timer

systemctl --user start infoscreen-live-data.service || true
systemctl --user start infoscreen-event-stream.service || true
systemctl --user start infoscreen-photos.service || true

sudo loginctl enable-linger "$USER" || true

echo
printf '[OK] InfoScreen services installed for %s\n' "$APP_DIR"
printf '[OK] Open: http://127.0.0.1:%s/\n' "$PORT"
printf '[OK] Status: bash scripts/infoscreen_status.sh\n'
