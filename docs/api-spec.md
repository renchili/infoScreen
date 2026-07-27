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
| `GET`, `HEAD` | `/schedule.json` | `schedule.json` | `calendar_board.js`, Sync ticker | Mac EventKit export and atomic remote publish |
| `GET`, `HEAD` | `/weather.json` | `weather.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market.json` | `market.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market_config.json` | `market_config.json` | Direct operator/debug read | Market config API |
| `GET`, `HEAD` | `/event_stream.json` | `event_stream.json` | `local_event_card.js`, Sync ticker | `fetch_event_stream.py` |
| `GET`, `HEAD` | `/local_event_search_results.json` | `local_event_search_results.json` | Direct operator/debug read | Local-event collector plus Review projection |
| `GET`, `HEAD` | `/photos.json` | `photos.json` | `local_event_card.js` | Photo builder |
| `GET`, `HEAD` | `/sync_status.json` | `sync_status.json` | Reserved/direct read | No active producer documented |

`local_event_collector_results.json` is an internal producer snapshot under the runtime directory. It is not the kiosk API response. `local_event_search_results.json` is the public projection created from that collector snapshot plus current Review decisions.

### Missing runtime behaviour

For `GET`, when a runtime file does not exist, the server returns HTTP `200` with the endpoint’s default JSON shape plus:

```json
{
  "ok": false,
  "error": "missing_runtime_json",
  "expected_path": "/absolute/path/to/the/runtime/file"
}
```

The generated OpenAPI schema models the successful and missing-runtime shapes as alternatives under the `200` response. For `HEAD`, a missing runtime file returns HTTP `404`.

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
| `GET`, `HEAD` | `/public_photos/<relative-path>` | confined regular file below `surface/.env/public_photos/` | Photo wall |

The server rejects absolute paths, dot segments, repeated separators, encoded traversal, null bytes, and symlink escape. The photo builder controls which files are copied into the public runtime directory. The browser does not receive arbitrary filesystem access.

The public `photos.json` manifest contains browser URLs, captions, and output types only. It does not expose the original absolute source directory or source-file path.

## 5. Market configuration interaction

### Read active symbols

```http
GET /api/market-config
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

Invalid input returns HTTP `400`. `market_custom.js` follows a successful save by calling the Market refresh endpoint and then `window.loadMarket()`.

## 6. Market and Weather manual refresh

```http
POST /api/market-refresh
```

Request body: none.

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/fetch_live_data.py
  -> atomic replace: surface/.env/weather.json
  -> atomic replace: surface/.env/market.json
```

The subprocess timeout is 60 seconds. HTTP status is `200` when the subprocess exits successfully and `500` otherwise.

The response includes both producer outputs:

```json
{
  "ok": true,
  "returncode": 0,
  "stdout": "...",
  "stderr": "",
  "market": {},
  "weather": {}
}
```

A non-zero producer exit may return the same response shape with `ok: false`; a failure before the subprocess result is available may return the generic error shape. OpenAPI models both alternatives for HTTP `500`.

## 7. Local Events read and dashboard-filter interaction

```http
GET /api/local-events/search
```

This endpoint does not run a crawl. It returns the current normalized `local_event_search_results.json` projection. Missing runtime data is returned as an HTTP `200` missing-runtime/default JSON shape.

The kiosk Local Events card calls this GET endpoint and keeps the returned rows in browser memory. Its filter dialog:

- builds institution options from current rows;
- filters by exact selected institution;
- applies all typed terms across title, institution/source, date/time, venue/place, and summary/description;
- stores only browser filter choices in `localStorage`;
- does not send a POST request, run Chromium, execute a producer, or write runtime JSON.

The periodic GET reload applies the active filter to the newly read payload.

Review projection rules are:

- a confirmed candidate with the same canonical detail URL replaces non-empty title/date/venue/summary fields on the collector row;
- collector ordering and evidence fields remain on the projected row;
- a confirmed candidate without a collector match is appended;
- a rejected candidate suppresses its matching collector row;
- a pending/reset candidate leaves or restores the collector row.

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
  -> surface/.env/local_event_collector_results.json
  -> Review-state projection
  -> surface/.env/local_event_search_results.json
