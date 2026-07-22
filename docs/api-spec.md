# InfoScreen HTTP interaction contract

This document defines the HTTP boundary between the kiosk frontend, local operator tools, runtime JSON, and producer jobs. Deployment and troubleshooting commands belong in `README.md`; architecture belongs in `docs/design.md`.

## 1. Server boundary

The HTTP owner is:

```text
surface/serve_infoscreen.py
```

The process binds `0.0.0.0:8765`. Local kiosk access normally uses `http://127.0.0.1:8765/`. A second trusted LAN device uses the Surface LAN address. The server has no application authentication layer; exposure beyond the trusted local network must be controlled outside the application.

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

Static assets are served from `surface/web/` through `SimpleHTTPRequestHandler`.

## 3. Runtime JSON reads

| Method | Path | Runtime file | Primary caller | Producer |
| --- | --- | --- | --- | --- |
| `GET`, `HEAD` | `/schedule.json` | `schedule.json` | Calendar board, Sync ticker | Mac EventKit export and SCP push |
| `GET`, `HEAD` | `/weather.json` | `weather.json` | Dashboard, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market.json` | `market.json` | Dashboard, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market_config.json` | `market_config.json` | Operator or debug read | Market config API |
| `GET`, `HEAD` | `/event_stream.json` | `event_stream.json` | News card, Sync ticker | `fetch_event_stream.py` |
| `GET`, `HEAD` | `/local_event_search_results.json` | `local_event_search_results.json` | Direct operator or debug read | Local Event producer plus Review overlay |
| `GET`, `HEAD` | `/photos.json` | `photos.json` | Photo wall | Photo builder |
| `GET`, `HEAD` | `/sync_status.json` | `sync_status.json` | Reserved or direct read | No active producer documented |

### Missing runtime behaviour

For `GET`, a missing runtime file returns the endpoint default shape plus:

```json
{
  "ok": false,
  "error": "missing_runtime_json",
  "expected_path": "/absolute/path/to/the/runtime/file"
}
```

For `HEAD`, a missing runtime file returns HTTP `404`.

### HEAD freshness contract

For an existing runtime file, `HEAD` returns JSON content headers and `Last-Modified`. The Sync ticker uses `Last-Modified`; it does not depend on a JSON `updated_at` field.

## 4. Public photo reads

| Method | Path | Filesystem mapping | Caller |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/public_photos/<relative-path>` | `surface/.env/public_photos/<relative-path>` | Photo wall |

The photo builder controls which files enter the public runtime directory. The browser does not receive arbitrary filesystem access.

## 5. Market configuration

### Read active symbols

```http
GET /api/market-config
```

Resolution order:

1. `surface/.env/market_config.json`;
2. `surface/conf/market_config.default.json`;
3. built-in defaults.

### Save active symbols

```http
POST /api/market-config
Content-Type: application/json
```

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

Values are trimmed and uppercased, duplicates are removed in order, at most 12 symbols are stored, and an empty final list is rejected. Success writes `surface/.env/market_config.json` with `updated_at`. Invalid input returns HTTP `400`.

## 6. Market and Weather manual refresh

```http
POST /api/market-refresh
```

Side effect:

```text
serve_infoscreen.py
  -> python surface/fetch_live_data.py
  -> weather.json
  -> market.json
```

HTTP status is `200` when the subprocess exits successfully and `500` otherwise.

## 7. Local Events read interaction

```http
GET /api/local-events/search
```

This endpoint does not run a crawl. It returns the current `local_event_search_results.json` payload.

The final `results` list contains:

- normalized automatically collected producer rows;
- current operator-confirmed Review rows that are not already represented by the producer result.

## 8. Local Events producer interaction

```http
POST /api/local-events/search
Content-Type: application/json
```

```json
{
  "location": "Punggol Singapore"
}
```

Side effect:

```text
serve_infoscreen.py
  -> python surface/search_local_events.py <location>
  -> surface/jobs/local_event_search.py
  -> complete official-source collector
  -> normalize new producer rows
  -> partial-result protection
  -> overlay current confirmed Review Events
  -> local_event_search_results.json
