# Surface Info TTY

ASCII-style local information screen for an old Surface Go running Ubuntu. It is designed for Chromium kiosk mode and displays local schedule, weather, market quotes, multilingual rolling news, photo flip display, and basic device status.

## What it does

- Runs as a local HTTP dashboard on the Surface Go.
- Opens in Chromium kiosk mode.
- Reads Apple Calendar data from `schedule.json`.
- Reads weather data from `weather.json`.
- Reads market quote data from `market.json`.
- Reads multilingual news data from `event_stream.json`.
- Reads photo manifest data from `photos.json`.
- Keeps Apple Calendar private: the Mac exports only `schedule.json`; the dashboard never connects to your personal calendar directly.
- Surface fetches public weather, market, news, and photo manifest data by itself using systemd user timers.

## Architecture

```text
Mac
  cybercalendar/export.py schedule.json
  launchd every 5 minutes
  scp schedule.json to Surface

Surface Go Ubuntu
  ~/infoscreen/index.html
  ~/infoscreen/fetch_live_data.py       -> weather.json + market.json
  ~/infoscreen/fetch_event_stream.py    -> event_stream.json
  ~/infoscreen/build_photos_json.py     -> photos.json + public_photos/
  python3 -m http.server 8765
  Chromium kiosk -> http://127.0.0.1:8765/
```

## Surface Go Ubuntu install notes

Recommended path for Surface Go:

1. Create an Ubuntu USB installer.
2. Boot Surface Go from USB.
3. Install Ubuntu normally.
4. During install, enable Wi-Fi if possible.
5. After first boot, update packages.
6. Install Chromium and runtime tools.
7. Clone this repo into `~/infoscreen`.
8. Run the setup script in this repo.

Typical commands after Ubuntu is installed:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git python3 curl ca-certificates chromium ffmpeg imagemagick

git clone git@github.com:renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
bash scripts/setup_surface_go.sh
```

If SSH clone is not configured yet, use HTTPS:

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
```

The page must be served over HTTP. Do not open `index.html` with `file://`, because the page uses `fetch()` to read JSON files.

## Surface quick start

```bash
cd ~/infoscreen
python3 -m http.server 8765 --bind 0.0.0.0
```

Open:

```text
http://127.0.0.1:8765/
```

On another device in the same LAN:

```text
http://<surface-ip>:8765/
```

## One-command Surface service setup

Run:

```bash
cd ~/infoscreen
bash scripts/setup_surface_go.sh
```

The script creates and starts:

```text
infoscreen-http.service
infoscreen-live-data.timer
infoscreen-event-stream.timer
infoscreen-photos.timer
```

It also creates a Chromium kiosk autostart entry under:

```text
~/.config/autostart/infoscreen-kiosk.desktop
```

## Systemd user timers on Surface

### HTTP server

```bash
systemctl --user status infoscreen-http.service
systemctl --user restart infoscreen-http.service
journalctl --user -u infoscreen-http.service -n 80 --no-pager
```

### Weather and market data

```bash
systemctl --user status infoscreen-live-data.timer
systemctl --user start infoscreen-live-data.service
journalctl --user -u infoscreen-live-data.service -n 80 --no-pager
```

Generated files:

```text
weather.json
market.json
```

### Multilingual news stream

```bash
systemctl --user status infoscreen-event-stream.timer
systemctl --user start infoscreen-event-stream.service
journalctl --user -u infoscreen-event-stream.service -n 80 --no-pager
```

Generated file:

```text
event_stream.json
```

### Photos manifest

```bash
systemctl --user status infoscreen-photos.timer
systemctl --user start infoscreen-photos.service
journalctl --user -u infoscreen-photos.service -n 80 --no-pager
```

Input folder:

```text
~/infoscreen/photos/
```

Generated output:

```text
~/infoscreen/photos.json
~/infoscreen/public_photos/
```

For iPhone HEIC images, the safest workflow is to convert on macOS first:

```bash
sips -s format jpeg IMG_6338.HEIC --out IMG_6338.jpg
scp IMG_6338.jpg rody@10.168.1.207:/home/rody/infoscreen/photos/
```

Then rebuild the manifest:

```bash
cd ~/infoscreen
python3 build_photos_json.py
```

Linux HEIC decoding can produce the wrong tile or preview layer for some iPhone files. Prefer Mac-generated JPG for important photos.

## Mac schedule sync

The Mac owns Apple Calendar access. It runs your CyberCalendar export, then pushes the generated `schedule.json` to Surface.

Existing script:

```text
mac/sync_schedule.sh
```

Important variables inside it:

```bash
SURFACE_USER="rody"
SURFACE_HOST="10.168.1.207"
REMOTE_SCHEDULE_JSON="/home/rody/infoscreen/schedule.json"
```

The script runs:

```bash
python3 export.py schedule.json
scp schedule.json rody@10.168.1.207:/home/rody/infoscreen/schedule.json
```

Install launchd plist on Mac:

```text
~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist
```

Load it:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.renchi.infoscreen.schedule-sync.plist
launchctl kickstart -k gui/$(id -u)/com.renchi.infoscreen.schedule-sync
```

Check Mac sync log:

```bash
tail -n 80 /Users/rody/infoscreen-sync/push_schedule.log
```

## Maintenance commands

### Check everything

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

### Restart kiosk browser

```bash
cd ~/infoscreen
bash scripts/restart_kiosk.sh
```

### Trigger all Surface refresh jobs once

```bash
systemctl --user start infoscreen-live-data.service
systemctl --user start infoscreen-event-stream.service
systemctl --user start infoscreen-photos.service
```

### List timers

```bash
systemctl --user list-timers --all | grep infoscreen
```

### Follow logs

```bash
journalctl --user -u infoscreen-live-data.service -f
journalctl --user -u infoscreen-event-stream.service -f
journalctl --user -u infoscreen-photos.service -f
```

### Rebuild photo manifest manually

```bash
cd ~/infoscreen
python3 build_photos_json.py
cat photos.json
```

### Re-fetch public data manually

```bash
cd ~/infoscreen
python3 fetch_live_data.py
python3 fetch_event_stream.py
```

## Files

```text
index.html                         Main dashboard page
fetch_live_data.py                 Fetch weather.json and market.json
fetch_event_stream.py              Fetch multilingual news event_stream.json
build_photos_json.py               Build photos.json and public_photos/
mac/sync_schedule.sh               Mac-side calendar export and scp sync
scripts/setup_surface_go.sh        Create Surface services/timers/autostart
scripts/infoscreen_status.sh       Diagnose timers, logs, JSON files, HTTP
scripts/restart_kiosk.sh           Restart Chromium kiosk
photos/                            Original user photos, ignored by git
public_photos/                     Web-normalized generated photos, ignored by git
```

## Runtime JSON files

These are generated on the Surface and should normally stay out of git:

```text
schedule.json
weather.json
market.json
event_stream.json
photos.json
```

The dashboard uses file `Last-Modified` headers to show sync status, so it should be served by the local HTTP server.
