# InfoScreen design

## Runtime ownership

`surface/serve_infoscreen.py` owns HTTP serving, static dashboard delivery, runtime JSON delivery, public photo delivery, and local API endpoints. It is run by `infoscreen-http.service`.

Runtime JSON files live under `surface/.env/`. They are local machine state, not source files.

## Repository root policy

The repository root is reserved for repository control, documentation, metadata, CI/test configuration, and operator/deployment entrypoints.

Allowed root-level project paths:

```text
README.md
AGENTS.md
AGENT.md
metadata.json
pyproject.toml
.gitignore
.githooks/
.github/
docs/
skills/
surface/
deploy/
mac/
scripts/
tests/
```

Runtime JSON belongs under `surface/.env/`. Browser CSS and JavaScript belong under `surface/web/assets/`. Local photo inputs belong under `surface/.env/photos/`. Test fixtures belong under `tests/fixtures/`.

These paths are not runtime locations and should stay absent from the repository root:

```text
schedule.json
weather.json
market.json
event_stream.json
photos.json
*.css
*.js
```

The local pre-commit hook at `.githooks/pre-commit` and the repository-wide checker at `scripts/ci/check_repo.py --suite all --scope repository` enforce this policy for committed files.

Legacy static files directly under `surface/web/*.js` or `surface/web/*.css` are not active source paths and should be removed instead of replaced with placeholders.

## Active implementation files

Server and API support:

```text
surface/serve_infoscreen.py       HTTP server and local API
surface/openapi_spec.py           support module for /openapi.json
surface/api_models.py             schema support module for openapi_spec.py
```

Jobs and wrappers:

```text
surface/fetch_live_data.py         weather and market refresh
surface/fetch_event_stream.py      event/news stream refresh
surface/build_photos_json.py       photo wall JSON builder
surface/search_local_events.py     compatibility wrapper
surface/jobs/local_event_search.py local event refresh job
mac/export.py                      macOS Calendar/EventKit export
mac/sync_schedule.sh               Mac-to-Surface schedule push
```

Active browser files:

```text
surface/web/index.html
surface/web/assets/js/dashboard.js
surface/web/assets/js/calendar_board.js
surface/web/assets/js/local_event_card.js
surface/web/assets/js/market_custom.js
surface/web/assets/css/app.css
surface/web/assets/css/calendar_board.css
surface/web/assets/css/local_events.css
surface/web/assets/css/market_custom.css
```

## Page UI ownership and data sources

Every visible DOM mount has one renderer. A producer job may feed multiple UI areas, but multiple browser scripts must not rewrite the same mount point.

| Page area | DOM mount | Browser owner | Scheduler / trigger | Producer and runtime/API | External or local source | Failure effect |
| --- | --- | --- | --- | --- | --- | --- |
| Header clock/date | `#time`, `#date` | `dashboard.js:updateClock()` | Browser every second | None | Browser device clock | Wrong browser clock produces wrong display time |
| Bottom refresh/page uptime | `#refresh`, `#uptime` | `dashboard.js:updateClock()` | Browser every second | None | Browser time and page start timestamp | `UPTIME` is page-session uptime, not Surface OS uptime |
| Market card | `#marketList` | `dashboard.js:loadMarket()` | `infoscreen-live-data.timer` every 5 minutes; `/api/market-refresh` on demand | `surface/fetch_live_data.py` → `surface/.env/market.json` → `/market.json` | Nasdaq, CNBC, Stooq, Yahoo fallback and stale cache | Error row with `market.json FAIL` |
| Global market tape | `#globalMarketTapeTrack` | `dashboard.js:loadMarket()` | Same Market job | Same `market.json` | Same market providers | Market failure tape |
| Market config overlay | Dynamic controls near `#marketList` | `market_custom.js` | User save/refresh | `/api/market-config`, `/api/market-refresh`, `surface/.env/market_config.json` | User-selected symbols | Config status reports save/refresh failure |
| Local event card | `#localEventList` | `local_event_card.js` | `infoscreen-local-events.timer` every 6 hours; POST search on demand | `surface/search_local_events.py` → `surface/jobs/local_event_search.py` → `surface/.env/local_event_search_results.json` → `/api/local-events/search` | Official listing pages in `surface/conf/event_sources.json` | `LOCAL EVENTS UNAVAILABLE` or search error |
| Sync ticker | `#leftSyncTapeTrack` | `local_event_card.js:loadSyncStatus()` | Browser every 60 seconds | `HEAD /schedule.json`, `/weather.json`, `/market.json`, `/event_stream.json` | Runtime file `Last-Modified` headers | `OK`, `STALE`, `MISS`, or `ERR` |
| EN/FR/ZH news ticker | `#newsTickerTrackEN`, `#newsTickerTrackFR`, `#newsTickerTrackZH` | `local_event_card.js:repairNews()` | `infoscreen-event-stream.timer` every 5 minutes | `surface/fetch_event_stream.py` → `surface/.env/event_stream.json` → `/event_stream.json` | Google News RSS, CNA, France24, RFI, BBC Chinese; Google Translate | Three ticker rows show error fallback |
| Photo wall | `#photoFlipWall` | `local_event_card.js:repairPhotoWall()` | Manual builder after photo changes | `surface/.env/photos/` → `surface/build_photos_json.py` → `surface/.env/photos.json` and `surface/.env/public_photos/` → `/photos.json`, `/public_photos/*` | User-owned local images | Empty/error photo message |
| Weather card | `#weatherTemp`, `#weatherDesc` | `dashboard.js:loadWeather()` | `infoscreen-live-data.timer` every 5 minutes | `surface/fetch_live_data.py` → `surface/.env/weather.json` → `/weather.json` | Open-Meteo, Singapore coordinates | `weather.json not loaded` |
| CPU/MEM/DSK/NET bars | `#cpuBar`, `#memBar`, `#diskBar`, `#netBar` | `dashboard.js:updateDemoMetrics()` | Browser every 6 seconds | None | `Math.random()` demo values | No backend failure path because these are not real metrics |
| Calendar board | `#agendaList` | `calendar_board.js` | Mac LaunchAgent `com.renchili.infoscreen.schedule-sync`, default 120 seconds | `mac/export.py` → `mac/sync_schedule.sh` → `surface/.env/schedule.json` → `/schedule.json` | macOS Calendar/EventKit on the Mac | `SCHEDULE ERROR` or empty schedule |
| POWER/DISPLAY/NETWORK labels | Static header/footer HTML | `index.html` | None | None | Static text | Not health checks and not tied to jobs |
| OpenAPI pages | `/openapi.json`, `/docs` | Server routes | HTTP request | `surface/openapi_spec.py` + `surface/api_models.py` | Committed API schema code | HTTP error only; not a kiosk panel |

