# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, schedule, weather, market movement, multilingual news, nearby official Events, local photos, and runtime freshness in one stable kiosk page.

The project favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from curated official organisation pages. Calendar authority remains on a Mac using macOS Calendar and EventKit. Runtime JSON, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files.

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

API documentation:

```text
http://127.0.0.1:8765/docs
```

## Prerequisites

Small local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when using supported deployment scripts.

Full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and Python Playwright for Local Events;
- Pydantic 2;
- outbound network access for Market, Weather, News, and official Event sources;
- `ffmpeg` for HEIC or HEIF conversion;
- ImageMagick `magick` for optional photo normalization;
- a Mac with EventKit-capable Python only for Calendar sync.

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
- Market card and global Market tape;
- Singapore weather;
- aligned English, French, and Chinese news;
- Local Events from curated official institutions;
- Calendar board supplied by macOS Calendar and EventKit;
- local Photo wall;
- Sync ticker for fresh, stale, missing, or unreachable runtime files;
- local OpenAPI documentation;
- Local Event Studio for list-page review, Event review, manual official list entry, and diagnostics.

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

## Data ownership

| Product area | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` or manual refresh | `market.json`, `weather.json` | `dashboard.js` |
| Multilingual News | `infoscreen-event-stream.timer` | `event_stream.json` | `local_event_card.js` |
| Local Events | `infoscreen-local-events.timer`, location search, and Review decisions | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Local Event review | Operator actions | `/api/local-events/review/*`, `local_event_review/state.json` | Studio scripts |
| Calendar | Mac LaunchAgent | `schedule.json` | `calendar_board.js` |
| Photos | Manual photo builder | `photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Browser `HEAD` checks | Runtime endpoints | `local_event_card.js` |

Producer jobs write runtime data. Browser scripts render it. The HTTP server serves files and local APIs.

## Market symbols

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and refreshes Market data.
- `REFRESH` sends `POST /api/market-refresh`.
- Market refresh also refreshes Weather.
- At most 12 unique symbols are stored.

## Local-event location

- The last location is stored in browser `localStorage` as `local_events_location`.
- Search sends `POST /api/local-events/search`.
- The server runs the complete source-specific producer and returns the combined runtime payload.

## Local Event Studio

Open on the Surface:

```text
http://127.0.0.1:8765/local-events/studio/
```

From another trusted LAN computer:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

### Review list pages and Events

1. Select the institution when work should be scoped to one organisation.
2. Click `COLLECT LIST PAGES`.
3. Inspect candidate URLs and use `PREVIEW EVENTS`.
4. Choose `CONFIRM LIST PAGE`, `REJECT`, or `RESET`.
5. Click `COLLECT EVENTS FROM CONFIRMED PAGES`.
6. Review each Event and choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

A usable official list card proves activity membership. A card may use either:

- one official detail URL, with date, venue, and summary enriched from the detail page; or
- complete fields directly on the official list, with the official list URL used as its public URL.

Several listing-only activities may share one list URL and must remain separate Events.

Every candidate shows its originating list URL, DOM selector, selector match number, page index, document position, detail URL when present, and detail result.

### Effect of Event decisions

`RELATED ACTIVITY` is immediately overlaid into `local_event_search_results.json` and becomes visible on the Surface. It does not delete automatically collected Events.

`NOT RELATED` or `RESET` removes only the row previously published from Review state. It does not remove an equivalent automatically collected Event.

A confirmed candidate is not rejected again because a date, summary, venue, or independent detail page is unavailable.

### Add one correct official list page manually

1. Select exactly one institution.
2. Paste the correct official list URL.
3. Click `ADD LIST PAGE`.
4. The page appears as `pending`.
5. Preview it and use the normal confirm or reject flow.

The backend validates the configured institution, absolute HTTP or HTTPS URL, and allowed hostname. Manual addition changes Review state only; it does not modify committed `event_sources.json` or collect automatically.

### Zero-result diagnostics

A zero result shows the failed recognition stage rather than only `0 EVENT`. Diagnostics include page access, visible links, official-domain links, possible detail links, extracted and admitted cards, DOM evidence, selectors, candidates, detail status, and stable reason codes.

Review state is stored at:

```text
surface/.env/local_event_review/state.json
```

## Complete Local Events producer

The maintained institution inventory is:

```text
surface/conf/event_sources.json
```

The supported producer:

- starts every configured institution source;
- renders and expands every configured official list;
- preserves official list-card evidence;
- enriches admitted cards from official detail pages when available;
- supports complete listing-only cards;
- preserves configured source order;
- records per-source and per-listing evidence;
- normalizes newly collected producer rows;
- protects verified rows when a later run is incomplete;
- overlays current confirmed Review Events;
- atomically writes the primary runtime.

Coverage budgets are applied to the live runtime modules. They allow all source-concurrency batches and enough per-source time for detail pages. Runtime configuration may raise these floors but must not silently lower the supported scope.

Primary output:

```text
surface/.env/local_event_search_results.json
```

Incomplete evidence:

```text
surface/.env/local_event_search_results.partial.json
```

Debug evidence:

```text
surface/.env/local_event_debug_cards/
```

The partial file does not replace a larger protected producer result. The primary output always combines protected producer rows with current confirmed Review rows.

## HTTP/2 handling

Supported collection entry points apply:

```text
surface/local_events_runtime/http1_browser.py
```

before collection. Every patched Chromium launch includes:

```text
--disable-http2
```

There is no HTTP/2-first attempt or protocol retry loop.

## Refresh behaviour

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds |
| Photos | Manual builder | No timer |

The Local Event Studio reloads on initial load, explicit operations, manual `RELOAD`, and tab return. The kiosk Local Events card polls the primary runtime and avoids redrawing unchanged content.

## Project structure

```text
surface/serve_infoscreen.py                         local HTTP server and APIs
surface/fetch_live_data.py                          Market and Weather producer
surface/fetch_event_stream.py                       multilingual News producer
surface/search_local_events.py                      supported Local Events wrapper
surface/jobs/local_event_search.py                  Local Events producer orchestration
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

This step is required after changing service unit files. It copies the units, reloads the user systemd manager, and restarts the services. The Local Events oneshot and HTTP subprocess timeouts are sized for the complete producer run.

When unit files have not changed, restart only the HTTP service:

```bash
systemctl --user restart infoscreen-http.service
```

## Operation and troubleshooting

Check deployment:

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

Check HTTP:

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

A complete run should show all configured sources in `debug_by_source`. A source with `elapsed_seconds: 0` and `skipped_by_global_deadline` indicates an invalid deployment or old runtime, not an acceptable reduced result.

For Studio preview failures, inspect `event_collection.listing_diagnostics` in `surface/.env/local_event_review/state.json`.

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

Run only checks appropriate to the task and report exactly what was or was not executed.

## Documentation

```text
README.md          onboarding, capabilities, interaction, deployment, troubleshooting
docs/design.md     architecture, ownership, data flow, implementation boundaries
docs/api-spec.md   HTTP methods, payloads, side effects, runtime mapping
docs/questions.md  requirement clarifications and acceptance evidence
AGENT.md           repository-specific contribution rules
AGENTS.md          required read order and safe boundary
```
