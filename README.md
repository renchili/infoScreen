# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project is designed for glanceable use rather than constant interaction. It favours readable typography, compact information density, predictable layout, local ownership of personal data, visible failure states, and source-specific evidence for Local Events.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from a curated inventory of official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Local Event Studio is a local operator tool inside the existing InfoScreen HTTP service. It is not a second application, crawler service, cloud rule store, or arbitrary URL editor.

Runtime JSON, machine-local configuration, Studio rules and captures, logs, debug evidence, and personal photos are device state under `surface/.env/`; they are not repository source files or sample data to commit.

## Who this is for

The primary operator maintains one always-on Surface or Ubuntu display and may use a Mac to supply Calendar data. A maintainer should be comfortable with Python commands, browser inspection, systemd user services on the Surface, and LaunchAgent/SSH diagnostics on the Mac when Calendar sync is enabled.

## First 10 minutes

The smallest useful path starts the local HTTP server and opens the committed dashboard without requiring external providers, systemd, a Mac, personal runtime data, or a Studio rule.

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -fsS http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 20
```

Open the kiosk:

```text
http://127.0.0.1:8765/
```

Open Local Event Studio:

```text
http://127.0.0.1:8765/local-events/studio/
```

This proves only that the committed frontend, local HTTP server, generated OpenAPI document, and Studio page are available. It does not prove current external-source reachability, Playwright/Chromium operation, a published Studio rule, systemd installation, or semantic correctness of live activities.

## Prerequisites

For the smallest local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For repository tests:

```bash
python3 -m pip install --user "pytest>=8,<9" "pydantic>=2,<3"
```

For full Surface deployment and Local Events:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package;
- outbound network access for Market, Weather, News, and official Local Events sources;
- `ffmpeg` for HEIC/HEIF conversion and ImageMagick `magick` for optional photo normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

Install common Surface dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium
python3 -m pip install --user playwright
```

`surface/local_events_runtime/browser.py` uses an installed Chromium-compatible browser. Set `INFOSCREEN_CHROMIUM_PATH` only when auto-detection does not find the correct executable.

## Configuration and safe local state

No private configuration is required to serve the static dashboard. Runtime files and local preferences are created under:

```text
~/infoscreen/surface/.env/
```

Committed configuration includes:

```text
surface/conf/market_config.default.json
surface/conf/event_sources.json
```

Machine-specific Calendar sync configuration is written to uncommitted `mac/local.env`.

Local Event Studio writes only under:

```text
surface/.env/local_event_studio/
```

That directory contains snapshots, drafts, published rules, immutable rule history, and deterministic test runs. Do not commit it.

## Startup success signals

The smallest local startup is successful when:

1. the server prints a startup line for `0.0.0.0:8765`;
2. `GET /` returns dashboard HTML referencing `dashboard.js` and `local_event_card.js`;
3. `GET /openapi.json` returns a document titled `InfoScreen Local API`;
4. `GET /local-events/studio/` returns the Studio page;
5. the browser opens even when runtime files are missing, with missing/unavailable states instead of invented data.

A full deployment has additional success signals: `scripts/infoscreen_status.sh` reports the HTTP service and relevant timers, runtime files have current modification times, the visible panels agree with served JSON, and live Local Events evidence is inspected separately.

## 1. What the project provides

The dashboard includes:

- current time, date, page refresh time, and page-session uptime;
- a Market card and global Market tape with configurable symbols;
- current Singapore weather;
- aligned English, French, and Chinese news rows;
- a Local Events card built from curated official organisation sources;
- Local Event Studio for per-source/listing capture, annotation, deterministic testing, publication, and rollback;
- a Calendar board supplied by macOS Calendar/EventKit;
- a local Photo wall;
- a Sync ticker showing Schedule, Weather, Market, and News freshness;
- generated local OpenAPI documentation.

The CPU/MEM/DSK/NET bars remain simulated browser values. POWER/DISPLAY/NETWORK labels remain static text.

## 2. Product and runtime model

```text
Mac, required only for Calendar
  macOS Calendar/EventKit
  -> LaunchAgent
  -> schedule.json over SSH/SCP

Surface or Ubuntu device
  systemd --user services and timers
  -> producer jobs
  -> runtime state under surface/.env/
  -> surface/serve_infoscreen.py on port 8765
  -> kiosk page and Local Event Studio
```

Repository root:

```text
~/infoscreen
```

Runtime and personal-data root:

```text
~/infoscreen/surface/.env
```

## 3. Data sources, producers, and consumers

