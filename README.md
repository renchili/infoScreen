# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project is designed for glanceable use rather than constant interaction. It favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from a curated inventory of official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Runtime JSON, machine-local configuration, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files or sample data to commit.

## Who this is for

The primary operator maintains one always-on Surface or Ubuntu display and may use a Mac to supply Calendar data. A maintainer should be comfortable with Python commands, browser inspection, systemd user services on the Surface, and LaunchAgent/SSH diagnostics on the Mac when Calendar sync is enabled.

## First 10 minutes

The smallest useful path starts the local HTTP server and opens the committed dashboard without requiring external providers, systemd, a Mac, or personal runtime data.

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

Then open:

```text
http://127.0.0.1:8765/
```

This quick path proves that the committed frontend, local HTTP server, and OpenAPI generation are available. It does not prove that external Market, Weather, News, or Local Events sources are currently reachable, that systemd timers are installed, or that Mac Calendar sync is configured.

## Prerequisites

For the smallest local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For the full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package for Local Events;
- outbound network access for Market, Weather, News, and official Local Events sources;
- `ffmpeg` for HEIC/HEIF conversion and ImageMagick `magick` for optional photo normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

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

Machine-specific Calendar sync configuration is written to uncommitted `mac/local.env`. Do not commit runtime JSON, logs, debug captures, personal photos, SSH details, or machine-local environment files.

## Startup success signals

The smallest local startup is successful when all of these are true:

1. the server prints a startup line for `0.0.0.0:8765`;
2. `GET /` returns the dashboard HTML and references `assets/js/dashboard.js` and `assets/js/local_event_card.js`;
3. `GET /openapi.json` returns a JSON document whose title is `InfoScreen Local API`;
4. the browser opens the page even when runtime files are missing, with missing or unavailable states shown instead of invented data.

A full deployment has additional success signals: `bash scripts/infoscreen_status.sh` reports the HTTP service and relevant timers, runtime files have current modification times, and the visible panels agree with their served JSON.

## 1. What the project provides

The dashboard currently includes:

- current time, date, page refresh time, and page-session uptime;
- a Market card and global Market tape with configurable symbols;
- current Singapore weather;
- aligned English, French, and Chinese news rows;
- a Local Events card built from curated official organisation sources;
- a Calendar board supplied by macOS Calendar/EventKit;
- a local Photo wall;
- a Sync ticker showing whether Schedule, Weather, Market, and News runtime files are fresh, stale, missing, or unreachable;
- local OpenAPI documentation for the HTTP endpoints.

The CPU/MEM/DSK/NET bars are currently simulated browser values, not Surface system monitoring. POWER/DISPLAY/NETWORK labels are static text.

## 2. Product and runtime model

```text
Mac, required only for Calendar
  macOS Calendar/EventKit
  -> LaunchAgent
  -> schedule.json over SSH/SCP

Surface or Ubuntu device
  systemd --user services and timers
  -> producer jobs
  -> runtime JSON under surface/.env/
  -> surface/serve_infoscreen.py
  -> browser kiosk page
```

Repository root:

```text
~/infoscreen
```

Runtime and personal-data root:

```text
~/infoscreen/surface/.env
```

Runtime JSON, logs, local configuration, debug output, and user photos are device state and are not committed.

## 3. Data sources, producers, and page consumers

