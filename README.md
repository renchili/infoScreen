# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from a curated inventory of official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Runtime JSON, machine-local configuration, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files or sample data to commit.

## Who this is for

The primary operator maintains one always-on Surface or Ubuntu display and may use a Mac to supply Calendar data. The Local Event review page may be operated from another computer on the same trusted local network; the Surface screen and mouse are not required for browser feedback.

## First 10 minutes

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

This quick path proves that the committed frontend, local HTTP server, and OpenAPI generation are available. It does not prove external provider reachability, systemd installation, live Local Event extraction, or Mac Calendar sync.

## Prerequisites

For the smallest local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For the full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package for system-collected Local Events;
- outbound network access for Market, Weather, News, and official Local Event sources;
- `ffmpeg` for HEIC/HEIF conversion and ImageMagick `magick` for optional photo normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

For Local Event browser feedback from another computer:

- Chrome or another Chromium browser that supports unpacked Manifest V3 extensions;
- network access from that computer to `http://<surface-lan-address>:8765`;
- access to the official Event sites from that computer.

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

The smallest local startup is successful when:

1. the server prints a startup line for `0.0.0.0:8765`;
2. `GET /` returns the dashboard HTML and references `assets/js/dashboard.js` and `assets/js/local_event_card.js`;
3. `GET /openapi.json` returns a JSON document whose title is `InfoScreen Local API`;
4. the browser opens the page even when runtime files are missing, with missing or unavailable states shown instead of invented data.

A full deployment has additional success signals: `bash scripts/infoscreen_status.sh` reports the HTTP service and relevant timers, runtime files have current modification times, and visible panels agree with their served JSON.

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
- local OpenAPI documentation;
- a Local Event operator page for list-page review, Event review, diagnostics, and independent browser feedback.

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
  -> surface/serve_infoscreen.py on port 8765
  -> kiosk browser
  -> optional operator browser on another LAN device