| Product area | Data source | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- | --- |
| Market | Nasdaq, CNBC, Stooq, Yahoo, previous cache | `infoscreen-live-data.timer` or Market refresh | `market.json`, `/market.json` | `dashboard.js` |
| Weather | Open-Meteo, Singapore coordinates | `infoscreen-live-data.timer` or Market refresh | `weather.json`, `/weather.json` | `dashboard.js` |
| News | Google News RSS, CNA, France24, RFI, BBC Chinese, translation | `infoscreen-event-stream.timer` | `event_stream.json` | `local_event_card.js` |
| Local Events | Curated official listing/detail pages | `infoscreen-local-events.timer` or location search | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Local Event Studio | Configured official listing pages and local rule state | Explicit operator actions | `/api/local-events/studio/*` | `local_event_studio.js`, `local_event_studio_test.js` |
| Calendar | macOS Calendar/EventKit | Mac LaunchAgent | `schedule.json` | `calendar_board.js` |
| Photos | User files under `surface/.env/photos/` | Manual photo builder | `photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Runtime-file `Last-Modified` | Browser `HEAD` checks | Four runtime endpoints | `local_event_card.js` |
| Market configuration | User-selected symbols | Market config UI | `/api/market-config` | `market_custom.js` |

Each visible mount has one renderer owner. Producers write runtime data; browser scripts render it; the HTTP process serves files and bounded local APIs.

## 4. User interaction and configuration

### Market symbols

The Market gear opens a local configuration panel.

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and refreshes Market/Weather.
- `REFRESH` sends `POST /api/market-refresh`.
- At most 12 unique symbols are stored.

### Local-event location

The Local Event search control opens a location input.

- The last location is stored in browser `localStorage` as `local_events_location`.
- Search sends `POST /api/local-events/search`.
- The server runs `surface/search_local_events.py` and returns the resulting runtime payload.
- Previous/next controls change the current accepted card immediately.

### Local Event Studio

Studio is available at:

```text
http://127.0.0.1:8765/local-events/studio/
```

The workflow is:

```text
choose configured source and listing
-> CAPTURE NOW
-> select two real repeated activity cards
-> map TITLE / WHEN / WHERE / DETAIL URL
-> optionally map SUMMARY / IMAGE and detail-page overrides
-> add EXCLUDE selectors for non-activity cards
-> SAVE DRAFT
-> TEST DRAFT against the selected stored snapshot
-> inspect accepted/rejected rows and field evidence
-> PUBLISH TESTED DRAFT only when publishable
```

Important boundaries:

- source and listing choices come only from committed `event_sources.json`;
- screenshot rectangles are annotation aids, not stored extraction coordinates;
- drafts and test runs do not affect production;
- publication requires the exact current draft fingerprint to have a publishable test;
- publication activates only that source/listing in subsequent Local Events jobs;
- rollback republishes a historical version as a new version.

### Calendar

Calendar accounts and permissions remain on the Mac. The Surface has no Calendar account configuration.

### Photos

Place files under:

```text
surface/.env/photos/
```

Then rebuild:

```bash
cd ~/infoscreen
python3 surface/build_photos_json.py
```

The browser does not scan the filesystem directly.

## 5. Refresh behavior

### Producer refresh

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds |
| Photos | Manual builder | No timer |

Publishing a Studio rule does not automatically run Local Events; start the existing Local Events service when an immediate production result is required.

### Browser reload

| Area | Behavior |
| --- | --- |
| Market | Page load, every 60 seconds, after refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | Page load and every 60 seconds using `HEAD` |
| Local Events | Page load and after on-demand search |
| Calendar | Page load only |
| Photos | Page load and every 5 minutes |
| Studio | Explicit source/listing/snapshot, reload, capture, test, publish actions |

### Visual rotation

| Area | Rotation |
| --- | --- |
| Local Event card | 15 seconds |
| Calendar board | 7 seconds |
| Photo wall | 9 seconds |
| News and Market tapes | Continuous |

Producer refresh, browser reload, and visual rotation are independent.

## 6. Local Events is source-specific by design

Local Events is not a generic search-engine scraper. The maintained official inventory is:

```text
surface/conf/event_sources.json
```

Each source defines its ID, name, official home, allowed domains, configured activity-list URLs, default venue, adapter hint, and order.

The existing collector:

- renders and expands configured official activity lists;
- admits only isolated rendered list cards with one official detail URL, usable date, and usable title;
- uses XHR/embedded structured state and detail pages only to enrich an admitted list card;
- discards unmatched structured records even when typed as `Event`;
- preserves configured source order and per-source evidence;
- applies targeted source field repair only after list admission.

Published Studio rules are applied after the existing collector and before final normalization:

```text
no published rule
  -> existing result remains