| Product area | Data source | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- | --- |
| Market card and tape | Nasdaq, CNBC, Stooq, Yahoo, previous cache | `infoscreen-live-data.timer` or Market refresh action | `market.json`, `/market.json` | `dashboard.js` |
| Weather | Open-Meteo using Singapore coordinates | `infoscreen-live-data.timer` or Market refresh action | `weather.json`, `/weather.json` | `dashboard.js` |
| Multilingual News | Google News RSS, CNA, France24, RFI, BBC Chinese, Google Translate | `infoscreen-event-stream.timer` | `event_stream.json`, `/event_stream.json` | `local_event_card.js` |
| Local Events | Curated official organisation listing and detail pages | `infoscreen-local-events.timer` or location search | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Calendar | macOS Calendar/EventKit on the Mac | Mac LaunchAgent | `schedule.json`, `/schedule.json` | `calendar_board.js` |
| Photos | User files under `surface/.env/photos/` | Manual photo builder | `photos.json`, `/photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Runtime-file HTTP `Last-Modified` | Browser `HEAD` checks | Schedule, Weather, Market, and News endpoints | `local_event_card.js` |
| Market configuration | User-selected symbols | Market config UI | `/api/market-config`, `market_config.json` | `market_custom.js` |
| Clock and page uptime | Browser clock | Browser timers | No runtime file | `dashboard.js` |

Each visible DOM mount has one renderer owner. Producers write runtime data; browser scripts render that data; the HTTP server serves files and local APIs.

## 4. User interaction and configuration

### Market symbols

The Market gear opens a local configuration panel.

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and then refreshes Market data.
- `REFRESH` sends `POST /api/market-refresh`.
- A Market refresh runs `surface/fetch_live_data.py`, so it refreshes both Market and Weather.
- At most 12 unique symbols are stored.

Default symbols:

```text
surface/conf/market_config.default.json
```

Active runtime configuration:

```text
surface/.env/market_config.json
```

### Local-event location

The Local Event search control opens a location input.

- The last location is stored in browser `localStorage` as `local_events_location`.
- Search sends `POST /api/local-events/search`.
- The server runs the source-specific Local Events collector and returns the resulting runtime payload.
- The configured official source inventory remains the same; the entered location is an input to the collection job.
- Previous and next controls change the current card immediately.

### Local Event review and user feedback

The development branch `develop/surface-local-events-coverage` adds an operator page to the existing InfoScreen HTTP service. It does not add a second server, service, or port.

Update and install on the Surface from a visible desktop session:

```bash
cd ~/infoscreen
git fetch origin
git switch develop/surface-local-events-coverage
git pull --ff-only origin develop/surface-local-events-coverage
bash deploy/scripts/install-user-systemd.sh
```

The installer starts or restarts the existing HTTP service on port `8765`. Running it from the Surface desktop session allows the service to receive the graphical-session environment required when it opens the separate Chromium feedback window.

Open:

```text
http://127.0.0.1:8765/local-events/studio/
```

The page exposes two independent abilities.

#### Review system-collected list pages and Events

1. Click `COLLECT LIST PAGES`.
2. Open each candidate URL and choose `CONFIRM LIST PAGE`, `REJECT`, or `RESET`.
3. After confirming the required pages, click `COLLECT EVENTS FROM CONFIRMED PAGES`.
4. Review each collected Event. The card shows the official detail URL and detail-page fields together with the originating listing URL, DOM selector, selector match number, listing page index, and document position.
5. Choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

Only pages marked `confirmed` are used by the Event-review collection action. This operator-review state is separate from the normal kiosk Local Events runtime file.

#### Browse a listing page and point out an Event location

This ability does not require the list-page or Event collection steps above to be run first.

1. Select the institution and listing page under `ABILITY 2 · INDEPENDENT`.
2. Click `OPEN REAL LISTING PAGE`.
3. Use the opened Chromium window normally. Scrolling, filters, tabs, expanding sections, pagination, links, and other page controls remain available while the toolbar is in `BROWSE` mode.
4. When the required Event is visible, click `POINT TO EVENT`, then click the corresponding Event link, card, row, or tile.
5. Use `SMALLER` or `LARGER` to select the appropriate DOM level when the first highlighted element is too narrow or too broad.
6. Click `SUBMIT THIS POSITION`.
7. The toolbar returns to `BROWSE` mode. The submitted selector, match number, page position, visible text, page URL, and link appear in `Submitted positions` on the operator page.

`POINT TO EVENT` pauses the next page click only while selecting an element. It is not required for normal browsing and does not turn the whole browsing session into a marking mode.

Review data, submitted feedback, browser session metadata, and the feedback browser profile are local runtime state under:

```text
surface/.env/local_event_review/
├── state.json
├── browser_sessions/
└── browser_profiles/
```

These files must not be committed. The operator page reloads review state automatically and also provides a `RELOAD` button.

For a manual foreground server start, with Chromium, Playwright, and Pydantic already installed:

```bash
cd ~/infoscreen
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

Then open the same `/local-events/studio/` URL. The foreground process must inherit a graphical desktop environment for `OPEN REAL LISTING PAGE` to create a visible Chromium window.

### Calendar

Calendar accounts and permissions remain on the Mac. The Surface has no Calendar account configuration. Only the Mac-to-Surface target and sync interval are configured.

### Photos

Place files under:

```text
surface/.env/photos/
```

Then rebuild the manifest:

```bash
cd ~/infoscreen
python3 surface/build_photos_json.py
```

The browser does not scan the filesystem directly.

## 5. Refresh behaviour

The project has three separate refresh layers.

### Producer refresh

A producer fetches or generates data and writes runtime JSON.

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds by default |
| Photos | Manual builder | No supported timer |

