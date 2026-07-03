# Surface app

This directory is the Surface / Ubuntu runtime app.

## Python source map

### HTTP server

```text
serve_infoscreen.py
```

Purpose: local HTTP server on port 8765.

Owns:
- dashboard HTML: `/`, `/index.html`
- runtime JSON reads: `/schedule.json`, `/weather.json`, `/market.json`, `/event_stream.json`, `/photos.json`, `/sync_status.json`
- market config API: `/api/market-config`
- market refresh API: `/api/market-refresh`
- local event API: `/api/local-events/search`
- API docs: `/docs`, `/openapi.json`
- public photo files: `/public_photos/...`

Calls:
- `fetch_live_data.py` for market/weather refresh
- `search_local_events.py` for local event refresh
- `openapi_spec.py` for OpenAPI JSON

### API schema modules

```text
api_models.py
openapi_spec.py
```

Purpose: schema and OpenAPI documentation for the HTTP server.

- `api_models.py` defines Pydantic response/request models.
- `openapi_spec.py` builds `/openapi.json` from those models.

These files do not fetch data and do not write runtime JSON.

### Data refresh scripts

```text
fetch_live_data.py
fetch_event_stream.py
build_photos_json.py
search_local_events.py
```

Purpose: write runtime JSON under `surface/.env/`.

| File | Input | Output | Called by |
|---|---|---|---|
| `fetch_live_data.py` | `conf/market_config.default.json`, `.env/market_config.json`, external weather/market providers | `.env/weather.json`, `.env/market.json` | manual, timers, `POST /api/market-refresh` |
| `fetch_event_stream.py` | RSS feeds and translation endpoint | `.env/event_stream.json` | manual or timer |
| `build_photos_json.py` | `.env/photos/` | `.env/public_photos/`, `.env/photos.json` | manual or timer |
| `search_local_events.py` | `conf/event_sources.json`, location string | `.env/local_event_search_results.json` | manual, `POST /api/local-events/search` |

### Local event package

```text
local_events_runtime/__init__.py
local_events_runtime/browser.py
local_events_runtime/extract.py
```

Purpose: the only active local event implementation package.

Call chain:

```text
search_local_events.py
  -> local_events_runtime.collect_events
  -> local_events_runtime.extract.collect_events
  -> local_events_runtime.browser.render_listing_cards
```

`browser.py` owns Playwright/browser rendering helpers.
`extract.py` owns extraction, scoring, filtering, and output shaping.
`__init__.py` applies the wrapper used by `search_local_events.py`.

### Config files

```text
conf/event_sources.json
conf/market_config.default.json
conf/official_source_registry.json
```

Purpose:
- `event_sources.json`: active official listing entrypoints for local events.
- `market_config.default.json`: default stock symbols.
- `official_source_registry.json`: official source identity registry. It is not the active crawler entrypoint list.

## Non-source runtime files

Runtime files belong under:

```text
surface/.env/
```

They are generated/local state and should not be committed.

## Rule for new Python files

Do not add another root-level local-event engine or adapter. Local event code belongs in `local_events_runtime/`, and the public CLI remains `search_local_events.py` unless the design is intentionally changed in `docs/design.md` and this file together.