## Browser renderer ownership

`dashboard.js` owns:

```text
#time
#date
#refresh
#uptime
#marketList
#globalMarketTapeTrack
#weatherTemp
#weatherDesc
#cpuBar / #cpuText
#memBar / #memText
#diskBar / #diskText
#netBar / #netText
```

`calendar_board.js` owns:

```text
#agendaList
#calendarBoardRows
```

`local_event_card.js` owns:

```text
#localEventList and local-event controls
#leftSyncTapeTrack
#newsTickerTrackEN
#newsTickerTrackFR
#newsTickerTrackZH
#photoFlipWall
```

`market_custom.js` owns only the market configuration button, panel, input, and status. It calls `window.loadMarket()` after a successful refresh and must not render quote rows itself.

The previous duplicate renderer pattern was invalid: `local_event_card.js` must not render Market, and `dashboard.js` must not render news or sync status. Duplicate asynchronous writers cause correct content to flash and then be overwritten by incompatible markup or classes.

## Local event implementation and source policy

The active local event code path is:

```text
infoscreen-local-events.timer
  -> infoscreen-local-events.service
  -> surface/search_local_events.py
  -> surface/jobs/local_event_search.py
  -> surface/local_events_runtime/__init__.py
  -> surface/local_events_runtime/extract.py
  -> surface/local_events_runtime/browser.py
  -> surface/.env/local_event_search_results.json
```

The same job can be triggered on demand through `POST /api/local-events/search` with a user-selected location.

`surface/conf/event_sources.json` contains verified official event listing entrypoints. The collection policy forbids third-party aggregators as the primary source and uses official museum, library, community, attraction, venue, and institution pages.

The backend owns collection, extraction, normalization, and API delivery. It should return the best available data without presentation-driven truncation. The frontend owns wrapping, clipping, scrolling, and visual ellipsis.

## Sync ticker contract

The sync ticker is an observer, not a producer. It performs `HEAD` requests and reads the HTTP `Last-Modified` header. `AGE` is calculated from the browser clock and runtime file modification time; it is not the event time and not JSON `updated_at`.

| Stat | Producer scheduler | Producer | Runtime JSON / endpoint | Product UI | Stale threshold |
| --- | --- | --- | --- | --- | --- |
| `SCHEDULE` | Mac LaunchAgent, default 120 seconds | `mac/export.py` + `mac/sync_schedule.sh` | `surface/.env/schedule.json`, `/schedule.json` | Calendar board | 600 seconds |
| `WEATHER` | `infoscreen-live-data.timer`, every 5 minutes | `surface/fetch_live_data.py` | `surface/.env/weather.json`, `/weather.json` | Weather card | 900 seconds |
| `MARKET` | `infoscreen-live-data.timer`, every 5 minutes | `surface/fetch_live_data.py` | `surface/.env/market.json`, `/market.json` | Market card and tape | 600 seconds |
| `NEWS` | `infoscreen-event-stream.timer`, every 5 minutes | `surface/fetch_event_stream.py` | `surface/.env/event_stream.json`, `/event_stream.json` | EN/FR/ZH news ticker | 600 seconds |

