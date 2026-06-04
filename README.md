# Surface Info TTY

ASCII-style local information screen for an old Surface Go running Ubuntu. It is designed for Chromium kiosk mode and displays local schedule, weather, market quotes, and basic status panels.

## What it does

- Shows a fixed ASCII/TTY style dashboard optimized for the small Surface Go screen.
- Reads local calendar data from `schedule.json`.
- Reads weather data from `weather.json`.
- Reads market quote data from `market.json`.
- Keeps Apple Calendar private by exporting schedule data on the Mac and syncing only the generated JSON file to Surface.
- Lets Surface fetch weather and market data by itself with a systemd user timer.

## Architecture

```text
Mac
  cybercalendar export.py schedule.json
  launchd every 5 minutes
  scp schedule.json to Surface

Surface Go Ubuntu
  python3 -m http.server 8765
  systemd user timer every 5 minutes
  fetch_live_data.py -> weather.json + market.json
  Chromium kiosk -> http://127.0.0.1:8765/
```

## Surface quick start

```bash
mkdir -p ~/infoscreen
cd ~/infoscreen
python3 -m http.server 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The dashboard should be served over HTTP rather than opened with `file://`, because the page uses `fetch()` to load JSON files.

## Surface live data timer

Copy the files in `surface/` to `~/infoscreen` and `~/.config/systemd/user/`, then run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now infoscreen-live-data.timer
systemctl --user start infoscreen-live-data.service
sudo loginctl enable-linger "$USER"
```

## Mac schedule sync

Copy `mac/sync_schedule.sh` to the Mac directory containing `export.py`, then update:

```bash
SURFACE_USER="rody"
SURFACE_HOST="10.168.1.207"
REMOTE_SCHEDULE_JSON="/home/rody/infoscreen/schedule.json"
```

Install the plist under:

```text
~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist
```

Load and trigger it:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist
launchctl kickstart -k gui/$(id -u)/com.renchi.infoscreen.schedule-sync
```

## Repo layout

```text
index.html
surface/fetch_live_data.py
surface/systemd/infoscreen-live-data.service
surface/systemd/infoscreen-live-data.timer
mac/sync_schedule.sh
mac/com.renchi.infoscreen.schedule-sync.plist
sample/schedule.json
sample/weather.json
sample/market.json
```