Surface timer configuration lives under:

```text
deploy/systemd/user/
```

After changing a committed timer, rerun:

```bash
bash deploy/scripts/install-user-systemd.sh
```

The Mac Calendar interval is configured with `mac/scripts/setup-schedule-sync.sh --interval`.

### Browser data reload

| UI area | Browser reload behaviour |
| --- | --- |
| Market | Page load, every 60 seconds, and after a Market refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | Page load and every 60 seconds using `HEAD` |
| Local Events | Page load and after an on-demand location search |
| Calendar | Page load only |
| Photos | Page load and every 5 minutes |

### Visual rotation

| UI area | Rotation |
| --- | --- |
| Local Event card | Every 15 seconds |
| Calendar board | Every 7 seconds |
| Photo wall | Every 9 seconds |
| News and Market tapes | Continuous animation |

A producer can update a runtime file while the page still shows an older in-memory Local Event or Calendar list. Reload the page to consume those updated files.

## 6. Local Events is source-specific by design

Local Events is not a generic search-engine scraper. The project uses a maintained inventory of official source entrypoints and adapter choices:

```text
surface/conf/event_sources.json
```

The current inventory covers official museum, library, community, attraction, shopping-centre, venue, and institution sites. Each source defines:

- source ID and display name;
- official home page;
- allowed domains;
- official activity-list URLs;
- default venue;
- adapter type;
- configured display order.

The adapter names are historical extraction hints. Both `rendered_dom_card` and `nhb` must produce a rendered card from a configured official activity list before an item can enter the result set.

In this architecture, positive event intent means membership in that correct official activity list; an explicit type, date range, or route is not an alternative admission path.

The collector was developed against real official-site differences. Current behaviour includes:

- fully rendering and expanding configured official activity lists;
- admitting only isolated list cards with one canonical official detail URL, a usable date, and a usable title;
- using XHR/fetch JSON, embedded structured state, and detail pages only to enrich an already admitted list card;
- discarding unmatched structured records even when they are explicitly typed as `Event` or appear under an event-looking route;
- avoiding per-record title and URL blacklists as the primary decision mechanism;
- retaining a legitimate listed activity even when its title contains a word seen in a previous bad record;
- Gardens by the Bay date-range and venue repair after list admission;
- configured source ordering and per-source listing admission/rejection evidence;
- preserving only previous rows carrying `candidate_policy: official-listing-authority-v1` when a partial run would replace a larger verified result.

The main output is:

```text
surface/.env/local_event_search_results.json
```

Incomplete diagnostic output may be written to:

```text
surface/.env/local_event_search_results.partial.json
```

When previous verified rows are retained, the partial payload records `write_policy: kept_previous_verified_result`. Legacy rows without current listing evidence are not kept simply because they appeared in an older complete file.

Per-source debug evidence is available through `debug_by_source` and under:

```text
surface/.env/local_event_debug_cards/
```

The detailed source inventory, collection pipeline, crawl budgets, and targeted source behaviour are documented in `docs/design.md`.

## 7. Project structure

```text
surface/serve_infoscreen.py            local HTTP server and APIs
surface/fetch_live_data.py              Market and Weather producer
surface/fetch_event_stream.py           multilingual News producer
surface/search_local_events.py          Local Events command wrapper
surface/jobs/local_event_search.py      Local Events job entrypoint
surface/local_events_runtime/           canonical source-specific collection and extraction library
surface/build_photos_json.py            Photo manifest builder
surface/conf/                            committed defaults and source inventory
surface/web/                             kiosk frontend
surface/.env/                            local runtime and personal data
mac/                                     EventKit export and schedule push
deploy/systemd/user/                     committed Surface user units
scripts/                                 status, validation, and repository scripts
docs/                                    architecture, API, and requirement clarifications
tests/                                   unit and contract tests
```

Start with `surface/serve_infoscreen.py` for the HTTP process, `surface/jobs/` for one-shot orchestration, `surface/local_events_runtime/` for Local Events collection logic, `surface/web/` for the kiosk UI, `surface/conf/` for committed configuration, `deploy/systemd/user/` for Surface scheduling, `mac/` for Calendar export and push, and `tests/` for offline regression contracts.

## 8. Deployment and update

