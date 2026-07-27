# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from curated official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Runtime JSON, machine-local configuration, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files or generated artifacts to commit.

## First 10 minutes

The HTTP server imports the Local Events review models at startup, so Pydantic 2 is required even when only opening the kiosk page. On Ubuntu or the Surface, use an isolated environment:

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
sudo apt update
sudo apt install -y python3 python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install "pydantic>=2,<3"
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

The machine-readable contract remains available without the Swagger UI assets at:

```text
http://127.0.0.1:8765/openapi.json
```

## Prerequisites

For the smallest local path:

- Python 3 with `venv` support;
- Pydantic 2 installed in the active Python environment;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For the full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package for system-collected Local Events;
- Pydantic 2;
- outbound network access for Market, Weather, News, and official Local Event sources;
- `ffmpeg` for HEIC/HEIF conversion;
- ImageMagick `magick` for PNG/WebP-to-JPEG normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

Without ImageMagick, existing JPEG files can still be copied safely, but PNG and WebP inputs are skipped rather than renamed to a false `.jpg` format.

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
- current Singapore weather with a visible retained-data error state when live retrieval fails;
- aligned English, French, and Chinese news rows, with Singapore sources selected before the random remainder;
- a Local Events card built from curated official organisation sources;
- a Calendar board supplied by macOS Calendar/EventKit;
- a local Photo wall;
- a Sync ticker showing whether Schedule, Weather, Market, and News runtime files are fresh, stale, missing, or unreachable;
- local OpenAPI JSON and a Swagger UI wrapper;
- a Local Event operator page for list-page review, Event review, isolated single-page preview, manual correct-list-page entry, and diagnostics.

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
| Local Events | `infoscreen-local-events.timer` or explicit collection API | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
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

## Local-event dashboard filter

- The kiosk card reads current results with `GET /api/local-events/search`; opening or applying its filter does not run a collection.
- The institution dropdown is built from institutions present in the current event rows and includes `ALL INSTITUTIONS`.
- The text field filters title, institution/source, date/time, venue/place, and description. Multiple terms must all match the same event.
- The selected institution and text are stored in browser `localStorage` as `local_events_filter_source` and `local_events_filter_query`.
- Pressing `FILTER` filters the already-loaded rows in browser memory. It does not send `POST /api/local-events/search`, launch Chromium, or rewrite runtime JSON.
- Periodic GET reloads keep the current filter applied to newly loaded results.

`POST /api/local-events/search` remains an explicit producer trigger for operator/API use; it is not the kiosk filter action.

## Local Event Studio

The operator page uses the existing HTTP service and port:

```text
http://127.0.0.1:8765/local-events/studio/
```

From another computer on the same trusted LAN:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

The local server has no authentication layer. Do not expose port 8765 outside the trusted device/LAN boundary.

Update and restart the canonical branch:

```bash
cd ~/infoscreen
git fetch origin
git switch main
git pull --ff-only origin main
systemctl --user restart infoscreen-http.service
```

### Review system-collected list pages and Events

1. Select the global institution used to filter visible Review cards.
2. Click `COLLECT LIST PAGES`.
3. Inspect a candidate URL.
4. Use `PREVIEW EVENTS` at any time on a pending, confirmed, or rejected list-page card when an isolated page-specific preview is needed.
5. Choose `CONFIRM LIST PAGE`, `REJECT`, or `RESET` for the real list-page decision.
6. Click `COLLECT EVENTS FROM CONFIRMED PAGES` to refresh and persist all currently confirmed pages.
7. Review each Event and choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

`PREVIEW EVENTS` sends only the selected `listing_url` to `POST /api/local-events/review/preview-events`. The server copies the current Review state into a temporary directory, confirms only that selected page inside the temporary copy, clears temporary Event/feedback/collection data, and runs the normal final collector. It never changes the real list-page decision or persisted Review state, never changes other list-page decisions temporarily, and does not refresh other confirmed pages.

Normal collection remains separate: `COLLECT EVENTS FROM CONFIRMED PAGES` persists candidates and diagnostics for all confirmed pages.

A listing card needs a usable title and one official detail link. The list card itself does not need to repeat date or venue. The collector follows detail pages for title, date/time, location, summary, and detail status.

Every Event candidate shows its originating list URL, DOM selector, selector match number, listing page index, document position, detail URL, and detail result.

### Add a correct Event list page manually

The manual input is directly below the top collection toolbar.

1. Select exactly one value in `Global institution`.
2. Paste the correct official Event list URL into `Add an official Event list page to the selected global institution`.
3. Click `ADD LIST PAGE`.
4. The page is saved as `pending` and appears in the left-side Event list pages.
5. Use isolated `PREVIEW EVENTS` immediately when validation is needed; this does not confirm the page.
6. Confirm, reject, or reset the page.
7. Confirmed pages participate in normal `COLLECT EVENTS FROM CONFIRMED PAGES` runs.

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

This applies to Studio discovery, isolated preview, confirmed-page collection, and scheduled/HTTP-triggered Local Events.

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

Producer-owned snapshot:

```text
surface/.env/local_event_collector_results.json
```

Primary kiosk output:

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

The Local Event Studio loads on initial entry, explicit operations, manual `RELOAD`, and return to the browser tab. It does not register an idle polling interval. Full-card rendering emits one completion event, and the scroll guard restores the previous card anchor or scroll position after that completed render.

The Sync ticker observes per-file `Last-Modified`; it is not a scheduler.

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
sudo apt install -y python3 python3-pip curl ca-certificates chromium imagemagick ffmpeg
python3 -m pip install --user playwright "pydantic>=2,<3" || \
  python3 -m pip install --user --break-system-packages playwright "pydantic>=2,<3"
```

Install or update user services:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

The installer never deletes conflicting legacy runtime directories. When both the legacy root path and `surface/.env/` destination exist, it preserves the legacy path under `surface/.env/migration_backup/` and stops rather than overwriting an existing backup.

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

A normal confirmed-page collection stores diagnostics in:

```text
surface/.env/local_event_review/state.json
```

An isolated preview returns its diagnostics in the preview response and does not overwrite that persisted file. A failure before DOM parsing is shown as a page/navigation error. Missing date on the listing card is not a rejection reason.

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

The public `photos.json` contains only browser URLs, captions, and output types; it does not expose original absolute filesystem paths. JPEG inputs can be copied safely without ImageMagick. PNG and WebP require ImageMagick, while HEIC and HEIF require `ffmpeg`.

## Development and validation

Install test dependencies in an isolated environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install pytest "pydantic>=2,<3"
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
