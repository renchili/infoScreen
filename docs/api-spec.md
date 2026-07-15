# InfoScreen HTTP interaction contract

This document defines the HTTP boundary between the kiosk frontend, local operator tools, runtime JSON, and producer jobs. Deployment and troubleshooting commands belong in `README.md`; architecture belongs in `docs/design.md`.

## 1. Server boundary

The HTTP owner is:

```text
surface/serve_infoscreen.py
```

The process binds `0.0.0.0:8765`. Local kiosk access normally uses `http://127.0.0.1:8765/`. The server has no authentication layer and is intended for a trusted local device/network; exposure beyond that boundary must be controlled outside the application.

Runtime files are read from:

```text
${INFOSCREEN_ENV_DIR:-surface/.env}
```

All responses add:

```text
Cache-Control: no-store
```

## 2. Static pages and generated API documentation

| Method | Path | Owner | Response |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/` | `serve_infoscreen.py` | `surface/web/index.html` |
| `GET`, `HEAD` | `/index.html` | `serve_infoscreen.py` | `surface/web/index.html` |
| `GET`, `HEAD` | `/docs` | `serve_infoscreen.py` | Swagger UI wrapper |
| `GET`, `HEAD` | `/openapi.json` | `serve_infoscreen.py`, `openapi_spec.py`, `api_models.py` | Generated OpenAPI JSON |

Static frontend assets are served from `surface/web/` through `SimpleHTTPRequestHandler`.

## 3. Runtime JSON reads

| Method | Path | Runtime file | Primary caller | Producer |
| --- | --- | --- | --- | --- |
| `GET`, `HEAD` | `/schedule.json` | `schedule.json` | `calendar_board.js`, Sync ticker | Mac EventKit export and SCP push |
| `GET`, `HEAD` | `/weather.json` | `weather.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market.json` | `market.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market_config.json` | `market_config.json` | Direct operator/debug read | Market config API |
| `GET`, `HEAD` | `/event_stream.json` | `event_stream.json` | `local_event_card.js`, Sync ticker | `fetch_event_stream.py` |
| `GET`, `HEAD` | `/local_event_search_results.json` | `local_event_search_results.json` | Direct operator/debug read | Local-event job |
| `GET`, `HEAD` | `/photos.json` | `photos.json` | `local_event_card.js` | Photo builder |
| `GET`, `HEAD` | `/sync_status.json` | `sync_status.json` | Reserved/direct read | No active producer documented |

### Missing runtime behaviour

For `GET`, when the runtime file does not exist, the server returns the endpoint’s default JSON shape plus:

```json
{
  "ok": false,
  "error": "missing_runtime_json",
  "expected_path": "/absolute/path/to/the/runtime/file"
}
```

For `HEAD`, a missing runtime file returns HTTP `404`.

### HEAD freshness contract

For an existing runtime file, `HEAD` returns:

```text
Content-Type: application/json; charset=utf-8
Content-Length: <file size>
Last-Modified: <file mtime as HTTP date>
```

The Sync ticker uses `Last-Modified`; it does not parse JSON `updated_at` fields.

## 4. Public photo reads

| Method | Path | Filesystem mapping | Caller |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/public_photos/<relative-path>` | `surface/.env/public_photos/<relative-path>` | Photo wall |

The photo builder controls which files are copied into the public runtime directory. The browser does not receive arbitrary filesystem access.

## 5. Market configuration interaction

### Read active symbols

```http
GET /api/market-config
```

Caller:

```text
surface/web/assets/js/market_custom.js
```

Resolution order:

1. `surface/.env/market_config.json` when present;
2. `surface/conf/market_config.default.json`;
3. built-in default symbols.

Example response:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

### Save active symbols

```http
POST /api/market-config
Content-Type: application/json
```

Canonical request body:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

Server behaviour:

- input must be a JSON list;
- values are trimmed and uppercased;
- duplicates are removed while preserving order;
- at most 12 symbols are stored;
- an empty final list is rejected;
- success writes `surface/.env/market_config.json` with `updated_at`.

Success response:

```json
{
  "ok": true,
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"],
  "updated_at": "<UTC ISO timestamp>"
}
```

