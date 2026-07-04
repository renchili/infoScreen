# InfoScreen design

## Runtime ownership

`surface/serve_infoscreen.py` owns HTTP serving and local API endpoints.

Runtime JSON files live under `surface/.env/`.

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
compact ‹ / › / ⌕ controls
EVENT / WHEN / WHERE / HOST fields
official link action at the card bottom
```

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
