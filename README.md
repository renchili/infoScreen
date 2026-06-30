# InfoScreen

InfoScreen is a local kiosk dashboard for an always-on Surface/Ubuntu display.

It shows:

```text
calendar schedule
market watchlist
weather
event/news stream
local official events
photo wall
runtime/sync status
```

The project uses local files, local HTTP, and user-level systemd units. Runtime data is intentionally local and should not be committed.

## Current required reading

Before changing the project, read these files:

```text
metadata.json                  project requirements, constraints, and cleanup plan
docs/project-structure.md      canonical structure and development-boundary rules
docs/design.md                 whole-project design
docs/api-spec.md               HTTP API interaction contract
docs/questions.md              implementation issues and resolution log
```

## Host roles

### Surface / Ubuntu

The Surface host runs:

```text
surface/serve_infoscreen.py
surface/fetch_live_data.py
surface/fetch_event_stream.py
surface/search_local_events.py
user systemd services/timers
dashboard on port 8765
```

### macOS

The Mac host only exports Apple Calendar and pushes `schedule.json` to Surface.

The Mac checkout must not switch to a Surface frontend/crawler branch just to run schedule sync.

## Runtime files

Current verified runtime files:

```text
~/infoscreen/schedule.json
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

Do not change these paths without verifying the running Surface host first.

Schedule verification:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
head -n 20 /tmp/served_schedule.json
```

## Repository layout

Target layout:

```text
deploy/                         systemd templates and install scripts
docs/                           documentation
mac/                            macOS calendar export/sync only
sample/                         sample JSON fixtures
scripts/                        repo/dev/status scripts
surface/                        Surface app implementation
surface/web/index.html          dashboard shell
surface/web/assets/css/         checked-in CSS
surface/web/assets/js/          checked-in browser JS
metadata.json                   project requirements and plan
schedule.json                   local runtime calendar file, not source
```

Checked-in frontend assets should live only under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

Duplicate root-level or `surface/web/*.js|*.css` files are cleanup debt.

## Install on Surface / Ubuntu

Clone or update the repository:

```bash
cd ~
git clone <repo-url> infoscreen
cd ~/infoscreen
```

Install or update user systemd units:

```bash
bash deploy/scripts/install-user-systemd.sh
```

Start/restart the HTTP service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now infoscreen-http.service
systemctl --user restart infoscreen-http.service
```

Open the dashboard:

```text
http://<surface-host>:8765/
http://127.0.0.1:8765/
```

## Start without systemd

For local debugging:

```bash
cd ~/infoscreen
python3 surface/serve_infoscreen.py
```

Then open:

```text
http://127.0.0.1:8765/
```

## Surface service status

Check services and timers:

```bash
systemctl --user status infoscreen-http.service --no-pager -l
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

Check HTTP logs:

```bash
tail -n 80 ~/infoscreen/surface/.env/logs/http.log
tail -n 80 ~/infoscreen/surface/.env/logs/http.err.log
```

The HTTP service must keep writing those file logs unless a documented migration replaces them.

## Calendar schedule sync from Mac

The Mac exports calendar data and pushes `schedule.json` to Surface.

Current Surface target:

```text
~/infoscreen/schedule.json
```

On Mac, configure `mac/local.env` or run setup with an explicit remote path:

```bash
cd /path/to/infoScreen
bash mac/scripts/setup-schedule-sync.sh \
  --host "<surface-host>" \
  --user "<surface-user>" \
  --remote-path "~/infoscreen/schedule.json"
```

Manual sync from Mac:

```bash
bash mac/sync_schedule.sh
```

Verify on Surface:

```bash
cd ~/infoscreen
stat schedule.json
curl -s http://127.0.0.1:8765/schedule.json | python3 -m json.tool | head -n 40
```

## Market and weather refresh

Manual refresh:

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
```

API refresh:

```bash
curl -s -X POST http://127.0.0.1:8765/api/market-refresh | python3 -m json.tool | head -n 80
```

Market config:

```bash
curl -s http://127.0.0.1:8765/api/market-config | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8765/api/market-config \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["AAPL","NVDA","MSFT"]}' | python3 -m json.tool
```

## Local official events

Manual search:

```bash
cd ~/infoscreen
python3 surface/search_local_events.py "Punggol Singapore"
```

API search:

```bash
curl -s -X POST http://127.0.0.1:8765/api/local-events/search \
  -H 'Content-Type: application/json' \
  -d '{"location":"Punggol Singapore"}' | python3 -m json.tool | head -n 120
```

Read current results:

```bash
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 120
```

Local event source rules:

```text
official_source_registry.json stores official homepage/domain identity only
event_sources.json stores verified event listing entrypoints
no third-party aggregators
no guessed domains or guessed /events paths
no hidden fallback to old crawler or fake data
```

## API docs

OpenAPI JSON:

```bash
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80
```

Swagger UI:

```text
http://127.0.0.1:8765/docs
```

If Pydantic is missing:

```bash
python3 -m pip install --user 'pydantic>=2.0'
```

## Runtime backup before destructive git operations

On the deployed Surface host, always back up runtime files before running commands such as `git reset --hard`, branch replacement, file deletion, or any `git clean` command.

```bash
cd ~/infoscreen
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
echo "$backup"
```

Do not run `git clean -fd` on a deployed Surface checkout unless the backup has been made and reviewed.

## Developer checks

Python syntax:

```bash
python3 -m py_compile surface/*.py mac/*.py scripts/ci/*.py
```

Local event self-test:

```bash
python3 surface/search_local_events.py --self-test
```

Repository checks if available:

```bash
python3 scripts/ci/check_repo.py --suite all --scope repository
```

## Troubleshooting

### Dashboard does not load

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 120 --no-pager
tail -n 120 ~/infoscreen/surface/.env/logs/http.err.log
```

### Schedule is stale

```bash
cd ~/infoscreen
stat schedule.json
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json schedule.json
```

Then check Mac schedule-sync logs on the Mac.

### Market or weather is stale

```bash
python3 surface/fetch_live_data.py
curl -s http://127.0.0.1:8765/weather.json | python3 -m json.tool | head -n 40
curl -s http://127.0.0.1:8765/market.json | python3 -m json.tool | head -n 80
journalctl --user -u infoscreen-live-data.service -n 120 --no-pager
```

### Local events are stale or poor quality

```bash
python3 surface/search_local_events.py "Punggol Singapore"
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 160
```

Do not claim extraction quality is fixed until `debug_by_source`, accepted/rejected reasons, and rendered results are reviewed.

### Frontend still looks old

```bash
systemctl --user restart infoscreen-http.service
pkill -f chromium || true
curl -s http://127.0.0.1:8765/ | grep -n "calendar_board\|local_events\|assets/" | head -n 40
```

## Privacy and git hygiene

Do not commit:

```text
schedule.json
surface/.env/
surface/.env/logs/
*.log
__pycache__/
*.pyc
local env files
SSH keys
tokens
personal calendar exports
personal photos
private IP addresses
```

## Current cleanup warning

This branch still has known cleanup debt:

```text
duplicate frontend CSS/JS locations
serve_infoscreen.py frontend patching from previous work
schedule path changes that need reconciliation
HTTP log writing needs verification
Mac schedule-sync changes mixed into a Surface branch
```

Do not treat this branch as clean until the cleanup plan in `metadata.json` and `docs/questions.md` is completed.