Invalid input returns HTTP `400` with:

```json
{
  "ok": false,
  "error": "<validation message>"
}
```

Saving configuration does not by itself render quotes. `market_custom.js` follows a successful save by calling the Market refresh endpoint and then `window.loadMarket()`.

## 6. Market and Weather manual refresh

```http
POST /api/market-refresh
```

Request body: none.

Caller:

```text
market_custom.js REFRESH action
market_custom.js SAVE action after config is written
```

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/fetch_live_data.py
  -> surface/.env/weather.json
  -> surface/.env/market.json
```

The subprocess timeout is 60 seconds.

Success/failure response includes:

```json
{
  "ok": true,
  "returncode": 0,
  "stdout": "<last output>",
  "stderr": "<last error output>",
  "market": {},
  "weather": {}
}
```

HTTP status is `200` when the subprocess exits successfully and `500` otherwise. Because Weather and Market share one producer, a manual Market refresh refreshes both runtime files.

## 7. Local Events read interaction

```http
GET /api/local-events/search
```

This endpoint does not run a crawl. It returns the current normalized `local_event_search_results.json` payload.

Primary caller:

```text
local_event_card.js on page load
```

The server normalizes text fields before returning the payload so API and page consumers receive the same plain-text representation.

## 8. Local Events search interaction

```http
POST /api/local-events/search
Content-Type: application/json
```

Canonical request body:

```json
{
  "location": "Punggol Singapore"
}
```

Primary caller:

```text
local_event_card.js location-search modal
```

The current server reads `location`; absent or empty input defaults to `Punggol Singapore`.

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/search_local_events.py <location>
  -> surface/jobs/local_event_search.py
  -> source-specific official collector
  -> surface/.env/local_event_search_results.json
  -> optional surface/.env/local_event_search_results.partial.json
  -> debug evidence under surface/.env/local_event_debug_cards/
```

The HTTP subprocess timeout is 330 seconds. The job itself has a larger default total budget; therefore the HTTP on-demand path may terminate earlier than a direct systemd/manual producer run when sources are slow.

The response is the normalized runtime payload plus:

```json
{
  "ok": true,
  "stdout": "<last producer output>",
  "stderr": "<last producer error output>"
}
```

HTTP status is `200` for a successful subprocess and `500` otherwise.

Important response fields include:

```text
results
sources
debug_by_source
partial
write_policy
previous_count
extractor
version
text_normalizer
```

The frontend displays only accepted `results`. `debug_by_source` is operator/developer evidence and is not rendered as event cards.

## 9. Browser interaction summary

| UI action | HTTP interaction | Server side effect | Final browser action |
| --- | --- | --- | --- |
| Open page | `GET /`, then runtime GETs | None | Render current runtime state |
| Market gear opens | `GET /api/market-config` | None | Populate symbol input |
| Market `SAVE` | `POST /api/market-config`, then `POST /api/market-refresh` | Write config; run live-data producer | Call `window.loadMarket()` |
| Market `REFRESH` | `POST /api/market-refresh` | Run live-data producer | Call `window.loadMarket()` |
| Local Event page load | `GET /api/local-events/search` | None | Render current accepted results |
| Local Event location search | `POST /api/local-events/search` | Run source-specific collector | Store location in browser local storage and render returned results |
| Sync observation | `HEAD` four runtime paths | None | Compute `AGE` and status |
| News reload | `GET /event_stream.json` | None | Rebuild three ticker rows |
| Photo reload | `GET /photos.json`, then image GETs | None | Rebuild and rotate the photo wall |
| Calendar load | `GET /schedule.json` | None | Build and rotate the Calendar board |

## 10. Endpoints that are intentionally not mutation APIs

There is no HTTP endpoint to:

- edit Calendar accounts or schedule events;
- change Local Events official source configuration;
- change systemd timer frequency;
- upload or delete private photos;
- edit News feed configuration;
- change Weather coordinates.

Those concerns remain Mac configuration, committed source/configuration, or local filesystem operations. This keeps the local API small and prevents the kiosk page from becoming an unrestricted administration interface.
