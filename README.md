# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from curated official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Runtime JSON, machine-local configuration, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files or generated artifacts to commit.

## First 10 minutes

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

Open:

```text
http://127.0.0.1:8765/
```

Open API documentation:

```text
http://127.0.0.1:8765/docs
```

## Prerequisites

For the smallest local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For the full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package for system-collected Local Events;
- Pydantic 2;
- outbound network access for Market, Weather, News, and official Local Event sources;
- `ffmpeg` for HEIC/HEIF conversion and ImageMagick `magick` for optional photo normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

## Runtime and configuration

Runtime and personal data belong under:

```text
~/infoscreen/surface/.env/
```

Committed configuration includes:

```text
surface/conf/market_config.default.json
surface/conf/event_sources.json
```

Do not commit runtime JSON, logs, debug captures, personal photos, SSH details, or machine-local environment files.

## Product areas

The dashboard includes:

- current time, date, page refresh time, and page-session uptime;
- a Market card and global Market tape with configurable symbols;
- current Singapore weather;
- aligned English, French, and Chinese news rows;
- a Local Events card built from curated official organisation sources;
- a Calendar board supplied by macOS Calendar/EventKit;
- a local Photo wall;
- a Sync ticker showing whether Schedule, Weather, Market, and News runtime files are fresh, stale, missing, or unreachable;
- local OpenAPI documentation;
- a Local Event operator page for list-page review, Event review, manual correct-list-page entry, and diagnostics.

## Runtime model

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
  -> optional operator browser on another trusted LAN device
