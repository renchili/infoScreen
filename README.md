# InfoScreen

InfoScreen is a local kiosk dashboard for a Surface or Ubuntu display. The Surface runs the web server and data jobs; a Mac supplies Calendar data through EventKit.

## Install on the Surface

The supported systemd installation entrypoint is:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

The installer copies the committed user units, enables the HTTP service and timers, creates `surface/.env/`, and starts the first data refresh.

Local-event collection also requires the Playwright Python package and a Chromium-compatible browser:

```bash
python3 -m pip install --user playwright
sudo apt install -y chromium
```

Open the dashboard at:

```text
http://127.0.0.1:8765/
```

After pulling repository updates, rerun the installer so changed unit files are copied and reloaded:

```bash
cd ~/infoscreen
git pull --ff-only
bash deploy/scripts/install-user-systemd.sh
```

## Operate the Surface

Show services, timers, recent logs, runtime-file ages, and HTTP checks:

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

Common commands:

```bash
# Web server
systemctl --user restart infoscreen-http.service
journalctl --user -u infoscreen-http.service -n 100 --no-pager

# Market and weather
systemctl --user start infoscreen-live-data.service
journalctl --user -u infoscreen-live-data.service -n 100 --no-pager

# News
systemctl --user start infoscreen-event-stream.service
journalctl --user -u infoscreen-event-stream.service -n 100 --no-pager

# Local events
systemctl --user start infoscreen-local-events.service
journalctl --user -u infoscreen-local-events.service -n 100 --no-pager
```

## Page data map

Each visible area has one frontend owner. Background jobs write runtime JSON under `surface/.env/`; the HTTP server exposes that data to the page.

| Page area | Frontend owner | Producer or trigger | Runtime/API | Data source |
| --- | --- | --- | --- | --- |
| Market card | `dashboard.js` | `infoscreen-live-data.timer`, every 5 minutes | `market.json`, `/market.json` | Nasdaq, CNBC, Stooq, then Yahoo/cache fallback |
| Global market tape | `dashboard.js` | Same Market job | Same `market.json` | Same market providers |
| Market configuration | `market_custom.js` | User save or refresh | `/api/market-config`, `/api/market-refresh`, `market_config.json` | User-selected symbols |
| Weather card | `dashboard.js` | `infoscreen-live-data.timer`, every 5 minutes | `weather.json`, `/weather.json` | Open-Meteo |
| EN/FR/中文 news ticker | `local_event_card.js` | `infoscreen-event-stream.timer`, every 5 minutes | `event_stream.json`, `/event_stream.json` | Google News RSS, CNA, France24, RFI, BBC Chinese, and translation output |
| Local event card | `local_event_card.js` | `infoscreen-local-events.timer`, every 6 hours, or an on-demand search | `local_event_search_results.json`, `/api/local-events/search` | Official pages in `surface/conf/event_sources.json` |
| Calendar board | `calendar_board.js` | Mac LaunchAgent, default every 120 seconds | `schedule.json`, `/schedule.json` | macOS Calendar/EventKit on the Mac |
| Photo wall | `local_event_card.js` | Manual `surface/build_photos_json.py` | `photos.json`, `/photos.json`, `/public_photos/*` | User files in `surface/.env/photos/` |
| Sync ticker | `local_event_card.js` | Browser `HEAD` checks every 60 seconds | `/schedule.json`, `/weather.json`, `/market.json`, `/event_stream.json` | Runtime-file `Last-Modified` headers |
| Header clock, date, refresh, and uptime | `dashboard.js` | Browser clock | No backend runtime file | Browser time; uptime is page-session uptime |
| CPU/MEM/DSK/NET bars | `dashboard.js` | Browser timer | No backend runtime file | `Math.random()` demo values, not system monitoring |
| POWER/DISPLAY/NETWORK labels | Static HTML | None | No API or runtime file | Static text, not health checks |
| OpenAPI pages | HTTP server | HTTP request | `/openapi.json`, `/docs` | Committed API definitions |

