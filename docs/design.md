# InfoScreen design

## Runtime ownership

`surface/serve_infoscreen.py` owns HTTP serving and local API endpoints.

Runtime JSON files live under `surface/.env/`.

## Repository root policy

The repository root is reserved for control files and documentation. Dashboard runtime JSON, browser CSS, and browser JavaScript must not live in the repository root.

Allowed root-level project files are limited to control and documentation files such as:

```text
README.md
AGENTS.md
AGENT.md
.gitignore
docs/
surface/
```

Runtime JSON belongs under `surface/.env/`. Browser CSS and JavaScript belong under `surface/web/assets/`. Legacy static files directly under `surface/web/*.js` or `surface/web/*.css` are not active source paths and should be removed instead of replaced with placeholders.

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
counter aligned with ‹ / › / ⌕ controls on the right
source or organization at the card top-left
no standalone EVENT label
compact WHEN and WHERE rows
official link immediately after content, not pushed to the panel bottom
```

Local event content must remain visible below the toolbar when `/api/local-events/search` has results. The CSS must not hide, absolutely overlap, grid-collapse, nest excessive padded boxes, or stretch the card to waste the full panel height.

## Sync ticker contract

The left sync ticker is a freshness indicator, not only a count indicator.

It must check runtime file freshness through `HEAD` requests and the `Last-Modified` header.

The ticker must show:

```text
SCHEDULE / WEATHER / MARKET / NEWS
OK / STALE / MISS / ERR
LATEST
AGE
```

## Photo wall contract

Preferred user photo directory:

```text
photos/
```

Supported compatibility directories:

```text
photo/
surface/.env/photos/
```

`surface/build_photos_json.py` reads those photo source directories, converts or copies images into `surface/.env/public_photos/`, and writes `surface/.env/photos.json`.

The browser does not scan the filesystem directly. After adding images, the builder must run before the dashboard can display them.

## Market UI contract

The visible kiosk market card must show market rows by default and must not inject an always-visible inline symbol editor that shifts or compresses the rows.

`surface/web/assets/js/market_custom.js` owns a compact config button. Clicking that button may open a temporary editor overlay. Symbol management stays behind the existing HTTP APIs:

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
/schedule.json             -> assets/js/calendar_board.js and sync freshness ticker
/weather.json              -> assets/js/dashboard.js and sync freshness ticker
/market.json               -> assets/js/dashboard.js and sync freshness ticker
/event_stream.json         -> assets/js/dashboard.js and sync freshness ticker
/photos.json               -> assets/js/dashboard.js
/api/local-events/search   -> assets/js/local_event_card.js
/openapi.json              -> openapi_spec.py + api_models.py
/docs                      -> Swagger UI for /openapi.json
```
