# InfoScreen design

## Runtime ownership

`surface/serve_infoscreen.py` owns HTTP serving, static dashboard delivery, runtime JSON delivery, and local API endpoints.

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

Runtime JSON belongs under `surface/.env/`. Browser CSS and JavaScript belongs under `surface/web/assets/`. Local photo inputs belong under `surface/.env/photos/`. Test fixtures belong under `tests/fixtures/`.

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

## Python files

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
```

Local event extraction support:

```text
surface/local_events_runtime/__init__.py
surface/local_events_runtime/extract.py
surface/local_events_runtime/browser.py
```

## Local event implementation

The active local event code path is:

```text
surface/search_local_events.py
  -> surface/jobs/local_event_search.py
  -> surface/local_events_runtime/__init__.py
  -> surface/local_events_runtime/extract.py
  -> surface/local_events_runtime/browser.py
```

`surface/jobs/local_event_search.py` writes `surface/.env/local_event_search_results.json`.

Legacy duplicate local event engines/adapters are not active source paths.

## Local event data/display boundary

The backend owns collection, extraction, normalization, and API delivery. It should return the best available local-event data without presentation-driven truncation.

The frontend owns presentation. `surface/web/assets/js/local_event_card.js` and `surface/web/assets/css/local_events.css` decide how much text is visible in the current card, including wrapping, clipping, scrolling, and visual ellipsis.

Backend changes must not be used to make text fit a particular screen size. UI fitting belongs in CSS/JS.

## Browser dashboard files

Active HTML:

```text
surface/web/index.html
```

Active CSS:

```text
surface/web/assets/css/app.css
surface/web/assets/css/calendar_board.css
surface/web/assets/css/local_events.css
surface/web/assets/css/market_custom.css
```

Active JavaScript:

```text
surface/web/assets/js/dashboard.js
surface/web/assets/js/calendar_board.js
surface/web/assets/js/local_event_card.js
surface/web/assets/js/market_custom.js
```

## Local event UI contract

`surface/web/assets/js/local_event_card.js` owns local event rendering and search modal behavior.

`surface/web/assets/css/local_events.css` owns local event panel styling.

The local event panel must keep the compact TTY visual style:

```text
no dotted local-event background
counter aligned with ‹ / › / ⌕ controls on the top-right
source or organization at the card top-left
no standalone EVENT label
compact WHEN and WHERE rows
official link pinned to the bottom of the card
```

Local event content must remain visible when `/api/local-events/search` has results. The CSS must not hide, absolutely overlap the source/title, grid-collapse, nest excessive padded boxes, or place controls where they obscure source text.

## Sync ticker contract

The left sync ticker is a freshness indicator, not only a count indicator. `surface/web/assets/js/local_event_card.js` owns the freshness requests and ticker DOM only; it does not own the monitored product panels.

It sends `HEAD` requests to the runtime JSON paths, reads `Last-Modified`, and calculates `AGE` from the browser clock. `AGE` is the runtime file age, not an event timestamp and not the JSON payload's `updated_at` field.

| Stat | Scheduler / job | Producer | Runtime JSON | Product UI | Stale threshold |
| --- | --- | --- | --- | --- | --- |
| `SCHEDULE` | Mac LaunchAgent `com.renchili.infoscreen.schedule-sync`, default 120 seconds | `mac/export.py` then `mac/sync_schedule.sh` | `surface/.env/schedule.json` | `calendar_board.js` calendar panel | 600 seconds |
| `WEATHER` | Surface `infoscreen-live-data.timer`, every 5 minutes | `surface/fetch_live_data.py` | `surface/.env/weather.json` | `dashboard.js` weather panel | 900 seconds |
| `MARKET` | Surface `infoscreen-live-data.timer`, every 5 minutes | `surface/fetch_live_data.py` | `surface/.env/market.json` | `dashboard.js` market card and global tape | 600 seconds |
| `NEWS` | Surface `infoscreen-event-stream.timer`, every 5 minutes | `surface/fetch_event_stream.py` | `surface/.env/event_stream.json` | news ticker | 600 seconds |

Ticker states:

```text
OK     file exists and AGE is within its threshold
STALE  file exists but AGE exceeds its threshold
MISS   HTTP path is missing or has no Last-Modified header
ERR    HEAD request failed; check HTTP/network before assuming producer failure
```

Troubleshooting follows producer ownership. `SCHEDULE` is repaired on the Mac by checking the LaunchAgent, `mac/local.env`, and `~/Library/Logs/infoscreen-sync/`. `WEATHER` and `MARKET` are repaired on the Surface through `infoscreen-live-data.timer` and `infoscreen-live-data.service`. `NEWS` is repaired through `infoscreen-event-stream.timer` and `infoscreen-event-stream.service`. If a newly written file still shows a large `AGE`, compare the browser, Surface, and for schedule the Mac system clocks.

## Photo wall contract

User photo inputs should be placed in:

```text
surface/.env/photos/
```

`surface/build_photos_json.py` reads that runtime input directory, converts or copies images into `surface/.env/public_photos/`, and writes `surface/.env/photos.json`.

The browser does not scan the filesystem directly. After adding images, the builder must run before the dashboard can display them.

## Market UI contract

`surface/web/assets/js/dashboard.js` is the only renderer allowed to write `marketList` and `globalMarketTapeTrack`. It reads `market.json`, assigns `up`, `down`, or `flat` consistently, and renders both the market card and the global market tape.

`surface/web/assets/js/market_custom.js` owns the compact config button and editor overlay. After saving or manually refreshing, it calls `window.loadMarket()` instead of rendering quote rows itself.

`surface/web/assets/js/local_event_card.js` must not fetch `market.json`, define a secondary market renderer, or write either Market DOM mount point. Multiple asynchronous renderers cause the correct dashboard output to flash first and then be overwritten by incompatible classes and markup.

Symbol management stays behind the existing HTTP APIs:

```text
GET /api/market-config
POST /api/market-config
POST /api/market-refresh
```

## News ticker contract

The event stream writes `items_by_lang.en`, `items_by_lang.fr`, and `items_by_lang.zh`.

The browser must render the three rows with fixed row labels:

```text
EN
FR
中文
```

It must not expose translated source labels such as `TR-*` as row labels.

## Runtime data flow

```text
Mac Calendar/EventKit
  -> Mac LaunchAgent com.renchili.infoscreen.schedule-sync
  -> mac/export.py
  -> mac/sync_schedule.sh
  -> surface/.env/schedule.json
  -> /schedule.json
  -> assets/js/calendar_board.js and sync freshness ticker

Surface infoscreen-live-data.timer
  -> infoscreen-live-data.service
  -> surface/fetch_live_data.py
  -> surface/.env/weather.json and surface/.env/market.json
  -> /weather.json and /market.json
  -> assets/js/dashboard.js and sync freshness ticker

Surface infoscreen-event-stream.timer
  -> infoscreen-event-stream.service
  -> surface/fetch_event_stream.py
  -> surface/.env/event_stream.json
  -> /event_stream.json
  -> news ticker and sync freshness ticker

surface/build_photos_json.py
  -> surface/.env/photos.json and surface/.env/public_photos/
  -> /photos.json and /public_photos/*
  -> assets/js/dashboard.js

surface/search_local_events.py
  -> surface/.env/local_event_search_results.json
  -> /api/local-events/search
  -> assets/js/local_event_card.js

surface/.env/market_config.json
  <-> /api/market-config
  -> assets/js/market_custom.js

surface/openapi_spec.py + surface/api_models.py
  -> /openapi.json
  -> /docs
```

The Surface address used by `mac/sync_schedule.sh` is local deployment configuration in `mac/local.env`, not committed source. All runtime JSON targets remain under `surface/.env/`.