```text
OK     file exists and AGE is within threshold
STALE  file exists but AGE exceeds threshold
MISS   path is missing or Last-Modified is absent
ERR    HEAD request failed; check HTTP/network before blaming the producer
```

Failure routing:

- `SCHEDULE STALE/MISS`: check the Mac LaunchAgent, `mac/local.env`, and `~/Library/Logs/infoscreen-sync/`. The schedule producer does not run on the Surface.
- `WEATHER STALE/MISS` or `MARKET STALE/MISS`: check `infoscreen-live-data.timer`, `infoscreen-live-data.service`, and `surface/fetch_live_data.py` on the Surface.
- `NEWS STALE/MISS`: check `infoscreen-event-stream.timer`, `infoscreen-event-stream.service`, and `surface/fetch_event_stream.py`.
- Any `ERR`: check `infoscreen-http.service` and browser access to the corresponding path first.
- A newly written file with a large `AGE`: compare browser, Surface, and for schedule Mac system clocks.

## Market contract and data providers

`surface/fetch_live_data.py` loads configured symbols and tries providers in this order:

```text
Nasdaq
CNBC
Stooq daily
Yahoo chart
previous market.json stale cache
```

The job writes provider/session metadata into `market.json`. `dashboard.js` renders price, session, direction class, and percentage consistently for both the card and the global tape.

`dashboard.js` is the only renderer allowed to write `marketList` and `globalMarketTapeTrack`. `market_custom.js` only changes configuration or requests refresh. `local_event_card.js` only monitors `market.json` freshness through `HEAD` and must not render Market content.

## News contract and sources

`surface/fetch_event_stream.py` reads configured RSS sources including Google News searches, CNA, France24, RFI, and BBC Chinese. It selects a base set and creates aligned EN/FR/ZH rows using Google Translate where needed.

The runtime payload writes `items_by_lang.en`, `items_by_lang.fr`, and `items_by_lang.zh`. `local_event_card.js` renders those arrays with fixed row labels `EN`, `FR`, and `中文`. It must not expose internal translated-source labels such as `TR-*` as the row labels.

## Photo wall contract

Photo inputs are local files under:

```text
surface/.env/photos/
```

`surface/build_photos_json.py` normalizes/copies images into `surface/.env/public_photos/` and writes `surface/.env/photos.json`. The browser does not scan the filesystem. There is currently no systemd photo timer; the builder must be run after photo files change.

## Simulated and static UI contract

The following page content is not backed by runtime jobs:

- Clock, date, refresh time, and page uptime use browser-local time.
- CPU/MEM/DSK/NET bars use `Math.random()` in `updateDemoMetrics()` and are not Surface metrics.
- POWER, DISPLAY, NETWORK, `AC_ONLY`, `ONLINE`, and `LAN_OK` are static HTML labels and are not health checks.

Documentation and tests must not describe these values as real monitoring until a real producer, runtime schema, endpoint, and renderer are implemented together.

## Runtime data flow

```text
infoscreen-http.service
  -> surface/serve_infoscreen.py
  -> index.html, assets, runtime JSON, public photos, local APIs

Mac Calendar/EventKit
  -> Mac LaunchAgent com.renchili.infoscreen.schedule-sync
  -> mac/export.py
  -> mac/sync_schedule.sh
  -> surface/.env/schedule.json
  -> /schedule.json
  -> calendar_board.js + sync ticker

infoscreen-live-data.timer
  -> infoscreen-live-data.service
  -> surface/fetch_live_data.py
  -> surface/.env/weather.json + surface/.env/market.json
  -> /weather.json + /market.json
  -> dashboard.js + sync ticker

infoscreen-event-stream.timer
  -> infoscreen-event-stream.service
  -> surface/fetch_event_stream.py
  -> surface/.env/event_stream.json
  -> /event_stream.json
  -> local_event_card.js news renderer + sync ticker

infoscreen-local-events.timer
  -> infoscreen-local-events.service
  -> surface/search_local_events.py
  -> surface/jobs/local_event_search.py
  -> surface/.env/local_event_search_results.json
  -> /api/local-events/search
  -> local_event_card.js local-event renderer

surface/.env/photos/
  -> manual surface/build_photos_json.py
  -> surface/.env/photos.json + surface/.env/public_photos/
  -> /photos.json + /public_photos/*
  -> local_event_card.js photo renderer

surface/.env/market_config.json
  <-> /api/market-config
  -> market_custom.js

POST /api/market-refresh
  -> surface/fetch_live_data.py
  -> window.loadMarket()

surface/openapi_spec.py + surface/api_models.py
  -> /openapi.json
  -> /docs
```

The Surface address used by `mac/sync_schedule.sh` is local deployment configuration in `mac/local.env`, not committed source. All runtime JSON targets remain under `surface/.env/`.