all configured listings for a source published
  -> that source becomes Studio-only

some listings published
  -> replace only rows carrying matching listing evidence

Studio failure or zero accepted rows
  -> that source is incomplete
  -> unrelated sources remain
  -> payload is partial
```

The primary output is:

```text
surface/.env/local_event_search_results.json
```

Incomplete evidence may be written to:

```text
surface/.env/local_event_search_results.partial.json
```

Per-source debug evidence is available in `debug_by_source`; Studio activation metadata is available in `studio_activations`.

Previous-cache protection mirrors the output contract. Current official-policy rows are eligible. A missing policy is eligible only for a previous payload in the current `structured-first` extractor family. A different non-empty policy is not retained.

Architecture details are in `docs/design.md`; HTTP details are in `docs/api-spec.md`; acceptance boundaries are in `docs/questions.md`.

## 7. Project structure

```text
surface/serve_infoscreen.py                         local HTTP server and APIs
surface/fetch_live_data.py                           Market and Weather producer
surface/fetch_event_stream.py                        multilingual News producer
surface/search_local_events.py                       Local Events command wrapper
surface/jobs/local_event_search.py                   Local Events orchestration
surface/jobs/local_event_studio_capture.py           one-shot Studio capture
surface/local_events_runtime/                        canonical Local Events library
surface/local_events_runtime/studio_rules.py         rule storage/versioning
surface/local_events_runtime/studio_capture.py       snapshot capture/storage
surface/local_events_runtime/studio_dom.py           bounded selector evaluation
surface/local_events_runtime/studio_evaluate.py      offline draft tests
surface/local_events_runtime/studio_collect.py       published live collection
surface/local_events_runtime/studio_pipeline.py      production replacement/health
surface/web/local-events/studio/index.html            Studio page
surface/web/assets/js/local_event_studio*.js          Studio interaction/test preview
surface/web/assets/css/local_event_studio*.css        Studio layout/preview styles
surface/build_photos_json.py                          Photo manifest builder
surface/conf/                                         committed defaults and source inventory
surface/.env/                                         local runtime and personal data
mac/                                                  EventKit export and schedule push
deploy/systemd/user/                                  committed Surface user units
scripts/                                              status and validation scripts
docs/                                                 architecture, API, requirements
tests/                                                unit and closed-loop tests
```

## 8. Deployment and update

### Install existing Surface services and timers

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

This is the supported installation entrypoint. It creates `surface/.env/`, installs committed user units, starts HTTP, enables timers, and triggers initial producers.

The only units used for Local Event Studio and production Local Events are the existing:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

There is no Studio service or timer.

### Update an existing deployment

```bash
cd ~/infoscreen
git pull --ff-only
bash deploy/scripts/install-user-systemd.sh
systemctl --user restart infoscreen-http.service
```

Rerun the installer after unit-file changes because active user units are copied to `~/.config/systemd/user/`.

### Trigger Local Events immediately

```bash
systemctl --user start infoscreen-local-events.service
```

Publishing a Studio rule affects this and future Local Events runs. The normal timer remains unchanged.

### Configure Mac Calendar sync

Run on the Mac:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user <surface-ssh-user> \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

The setup script writes `mac/local.env` and installs:

```text
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

Trigger immediately:

```bash
launchctl kickstart -k gui/$(id -u)/com.renchili.infoscreen.schedule-sync
```

The Surface does not generate Calendar data.

## 9. Operation and troubleshooting

### Check the whole deployment

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

### Common service controls

```bash
systemctl --user restart infoscreen-http.service
systemctl --user start infoscreen-live-data.service
systemctl --user start infoscreen-event-stream.service
systemctl --user start infoscreen-local-events.service
```