Detailed DOM ownership and data flow are in `docs/design.md`.

## Local events

Configuration:

```text
surface/conf/event_sources.json
```

Scheduled job:

```text
infoscreen-local-events.timer
  -> infoscreen-local-events.service
  -> surface/search_local_events.py
  -> surface/jobs/local_event_search.py
  -> surface/.env/local_event_search_results.json
```

Run a refresh manually:

```bash
cd ~/infoscreen
python3 surface/search_local_events.py "Punggol Singapore"
```

Inspect the result and per-source debug information:

```bash
python3 -m json.tool surface/.env/local_event_search_results.json | less
journalctl --user -u infoscreen-local-events.service -n 100 --no-pager
```

`debug_by_source` records which official sources were opened, how many cards were found and accepted, and why candidates were rejected. Debug card data is written under `surface/.env/local_event_debug_cards/`.

A date alone does not make a record an event. Structured records must have positive event intent, such as an explicit `Event` type or a relationship to the official event-listing route. Data-quality rejection belongs in the collector/extractor, not in frontend hiding rules.

## Schedule sync — run on the Mac

`schedule.json` is not generated on the Surface. macOS Calendar/EventKit is the data source, so the Mac exports Calendar events and pushes the file to the Surface runtime directory.

Configure the Surface SSH target and install or refresh the LaunchAgent on the Mac:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user rody \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

This writes the local-only `mac/local.env` and installs:

```text
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

Trigger an immediate sync:

```bash
launchctl kickstart -k gui/$(id -u)/com.renchili.infoscreen.schedule-sync
```

The remote target is `~/infoscreen/surface/.env/schedule.json`. The Surface only serves and renders this file; the schedule producer runs on the Mac.

## Photos

Put user photos in:

```text
surface/.env/photos/
```

Rebuild the photo manifest after adding or removing files:

```bash
cd ~/infoscreen
python3 surface/build_photos_json.py
```

Generated photo runtime data remains under `surface/.env/` and is not committed.

## Runtime files

Runtime state is local to the device:

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/market_config.json
surface/.env/event_stream.json
surface/.env/local_event_search_results.json
surface/.env/local_event_search_results.partial.json
surface/.env/local_event_debug_cards/
surface/.env/photos/
surface/.env/photos.json
surface/.env/public_photos/
surface/.env/logs/
```

## Sync status

The left ticker checks HTTP `Last-Modified` values and reports:

- `OK`: file age is within its threshold.
- `STALE`: the file exists but is too old.
- `MISS`: the runtime path or `Last-Modified` header is missing.
- `ERR`: the browser request failed.

Failure owner:

| Status | Check first |
| --- | --- |
| `SCHEDULE` | Mac LaunchAgent, `mac/local.env`, and `~/Library/Logs/infoscreen-sync/` |
| `WEATHER` or `MARKET` | `infoscreen-live-data.timer` and `infoscreen-live-data.service` on the Surface |
| `NEWS` | `infoscreen-event-stream.timer` and `infoscreen-event-stream.service` on the Surface |
| Local events | `infoscreen-local-events.timer` and `infoscreen-local-events.service`; local events are not part of the four-item sync ticker |

When a file was just updated but `AGE` is still large, compare the browser and Surface clocks; for `SCHEDULE`, also compare the Mac clock.

## Manual refresh commands

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/search_local_events.py "Punggol Singapore"
python3 surface/build_photos_json.py
```

## Tests

Install test dependencies and run the closed-loop suite:

```bash
cd ~/infoscreen
python3 -m pip install --user pytest pydantic
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

The full runner uses fixture runtime data and writes logs, JUnit XML, generated OpenAPI, and a summary under `${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}`. It does not write test data into the real `surface/.env/`.

## Documentation

```text
docs/design.md     runtime architecture, UI ownership, jobs, and data flow
docs/api-spec.md   HTTP endpoints and Python owners
docs/questions.md  durable product and architecture decisions
AGENT.md            repository-specific rules
AGENTS.md           required agent read order
```
