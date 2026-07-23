# InfoScreen HTTP interaction contract

This document defines the HTTP boundary between the kiosk frontend, local operator tools, runtime JSON, and producer jobs. Deployment and troubleshooting commands belong in `README.md`; architecture belongs in `docs/design.md`.

## 1. Server boundary

The HTTP owner is:

```text
surface/serve_infoscreen.py
```

The process binds `0.0.0.0:8765`. Local kiosk access normally uses `http://127.0.0.1:8765/`. A second device on the same trusted network uses the Surface LAN address instead. The server has no authentication layer; exposure beyond the trusted local device/network boundary must be controlled outside the application.

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
| `GET`, `HEAD` | `/local-events/studio/` | static server | Local Event operator review page |
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

Invalid input returns HTTP `400`.

Saving configuration does not by itself render quotes. `market_custom.js` follows a successful save by calling the Market refresh endpoint and then `window.loadMarket()`.

## 6. Market and Weather manual refresh

```http
POST /api/market-refresh
```

Request body: none.

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/fetch_live_data.py
  -> surface/.env/weather.json
  -> surface/.env/market.json
```

The subprocess timeout is 60 seconds. HTTP status is `200` when the subprocess exits successfully and `500` otherwise.

## 7. Local Events read and dashboard-filter interaction

```http
GET /api/local-events/search
```

This endpoint does not run a crawl. It returns the current normalized `local_event_search_results.json` payload.

The kiosk Local Events card calls this GET endpoint and keeps the returned rows in browser memory. Its filter dialog:

- builds the institution options from the current rows’ `source_name`, `institution`, or equivalent source field;
- filters by exact selected institution;
- applies all typed terms across title, institution/source, date/time, venue/place, and summary/description;
- stores only the selected browser filter in `localStorage`;
- does not send a POST request, run Chromium, execute a producer, or write runtime JSON.

The periodic GET reload applies the active filter to the newly read payload.

## 8. Explicit Local Events collection interaction

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

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/search_local_events.py <location>
  -> surface/jobs/local_event_search.py
  -> source-specific official collector
  -> surface/.env/local_event_search_results.json
```

The supported wrapper applies `surface/local_events_runtime/http1_browser.py` before importing the collector. Every Chromium instance launched through that path starts with:

```text
--disable-http2
```

There is no HTTP/2-first attempt and no protocol retry loop.

This POST endpoint remains an explicit producer trigger for operator or direct API use. The dashboard institution/keyword filter does not call it.

## 9. Local Event review interaction

The operator page uses local review state under:

```text
surface/.env/local_event_review/state.json
```

### Read review state

```http
GET /api/local-events/review/state
```

The response includes:

```text
sources
listing_pages
events
feedback
listing_collection
event_collection
```

`event_collection.listing_diagnostics` contains per-listing stage counts and a `reason_code` explaining zero-result collections.

### Discover candidate list pages

```http
POST /api/local-events/review/discover-listings
```

This opens configured institution home pages with Playwright and persists candidate list pages. The server applies `--disable-http2` before importing the review collector.

### Add one correct official list page manually

```http
POST /api/local-events/review/listing-page
Content-Type: application/json
```

Request body:

```json
{
  "source_id": "artscience",
  "url": "https://www.marinabaysands.com/museum/whats-on.html"
}
```

Rules:

- `source_id` must identify a configured institution;
- `url` must be absolute HTTP/HTTPS;
- the hostname must match that institution’s `allowed_domains`;
- the page is stored in review state as `pending`;
- adding an existing page resets it to `pending` so it can be reviewed again;
- the operation does not write committed `event_sources.json`;
- the operation does not collect Events automatically;
- the operator must preview and confirm the page before normal confirmed-page collection.

Success returns the updated review state. Invalid institution or domain returns HTTP `400` with `manual_listing_page_failed`.

### Save list-page decisions

```http
POST /api/local-events/review/listing-decision
Content-Type: application/json
```

```json
{
  "candidate_id": "<candidate-id>",
  "decision": "pending | confirmed | rejected"
}
```

### Collect Event candidates

```http
POST /api/local-events/review/collect-events
```

The collector reads pages currently marked `confirmed`, identifies isolated official detail links, records DOM selectors and page positions, and then opens detail pages for title, date/time, venue, and detail diagnostics. A date is not required on the listing card itself. Chromium is forced to start with `--disable-http2` before collection begins.

### Save Event review decisions

```http
POST /api/local-events/review/event-decision
Content-Type: application/json
```

```json
{
  "candidate_id": "<candidate-id>",
  "decision": "pending | confirmed | rejected"
}
```

### Interactive browser feedback status

The downloadable Chrome Helper, extension files, ZIP generation, and remote `feedback:` transport were removed. The operator page does not expose a replacement interactive browser-feedback action in this branch. `/api/local-events/review/open-feedback` is not part of the active API contract.

## 10. Browser interaction summary

| UI action | HTTP interaction | Server side effect | Final browser action |
| --- | --- | --- | --- |
| Open page | `GET /`, then runtime GETs | None | Render current runtime state |
| Market `SAVE` | `POST /api/market-config`, then `POST /api/market-refresh` | Write config; run live-data producer | Reload Market |
| Market `REFRESH` | `POST /api/market-refresh` | Run live-data producer | Reload Market |
| Local Event dashboard filter | Existing `GET /api/local-events/search` payload only | None | Filter rows by institution and text in browser memory |
| Explicit Local Event collection | `POST /api/local-events/search` | Run source-specific collector with HTTP/2 disabled | Return and render refreshed runtime results to the direct caller |
| Review page load or return to tab | `GET /api/local-events/review/state` | None | Render review state once |
| Add list page | `POST /api/local-events/review/listing-page` | Persist one pending page for the selected institution | Reload left-side list cards |
| Review list/Event decision | Review decision POST | Persist review state | Refresh affected cards |
| Review Event collection | `POST /api/local-events/review/collect-events` | Persist Events and diagnostics | Render Event candidates and exact zero-result reason |
| Sync observation | `HEAD` four runtime paths | None | Compute `AGE` and status |

## 11. Endpoints that are intentionally not mutation APIs

There is no HTTP endpoint to:

- edit Calendar accounts or schedule events;
- add a new institution or change its allowed domains;
- change systemd timer frequency;
- upload or delete private photos;
- edit News feed configuration;
- change Weather coordinates.

The manual listing endpoint adds a review-state candidate only. It does not alter committed institution source configuration.