### Page or Studio does not open

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
curl -v http://127.0.0.1:8765/
curl -v http://127.0.0.1:8765/local-events/studio/
```

### Studio capture fails

Inspect the HTTP journal and confirm Chromium/Playwright availability:

```bash
journalctl --user -u infoscreen-http.service -n 300 --no-pager
command -v chromium chromium-browser google-chrome
python3 -c 'import playwright; print(playwright.__file__)'
```

Known explicit errors include `missing_playwright_python_package` and `missing_system_chromium`. Studio validates the source/listing before browser launch, so `unknown_source` and `unknown_listing` indicate a binding mismatch rather than a browser failure.

### Draft cannot be published

Publication requires a current publishable snapshot test with the exact draft fingerprint. In Studio:

1. select the intended snapshot;
2. save or edit the draft;
3. run `TEST DRAFT`;
4. inspect fatal errors and rejected cards;
5. publish only after `PUBLISHABLE: YES`.

HTTP `422` with `studio_test_required` means the applicable test is missing, stale, or not publishable.

### Inspect Studio state

```bash
find surface/.env/local_event_studio -maxdepth 5 -type f -print | sort
```

Rule state can also be read through:

```text
GET /api/local-events/studio/sources
GET /api/local-events/studio/rules?source_id=<id>&listing_url=<url>
GET /api/local-events/studio/test-latest?source_id=<id>&listing_url=<url>
```

Do not manually edit published/history files while the service is active. Use draft import/export, publish, or rollback APIs/UI.

### Roll back a Studio rule

Use the Studio history selector and `ROLL BACK AS NEW VERSION`. Rollback republishes the selected historical rule as the next version; it does not delete or rewrite history. Trigger the existing Local Events service afterward to produce a new runtime result.

### Local Events is empty, partial, stale, or contains a bad record

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

Inspect:

```text
debug_by_source
studio_activations
source_status_counts
completed_source_count
incomplete_source_count
partial
write_policy
previous_cache_policy
```

For a bad row, first identify the configured official list card or published Studio rule that admitted it. Structured JSON, an explicit `Event` type, or an event-looking route without list-card evidence is insufficient.

For a Studio source, inspect the exact rule version, `studio_listing_url`, `studio_evidence`, accepted/rejected test rows, and detail-page evidence. Do not fix backend data quality by hiding titles in the frontend.

### Market or Weather is stale

```bash
systemctl --user status infoscreen-live-data.timer infoscreen-live-data.service --no-pager -l
journalctl --user -u infoscreen-live-data.service -n 200 --no-pager
systemctl --user start infoscreen-live-data.service
python3 -m json.tool surface/.env/market.json | head -n 80
python3 -m json.tool surface/.env/weather.json | head -n 80
```

### News is stale or empty

```bash
systemctl --user status infoscreen-event-stream.timer infoscreen-event-stream.service --no-pager -l
journalctl --user -u infoscreen-event-stream.service -n 200 --no-pager
systemctl --user start infoscreen-event-stream.service
python3 -m json.tool surface/.env/event_stream.json | less
```

### Schedule is stale or missing

The producer runs on the Mac. Check:

```bash
launchctl print gui/$(id -u)/com.renchili.infoscreen.schedule-sync
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.out.log
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.err.log
```

On the Surface:

```bash
ls -l surface/.env/schedule.json
curl -fsSI http://127.0.0.1:8765/schedule.json
```

Reload the page after confirming the file changed.

### Photos are empty

```bash
find surface/.env/photos -maxdepth 1 -type f -print
python3 surface/build_photos_json.py
python3 -m json.tool surface/.env/photos.json | less
```

### Sync `AGE` is unexpectedly large

The Sync ticker compares the browser clock with HTTP `Last-Modified`. Check producer state, runtime mtime, HTTP headers, and both device clocks. `ERR` means the browser `HEAD` request failed; it does not alone prove producer failure.

## 10. Development and validation

Run repository validation:

```bash
cd ~/infoscreen
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

The full runner uses fixture runtime data and writes logs, JUnit XML, generated OpenAPI, and a summary under:

```text
${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}
```

It sets `INFOSCREEN_ENV_DIR` to an isolated acceptance runtime and does not write fixture data into the real `surface/.env/`.

Manual producer commands:

```bash
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/search_local_events.py "Punggol Singapore"
python3 surface/build_photos_json.py
```

Evidence levels remain separate:

```text
source review
-> repository tests/CI
-> real source capture
-> human semantic annotation
-> publishable test
-> published version
-> live producer run
-> runtime JSON
-> visible Surface acceptance
```

A successful repository suite does not prove current external reachability or semantic correctness of current official pages.

Before changing code or documentation, read `AGENTS.md`, `AGENT.md`, and `skills/SKILL.md`, then open the relevant source, tests, deployment files, and one of `docs/design.md`, `docs/api-spec.md`, or `docs/questions.md`.

## 11. Documentation

```text
README.md          onboarding, capabilities, interaction, deployment, operation, troubleshooting
docs/design.md     architecture, ownership, data flow, Local Events and Studio runtime behavior
docs/api-spec.md   HTTP methods, payloads, responses, side effects, callers
docs/questions.md  requirement clarifications and acceptance evidence
AGENT.md           repository-specific contribution rules
AGENTS.md          required agent read order
```
