# InfoScreen design

## Runtime ownership

`surface/serve_infoscreen.py` owns HTTP serving and local API endpoints.

Runtime JSON files live under `surface/.env/`.

The detailed Python source map is `surface/README.md`.

## Python files

Entrypoints and API/schema modules:

```text
surface/serve_infoscreen.py       HTTP server and local API
surface/fetch_live_data.py        weather and market refresh
surface/fetch_event_stream.py     event/news stream refresh
surface/build_photos_json.py      photo wall JSON builder
surface/search_local_events.py    local event refresh CLI used by the API
surface/openapi_spec.py           OpenAPI payload builder
surface/api_models.py             OpenAPI/Pydantic schema models
```

Local event implementation package:

```text
surface/local_events_runtime/__init__.py
surface/local_events_runtime/extract.py
surface/local_events_runtime/browser.py
```

## Local event implementation

The canonical local event code path is:

```text
surface/search_local_events.py
  -> surface/local_events_runtime/__init__.py
  -> surface/local_events_runtime/extract.py
  -> surface/local_events_runtime/browser.py
```

`search_local_events.py` writes `surface/.env/local_event_search_results.json`.

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

## Runtime data flow

```text
/schedule.json             -> assets/js/calendar_board.js
/weather.json              -> assets/js/dashboard.js
/market.json               -> assets/js/dashboard.js
/event_stream.json         -> assets/js/dashboard.js
/photos.json               -> assets/js/dashboard.js
/api/local-events/search   -> assets/js/local_event_card.js
```