```

When the run is incomplete, the collector also writes:

```text
surface/.env/local_event_search_results.partial.json
```

A smaller partial run cannot delete protected verified producer rows. Review rows are overlaid after either a new collector result or a protected previous result.

The deployed HTTP service sets `LOCAL_EVENT_SEARCH_TIMEOUT_SECONDS=7500`, which is longer than the complete producer budget. The endpoint remains synchronous and returns after the producer exits or the HTTP subprocess timeout is reached.

The supported wrapper applies `surface/local_events_runtime/http1_browser.py`. That bootstrap applies complete collection authority and launches Chromium with `--disable-http2`.

## 9. Local Event review interaction

Review state is stored under:

```text
surface/.env/local_event_review/state.json
```

### Read review state

```http
GET /api/local-events/review/state
```

The response includes source inventory, list-page candidates, Event candidates, feedback, and collection metadata.

### Discover candidate list pages

```http
POST /api/local-events/review/discover-listings
```

The server opens configured official home pages and persists discovered list-page candidates.

### Add one official list page manually

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

- `source_id` identifies a configured institution;
- `url` is absolute HTTP or HTTPS;
- hostname matches the institution `allowed_domains`;
- the candidate is stored as `pending`;
- adding an existing institution and URL resets it to `pending`;
- committed `event_sources.json` is not changed;
- Events are not collected automatically.

Invalid input returns HTTP `400` with `manual_listing_page_failed`.

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

This changes Review state only. A confirmed page becomes eligible for explicit Event candidate collection.

### Collect Event candidates

```http
POST /api/local-events/review/collect-events
```

The collector reads list pages marked `confirmed`, records rendered card and DOM evidence, follows official detail pages when present, and keeps complete listing-only cards when no detail page exists. The result is saved to Review state; this operation does not replace the producer result.

### Save Event decisions

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

Side effects:

1. save the decision in `local_event_review/state.json`;
2. read the current `local_event_search_results.json`;
3. preserve all rows not created by Review publication;
4. rebuild the complete current set of `confirmed` Review rows;
5. skip a confirmed row already represented by the producer result;
6. atomically write the combined primary runtime.

A `confirmed` decision is authoritative for activity membership. Publication does not run crawler admission again. Missing date, venue, summary, or independent detail page does not remove the confirmed candidate. Listing-only candidates use their official list URL.

Changing a candidate to `rejected` or `pending` removes only its Review-published row. Automatically collected rows remain unchanged.

## 10. Local Events runtime fields

Producer and Review rows carry `candidate_policy: official-listing-authority-v1`.

Review-published rows additionally carry:

```text
operator_review_decision: confirmed
review_publish_origin: review_state
review_candidate_id: <candidate-id>
```

The primary payload includes `review_publish` metadata with confirmed count, added count, already-present count, publication mode, and Review state path.

Producer completion metadata includes per-source status, completed and incomplete source counts, and `partial`.

## 11. Interactive browser feedback status

The downloadable helper, extension files, ZIP generation, and remote `feedback:` transport are not active API features. `/api/local-events/review/open-feedback` is not part of the supported contract.

## 12. Browser interaction summary

| UI action | HTTP interaction | Server side effect | Browser action |
| --- | --- | --- | --- |
| Open kiosk | `GET /` plus runtime reads | None | Render current runtime |
| Reload Local Events data | `GET /api/local-events/search` | None | Preserve current card when data changed; avoid redraw when unchanged |
| Search Local Events | `POST /api/local-events/search` | Run complete producer and write combined runtime | Render returned result |
| Open Studio | `GET /local-events/studio/`, `GET /api/local-events/review/state` | None | Render Review state |
| Confirm Event | `POST /api/local-events/review/event-decision` | Save state and overlay confirmed rows into primary runtime | Refresh Review state; kiosk polling observes new runtime |