```

The supported wrapper applies `surface/local_events_runtime/http1_browser.py` before importing the collector. Every Chromium instance launched through that path starts with:

```text
--disable-http2
```

There is no HTTP/2-first attempt and no protocol retry loop.

This endpoint is an explicit producer trigger for operator or direct API use. The dashboard institution/keyword filter does not call it.

A smaller incomplete collection is written to `local_event_search_results.partial.json` and cannot replace a larger verified collector snapshot. Source completion states determine partial coverage; the number of debug rows does not determine completion. When the previous collector snapshot is retained, the kiosk primary is still rebuilt with current Review decisions.

Responses:

- HTTP `200`: collection completed within the HTTP budget;
- HTTP `500`: producer returned failure or could not start;
- HTTP `504`: producer exceeded the HTTP timeout; the response retains the normalized Local Events shape and timeout diagnostics.

## 9. Local Event review interaction

The operator page uses local review state under:

```text
surface/.env/local_event_review/state.json
```

### Read review state

```http
GET /api/local-events/review/state
```

The response includes sources, list-page candidates, Event candidates, feedback records, list collection metadata, Event collection metadata, and per-listing diagnostics.

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
- adding an existing page resets it to `pending`;
- the operation does not edit committed `event_sources.json`;
- the operation does not collect Events automatically;
- the saved page may be previewed while `pending`, `confirmed`, or `rejected`;
- only normal persisted collection requires the page to be `confirmed`.

Invalid institution, URL, or domain returns HTTP `400` without changing review state.

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

### Preview one saved list page without changing its decision

```http
POST /api/local-events/review/preview-events
Content-Type: application/json
```

```json
{
  "listing_url": "https://official.example/events"
}
```

The requested URL must already exist in Review state. Its current decision may be `pending`, `confirmed`, or `rejected`.

Preview is isolated:

```text
load real Review state
  -> deep-copy state
  -> keep only the selected list page
  -> mark only the temporary copy confirmed
  -> clear copied Event candidates, feedback, and Event collection metadata
  -> save the copy under a temporary Review root
  -> run the same final Event collector and detail owner
  -> return the temporary result
  -> delete the temporary root
```

Preview does not call the list-decision endpoint and does not change:

- the selected page’s persisted decision;
- unrelated page decisions;
- persisted Event candidates or Event decisions;
- submitted feedback;
- persisted collection metadata;
- `surface/.env/local_event_review/state.json`;
- the kiosk projection.

The Studio stores the returned display rows in `sessionStorage` only so the preview remains visible during the browser session. A missing or unknown `listing_url` returns HTTP `400`; collection failure returns HTTP `500`.

### Collect Event candidates from confirmed pages

```http
POST /api/local-events/review/collect-events
```

The collector reads all pages currently marked `confirmed`, identifies isolated official detail links, records DOM selectors and page positions, and opens detail pages for title, date/time, venue, and diagnostics. A date is not required on the listing card itself.

This is the persisted collection path. It replaces Review Event candidates and Event collection metadata while preserving matching Event decisions. It never changes list-page decisions.

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

Success persists `local_event_review/state.json` and atomically rebuilds `local_event_search_results.json` from `local_event_collector_results.json` plus the updated decisions. It does not start a new collection.

```text
confirmed -> replace matching collector fields or append a Review-only row
rejected  -> suppress a matching collector row
pending   -> leave or restore the collector row
```

Empty Review date, venue, or summary fields do not erase a non-empty collector field. A non-empty Review date replaces the complete `when/start_date/end_date` tuple so stale range endpoints cannot remain.

### Interactive browser feedback status

The downloadable Chrome Helper, extension files, ZIP generation, and remote `feedback:` transport were removed. The operator page does not expose a replacement interactive browser-feedback action. `/api/local-events/review/open-feedback` is not part of the active API contract.

## 10. Browser interaction summary

| UI action | HTTP interaction | Server side effect | Final browser action |
| --- | --- | --- | --- |
| Open page | `GET /`, then runtime GETs | None | Render current runtime state |
| Market `SAVE` | `POST /api/market-config`, then `POST /api/market-refresh` | Write config; run live-data producer | Reload Market and Weather runtime data |
| Market `REFRESH` | `POST /api/market-refresh` | Run live-data producer | Reload Market and Weather runtime data |
| Local Event dashboard filter | Existing `GET /api/local-events/search` payload only | None | Filter rows in browser memory |
| Explicit Local Event collection | `POST /api/local-events/search` | Run source-specific collector, write collector snapshot, project Review state | Return refreshed kiosk primary |
| Review page load or return to tab | `GET /api/local-events/review/state` | None | Render once, then restore card anchor or scroll position |
| Add list page | `POST /api/local-events/review/listing-page` | Persist one pending page | Reload list cards |
| Review list decision | `POST /api/local-events/review/listing-decision` | Persist decision | Refresh Review cards |
| Preview any saved list page | `POST /api/local-events/review/preview-events` | Collect one temporary isolated copy; no persisted mutation | Display candidates for selected URL |
| Collect confirmed list pages | `POST /api/local-events/review/collect-events` | Persist Event candidates and diagnostics from all confirmed pages | Refresh Review cards |
| Review Event decision | `POST /api/local-events/review/event-decision` | Persist decision and rebuild kiosk primary | Refresh Review cards |
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