```

## Data sources and ownership

| Product area | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` or Market refresh | `market.json`, `weather.json` | `dashboard.js` |
| Multilingual News | `infoscreen-event-stream.timer` | `event_stream.json` | `local_event_card.js` |
| Local Events | `infoscreen-local-events.timer` or location search | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Local Event review | Operator actions | `/api/local-events/review/*`, `local_event_review/state.json` | Local Event Studio scripts |
| Calendar | Mac LaunchAgent | `schedule.json` | `calendar_board.js` |
| Photos | Manual photo builder | `photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Browser `HEAD` checks | Runtime endpoints | `local_event_card.js` |

Each visible DOM mount has one renderer owner. Producers write runtime data; browser scripts render it; the HTTP server serves files and local APIs.

## Market symbols

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and refreshes Market data.
- `REFRESH` sends `POST /api/market-refresh`.
- A Market refresh runs `surface/fetch_live_data.py`, so it refreshes both Market and Weather.
- At most 12 unique symbols are stored.

## Local-event location

- The last location is stored in browser `localStorage` as `local_events_location`.
- Search sends `POST /api/local-events/search`.
- The server runs the source-specific collector and returns the resulting runtime payload.

## Local Event Studio

The operator page uses the existing HTTP service and port:

```text
http://127.0.0.1:8765/local-events/studio/
```

From another computer on the same trusted LAN:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

Update and restart:

```bash
cd ~/infoscreen
git fetch origin
git switch develop/surface-local-events-coverage
git pull --ff-only origin develop/surface-local-events-coverage
systemctl --user restart infoscreen-http.service
```

### Review system-collected list pages and Events

1. Select the global institution when work should be scoped to one organisation.
2. Click `COLLECT LIST PAGES`.
3. Inspect candidate URLs and use `PREVIEW EVENTS`.
4. Choose `CONFIRM LIST PAGE`, `REJECT`, or `RESET`.
5. Click `COLLECT EVENTS FROM CONFIRMED PAGES`.
6. Review each Event and choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

A listing card needs a usable title and one official detail link. The list card itself does not need to repeat date or venue. The collector follows detail pages for title, date/time, location, summary, and detail status.

Every Event candidate shows its originating list URL, DOM selector, selector match number, listing page index, document position, detail URL, and detail result.

### Add a correct Event list page manually

The manual input is directly below the top collection toolbar.

1. Select exactly one value in `Global institution`.
2. Paste the correct official Event list URL into `Add an official Event list page to the selected global institution`.
3. Click `ADD LIST PAGE`.
4. The page is saved as `pending` and appears in the left-side Event list pages.
5. Use `PREVIEW EVENTS`.
6. Confirm or reject it through the same review flow.

The backend validates that:

- the institution exists in `surface/conf/event_sources.json`;
- the URL is absolute HTTP/HTTPS;
- the hostname is within that institution’s `allowed_domains`.

Manual addition does not modify committed `event_sources.json` and does not collect Events automatically. Adding the same URL again resets it to `pending` for re-review.

### Zero-result diagnostics

A zero result must show the exact failed recognition stage rather than only `0 EVENT`. Diagnostics include page access, visible links, official-domain links, possible detail links, extracted cards, admitted cards, DOM evidence, selector generation, candidates, and detail-page status.

### HTTP/2 handling

System collection does not first try HTTP/2 and then retry. The supported entrypoints apply:

```text
surface/local_events_runtime/http1_browser.py
```

before collector imports, and every patched Chromium launch includes:

```text
--disable-http2
```

This applies to:

- Studio discovery and Event collection through `surface/serve_infoscreen.py`;
- scheduled and HTTP-triggered Local Events through `surface/search_local_events.py`.

### Interactive browser feedback status

The downloadable Chrome Helper, ZIP generator, unpacked extension files, and remote helper transport were removed. The Studio marks Ability 2 as `NOT IMPLEMENTED`; no download or generated archive is required or produced.

Review state is stored under:

```text
surface/.env/local_event_review/state.json
```

## Local Events collection policy

The maintained institution inventory is:

```text
surface/conf/event_sources.json
```

Collection behaviour includes:

- rendering and expanding configured official lists;
- admitting isolated list cards with one official detail URL and a usable title;
- allowing listing cards without dates;
- following admitted detail pages for required date/time, location, title, summary, and public URL;
- using XHR/fetch JSON and embedded structured state only to enrich a matched list card;
- discarding unmatched structured records;
- avoiding title and URL blacklists as the primary decision mechanism;
- preserving configured source order;
- recording per-source and per-listing evidence;
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

## Refresh behaviour

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds |
| Photos | Manual builder | No timer |

The Local Event Studio reloads on initial load, explicit operations, manual `RELOAD`, and tab return. It does not rebuild all cards every three seconds.

## Project structure

```text
surface/serve_infoscreen.py                         local HTTP server and APIs
surface/fetch_live_data.py                          Market and Weather producer
surface/fetch_event_stream.py                       multilingual News producer
surface/search_local_events.py                      supported Local Events wrapper
surface/jobs/local_event_search.py                  Local Events job
surface/local_events_runtime/                       collector, review, diagnostics, browser policy
surface/conf/                                       committed defaults and institution inventory
surface/web/                                        kiosk and operator frontend
surface/.env/                                       local runtime and personal data
mac/                                                EventKit export and schedule push
deploy/systemd/user/                                Surface user units
scripts/                                            status and acceptance scripts
docs/                                               architecture, API, requirement clarifications
tests/                                              unit and contract tests
```

## Deployment

Install dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium
python3 -m pip install --user playwright pydantic
```

Install or update user services:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

When dependencies and unit files are already installed:

```bash
systemctl --user restart infoscreen-http.service
```

## Operation and troubleshooting

Check deployment:

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

Check HTTP service:

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
curl -v http://127.0.0.1:8765/
```

Check Local Events:

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

When a Studio preview fails, inspect `event_collection.listing_diagnostics` in:

```text
surface/.env/local_event_review/state.json
```

A failure before DOM parsing should be shown as a page/navigation error. Missing date on the listing card is not a rejection reason.

## Calendar sync

Run on the Mac:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user <surface-ssh-user> \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

The Surface does not generate Calendar data.

## Photos

Place files under:

```text
surface/.env/photos/
```

Then rebuild:

```bash
python3 surface/build_photos_json.py
```

## Development and validation

Install test dependencies:

```bash
python3 -m pip install --user pytest pydantic
```

Repository checks include:

```bash
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

Run only checks appropriate to the requested task and report exactly what was or was not executed.

## Documentation

```text
README.md          onboarding, capabilities, interaction, deployment, troubleshooting
docs/design.md     architecture, ownership, data flow, implementation boundaries
docs/api-spec.md   HTTP methods, payloads, side effects, runtime mapping
docs/questions.md  requirement clarifications and acceptance evidence
AGENT.md           repository-specific contribution rules
AGENTS.md          required read order and safe boundary
```
