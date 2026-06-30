# InfoScreen

InfoScreen is a local kiosk dashboard for a Surface or Ubuntu display.

It shows calendar schedule, market watchlist, weather, event/news stream, local official events, photo wall, and runtime status.

## Runtime files

Runtime files are not source files. The Surface runtime directory is:

```text
~/infoscreen/surface/.env/
```

The schedule runtime file is:

```text
~/infoscreen/surface/.env/schedule.json
```

The repository root should not contain runtime `schedule.json`. The checked-in fixture is `sample/schedule.json`.

HTTP logs:

```text
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

## Repository layout

```text
deploy/                         systemd templates and install scripts
docs/                           api-spec.md, design.md, questions.md
mac/                            macOS calendar export and schedule sync
sample/                         sample JSON fixtures
scripts/                        repo/dev/status scripts
surface/                        Surface app implementation
surface/.env/                   local runtime state, ignored by Git
surface/web/index.html          dashboard shell
surface/web/assets/css/         checked-in CSS
surface/web/assets/js/          checked-in browser JS
metadata.json                   project requirements and plan
```

## Start on Surface / Ubuntu

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
systemctl --user daemon-reload
systemctl --user enable --now infoscreen-http.service
systemctl --user restart infoscreen-http.service
```

Open:

```text
http://127.0.0.1:8765/
```

## Start without systemd

```bash
cd ~/infoscreen
python3 surface/serve_infoscreen.py
```

## Calendar schedule sync from Mac

The Mac exports Apple Calendar and copies the result to the Surface runtime schedule path.

Remote target:

```text
~/infoscreen/surface/.env/schedule.json
```

Setup example:

```bash
cd /path/to/infoScreen
bash mac/scripts/setup-schedule-sync.sh \
  --host "<surface-host>" \
  --user "<surface-user>" \
  --remote-path "~/infoscreen/surface/.env/schedule.json"
```

Manual sync:

```bash
bash mac/sync_schedule.sh
```

Verify on Surface:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json surface/.env/schedule.json
```

## Service status

```bash
systemctl --user status infoscreen-http.service --no-pager -l
systemctl --user list-timers --all | grep -i infoscreen || true
tail -n 80 ~/infoscreen/surface/.env/logs/http.log
tail -n 80 ~/infoscreen/surface/.env/logs/http.err.log
```

## Market and weather refresh

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
```

## Local official events

```bash
cd ~/infoscreen
python3 surface/search_local_events.py "Punggol Singapore"
```

Local event source rules:

```text
official_source_registry.json stores official homepage/domain identity only
event_sources.json stores verified event listing entrypoints
no third-party aggregators
no guessed domains or guessed /events paths
```

## API docs

```text
http://127.0.0.1:8765/docs
http://127.0.0.1:8765/openapi.json
```

## Git hygiene

Do not commit runtime data:

```text
schedule.json
mac/schedule.json
surface/.env/
surface/.env/logs/
*.log
__pycache__/
*.pyc
```