```

Repository root:

```text
~/infoscreen
```

Runtime and personal-data root:

```text
~/infoscreen/surface/.env
```

## 3. Data sources, producers, and page consumers

| Product area | Data source | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- | --- |
| Market card and tape | Nasdaq, CNBC, Stooq, Yahoo, previous cache | `infoscreen-live-data.timer` or Market refresh | `market.json`, `/market.json` | `dashboard.js` |
| Weather | Open-Meteo using Singapore coordinates | `infoscreen-live-data.timer` or Market refresh | `weather.json`, `/weather.json` | `dashboard.js` |
| Multilingual News | Google News RSS, CNA, France24, RFI, BBC Chinese, Google Translate | `infoscreen-event-stream.timer` | `event_stream.json`, `/event_stream.json` | `local_event_card.js` |
| Local Events | Curated official listing and detail pages | `infoscreen-local-events.timer` or location search | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Local Event review | Candidate list pages, detail pages, operator decisions | Operator actions | `/api/local-events/review/*`, `local_event_review/state.json` | Local Event Studio scripts |
| Browser feedback | Official page in the operator's current Chrome | Chrome helper | `/api/local-events/review/open-feedback` | Chrome helper content script |
| Calendar | macOS Calendar/EventKit | Mac LaunchAgent | `schedule.json`, `/schedule.json` | `calendar_board.js` |
| Photos | User files under `surface/.env/photos/` | Manual photo builder | `photos.json`, `/photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Runtime-file HTTP `Last-Modified` | Browser `HEAD` checks | Schedule, Weather, Market, News endpoints | `local_event_card.js` |
| Market configuration | User-selected symbols | Market config UI | `/api/market-config`, `market_config.json` | `market_custom.js` |

Each visible DOM mount has one renderer owner. Producers write runtime data; browser scripts render it; the HTTP server serves files and local APIs.

## 4. User interaction and configuration

### Market symbols

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and refreshes Market data.
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

- The last location is stored in browser `localStorage` as `local_events_location`.
- Search sends `POST /api/local-events/search`.
- The server runs the source-specific collector and returns the resulting runtime payload.
- The configured official source inventory remains the same; the location is an input to the job.
- Previous and next controls change the current card immediately.

### Local Event review and user feedback

The branch `develop/surface-local-events-coverage` adds an operator page to the existing HTTP service. It does not add a second server, service, or port.

Update and restart the Surface service:

```bash
cd ~/infoscreen
git fetch origin
git switch develop/surface-local-events-coverage
git pull --ff-only origin develop/surface-local-events-coverage
systemctl --user restart infoscreen-http.service
```

Use the installer instead when dependencies or user units also need updating:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

Open on the Surface:

```text
http://127.0.0.1:8765/local-events/studio/
```

Open from another computer on the same trusted LAN:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

The page exposes two independent abilities.

#### Ability 1: review system-collected list pages and Events

1. Select the global institution when work should be scoped to one organisation.
2. Click `COLLECT LIST PAGES`.
3. Inspect candidate URLs. Use `PREVIEW EVENTS` before confirming a page.
4. Choose `CONFIRM LIST PAGE`, `REJECT`, or `RESET`.
5. Click `COLLECT EVENTS FROM CONFIRMED PAGES`.
6. Review each Event and choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

A list card is admitted from a configured official list when it has a usable title and exactly one canonical official detail link. The list card itself does **not** need to repeat the date or venue. The collector follows the detail page for date/time, location, title, summary, and detail status.

Each Event card shows:

- official detail URL;
- detail-page result and any detail error;
- originating listing URL;
- DOM selector;
- selector match number;
- listing-page index;
- document position.

When a preview returns zero Events, the card must show an exact recognition reason and stage counts, such as page access, official-domain link discovery, detail-route recognition, independent-card isolation, DOM evidence, selector generation, or detail-page failure. A correct list URL is not rejected merely because its cards omit dates.

The review page does not rebuild all cards every three seconds. State reload happens after explicit actions, manual `RELOAD`, and when the operator returns to the tab.

#### Ability 2: browse on the current computer and point to an Event

This ability is independent from Ability 1. It does not require discovery, confirmation, or Event collection first.

The supported flow runs in Chrome on the computer currently displaying the operator page. It does not open a browser on the Surface.

One-time helper installation:

1. Click `DOWNLOAD CHROME HELPER`.
2. Extract `infoscreen-local-event-feedback-extension.zip`.
3. Open `chrome://extensions`.
4. Enable `Developer mode`.
5. Click `Load unpacked`.
6. Select the extracted directory.
7. Reload the InfoScreen operator page.

Use it:

1. Select the institution and listing page.
2. Click `OPEN ON THIS DEVICE`.
3. The official listing opens in a normal tab in the current Chrome profile, using that computer's cookies and session.
4. Browse normally: accept cookies, scroll, filter, paginate, expand sections, and follow normal page controls.
5. Only when the required Event is visible, click `POINT TO EVENT`.
6. Click the corresponding Event link, card, row, or tile.
7. Use `SMALLER` or `LARGER` to choose the correct DOM level.
8. Click `SUBMIT THIS POSITION`.
9. Return to the operator tab; submitted selector, match number, page position, visible text, page URL, and link appear under `Submitted positions`.

`POINT TO EVENT` pauses only the selection click. Normal browsing remains available in `BROWSE` mode.

Review state is stored under:

```text
surface/.env/local_event_review/
├── state.json
├── browser_sessions/
└── browser_profiles/
```

`state.json` contains review decisions, diagnostics, Event candidates, and submitted feedback. `browser_sessions/` and `browser_profiles/` remain for the legacy Surface-local Playwright mode; the operator page uses the client-device Chrome helper.

For a manual foreground server start:

```bash
cd ~/infoscreen
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

A graphical Surface session is not required for the client-device Chrome helper. Playwright and Chromium remain required for system collection in Ability 1.

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

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds |
| Photos | Manual builder | No supported timer |

Surface timer configuration lives under `deploy/systemd/user/`.

### Browser data reload

| UI area | Browser reload behaviour |
| --- | --- |
| Market | Page load, every 60 seconds, and after Market refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | Page load and every 60 seconds using `HEAD` |
| Local Events | Page load and after an on-demand location search |
| Local Event review | Initial load, explicit action, manual `RELOAD`, and tab return; no recurring three-second rebuild |
| Calendar | Page load only |
| Photos | Page load and every 5 minutes |

### Visual rotation

| UI area | Rotation |
| --- | --- |
| Local Event card | Every 15 seconds |
| Calendar board | Every 7 seconds |
| Photo wall | Every 9 seconds |
| News and Market tapes | Continuous animation |

Producer refresh, browser reload, and visual rotation are independent.

## 6. Local Events is source-specific by design

The maintained inventory is:

```text
surface/conf/event_sources.json
```

Each source defines its ID, name, official home, allowed domains, official list URLs, default venue, adapter, and display order.

Both `rendered_dom_card` and `nhb` require a rendered card from a configured official activity list before an item can enter the result set. Positive Event intent means membership in that official list; an explicit type, date range, or event-looking route is not an alternative admission path.

Current collection behaviour includes:

- fully rendering and expanding configured official lists;
- admitting isolated list cards with one canonical official detail URL and a usable title;
- allowing listing cards without dates;
- following admitted detail pages for required date/time, location, title, summary, and public URL;
- using XHR/fetch JSON and embedded structured state only to enrich a matched list card;
- discarding unmatched structured records even when typed as `Event`;
- avoiding title and URL blacklists as the primary decision mechanism;
- preserving configured source order;
- recording per-source and per-listing admission, rejection, and failure evidence;
- preserving previous verified rows when a partial run would replace them with fewer results.

Primary output:

```text
surface/.env/local_event_search_results.json
```

Incomplete diagnostic output:

```text
surface/.env/local_event_search_results.partial.json
```

Debug evidence:

```text
surface/.env/local_event_debug_cards/
```

## 7. Project structure

```text
surface/serve_infoscreen.py                         local HTTP server and APIs
surface/fetch_live_data.py                          Market and Weather producer
surface/fetch_event_stream.py                       multilingual News producer
surface/search_local_events.py                      Local Events command wrapper
surface/jobs/local_event_search.py                  Local Events job entrypoint
surface/local_events_runtime/                       Local Events collection, review, diagnostics, feedback
surface/conf/                                       committed defaults and source inventory
surface/web/                                        kiosk and operator frontend
surface/web/local-events/feedback-extension/        client-device Chrome helper source
surface/.env/                                       local runtime and personal data
mac/                                                EventKit export and schedule push
deploy/systemd/user/                                committed Surface user units
scripts/                                            status, validation, repository scripts
docs/                                               architecture, API, requirement clarifications
tests/                                              unit and contract tests
```

## 8. Deployment and update

### Surface dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium
python3 -m pip install --user playwright pydantic
```

`surface/local_events_runtime/browser.py` uses an installed Chromium-compatible browser. Set `INFOSCREEN_CHROMIUM_PATH` only when auto-detection does not find it.

### Install Surface services and timers

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

This creates `surface/.env/`, installs user units, starts the HTTP service, enables timers, and triggers initial producer runs.

### Update an existing deployment

```bash
cd ~/infoscreen
git pull --ff-only
bash deploy/scripts/install-user-systemd.sh
```

When only application code changed and dependencies/units are already installed:

```bash
systemctl --user restart infoscreen-http.service
```

The server binds `0.0.0.0:8765`; network exposure must be controlled by the host and trusted local network.

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

### Page does not open

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
curl -v http://127.0.0.1:8765/
```

For another LAN device, also verify the Surface address, host firewall, and that port `8765` is reachable.

### Local Event review page flickers or shows stale diagnostics

The operator page should not poll and rebuild every three seconds. After updating:

```bash
cd ~/infoscreen
git pull --ff-only origin develop/surface-local-events-coverage
systemctl --user restart infoscreen-http.service
```

Then force-refresh the operator page. If the page reports `backend_diagnostics_not_loaded`, the frontend assets are newer than the running Python service. Restart the service and run `PREVIEW EVENTS` again so the current backend writes a diagnostic record for that exact list URL.

### Chrome helper is not detected

1. Download the helper again from the operator page.
2. Extract the ZIP.
3. Open `chrome://extensions`.
4. Verify Developer mode is enabled.
5. Remove the old unpacked extension if its directory changed.
6. Load the current extracted directory.
7. Reload the operator page.

The helper must be installed on the computer from which the operator page is being used, not on the Surface.

### Market or Weather is stale or missing

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

### Local Events is empty, partial, stale, or contains a bad record

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

Inspect `debug_by_source` and the operator page's `listing_diagnostics`. Determine whether failure occurred during page access, list expansion, official detail-link recognition, independent-card isolation, DOM evidence, selector generation, detail access, date parsing, or the total budget.

For a bad row, first identify the configured official list card that admitted it. Structured JSON or an Event-looking route without a matching list card is not sufficient.

### Schedule is stale or missing

On the Mac:

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

### Photos are empty

```bash
find surface/.env/photos -maxdepth 1 -type f -print
python3 surface/build_photos_json.py
python3 -m json.tool surface/.env/photos.json | less
```

### Sync `AGE` is unexpectedly large

The Sync ticker compares the browser clock with HTTP `Last-Modified`. Check producer state, runtime-file modification time, HTTP headers, and device clocks. `ERR` means the browser `HEAD` request failed and does not by itself prove the producer failed.

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

Generated validation artifacts belong under:

```text
${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}
```

Manual producer commands:

```bash
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/search_local_events.py "Punggol Singapore"
python3 surface/build_photos_json.py
```

Before changing code or documentation, read `AGENTS.md`, `AGENT.md`, and `skills/SKILL.md`, then the relevant source, tests, deployment files, and documentation.

## 11. Documentation

```text
README.md          onboarding, capabilities, interaction, refresh, deployment, troubleshooting
docs/design.md     architecture, source ownership, data flow, implementation boundaries
docs/api-spec.md   HTTP methods, callers, payloads, side effects, runtime mapping
docs/questions.md  requirement clarifications with implementation and acceptance evidence
AGENT.md           repository-specific contribution rules
AGENTS.md          required agent read order
```