### Surface dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium
python3 -m pip install --user playwright
```

`surface/local_events_runtime/browser.py` uses an installed Chromium-compatible browser. Set `INFOSCREEN_CHROMIUM_PATH` only when auto-detection does not find the correct executable.

### Install Surface services and timers

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

This is the supported Surface installation entrypoint. It creates `surface/.env/`, installs the committed user units, starts the HTTP service, enables timers, and triggers initial producer runs.

Open locally:

```text
http://127.0.0.1:8765/
```

The server binds `0.0.0.0:8765`; network exposure should be controlled by the host or local network.

### Update an existing deployment

```bash
cd ~/infoscreen
git pull --ff-only
bash deploy/scripts/install-user-systemd.sh
```

Rerun the installer after unit-file changes because active user units are copied to `~/.config/systemd/user/`.

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

The setup script writes machine-local configuration to `mac/local.env` and installs:

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

The status script reports services, timers, logs, runtime-file ages, HTTP checks, and runtime previews.

### Common service controls

```bash
systemctl --user restart infoscreen-http.service
systemctl --user start infoscreen-live-data.service
systemctl --user start infoscreen-event-stream.service
systemctl --user start infoscreen-local-events.service
```

### Page does not open

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
curl -v http://127.0.0.1:8765/
```

### Market or Weather is stale or missing

Both are written by the same producer:

```bash
systemctl --user status infoscreen-live-data.timer infoscreen-live-data.service --no-pager -l
journalctl --user -u infoscreen-live-data.service -n 200 --no-pager
systemctl --user start infoscreen-live-data.service
python3 -m json.tool surface/.env/market.json | head -n 80
python3 -m json.tool surface/.env/weather.json | head -n 80
```

`provider: stale-cache` means all live providers failed for that symbol and the previous usable item was retained. `session: ERR` with `price: N/A` means no live provider and no usable previous value succeeded.

### News is stale or empty

```bash
systemctl --user status infoscreen-event-stream.timer infoscreen-event-stream.service --no-pager -l
journalctl --user -u infoscreen-event-stream.service -n 200 --no-pager
systemctl --user start infoscreen-event-stream.service
python3 -m json.tool surface/.env/event_stream.json | less
```

Inspect the runtime `errors` array for feed or translation failures.

### Local Events is empty, partial, stale, or contains a bad record

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

Inspect `debug_by_source` for the affected organisation before changing extraction logic. Determine whether the failure is page access, list expansion, isolated-card discovery, official-detail URL extraction, structured-to-list matching, optional detail enrichment, date parsing, or the total crawl budget.

For a bad row, first ask which configured official list card admitted it. Structured JSON, an explicit `Event` type, or an event-looking route without a matching list card is not sufficient. Data-quality fixes belong in the collector/extractor, not in frontend title hiding or a growing list of blocked titles and paths.

When Playwright or Chromium is missing, logs contain `missing_playwright_python_package` or `missing_system_chromium`.

### Schedule is stale or missing

The producer runs on the Mac. Check the Mac LaunchAgent, `mac/local.env`, SSH reachability, and:

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

The Calendar board reads the file at page load, so reload the page after confirming the file changed.

### Photos are empty

```bash
find surface/.env/photos -maxdepth 1 -type f -print
python3 surface/build_photos_json.py
python3 -m json.tool surface/.env/photos.json | less
```

### Sync `AGE` is unexpectedly large

The Sync ticker compares the browser clock with HTTP `Last-Modified`. Check the producer, runtime file modification time, HTTP header, and device clocks. For Schedule also check the Mac clock. `ERR` means the browser `HEAD` request failed and does not by itself prove the producer failed.

## 10. Development and validation

Install test dependencies:

```bash
python3 -m pip install --user pytest pydantic
```

Run the repository suite:

```bash
cd ~/infoscreen
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

The full runner uses fixture runtime data and writes logs, JUnit XML, generated OpenAPI, and a summary under:

```text
${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}
```

It does not write fixture data into the real `surface/.env/`.

Manual producer commands:

```bash
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/search_local_events.py "Punggol Singapore"
python3 surface/build_photos_json.py
```

Before changing code or documentation, read `AGENTS.md`, `AGENT.md`, and `skills/SKILL.md`, then open the relevant source, tests, deployment files, and one of `docs/design.md`, `docs/api-spec.md`, or `docs/questions.md` according to the task.

## 11. Documentation

```text
README.md          newcomer onboarding, capabilities, data sources, interaction, refresh, deployment, and troubleshooting
docs/design.md     architecture, source ownership, data flow, and source-specific implementation
docs/api-spec.md   HTTP methods, callers, payloads, side effects, and runtime mapping
docs/questions.md  requirement clarifications with implementation and acceptance evidence
AGENT.md            repository-specific contribution rules
AGENTS.md           required agent read order
```
