# InfoScreen API usage spec

This document describes the HTTP API exposed by the local InfoScreen server and the schema generation rules.

## Runtime model

- Server entrypoint: `surface/serve_infoscreen.py`.
- Server bind address: `0.0.0.0:8765`.
- Static web root: `surface/web/`.
- Runtime JSON root: `surface/.env/`.
- Configuration root: `surface/conf/`.
- Pydantic schema definitions: `surface/api_models.py`.
- OpenAPI generation: `surface/openapi_spec.py`.
- Runtime JSON files are intentionally not source-controlled.
- The server must not read fallback runtime JSON from the repository root.

## Schema and documentation model

InfoScreen does not need to migrate to FastAPI just to get Swagger/OpenAPI.

Current design:

```text
surface/api_models.py      Pydantic request/response/runtime schemas
surface/openapi_spec.py    routes + Pydantic JSON Schema -> OpenAPI 3.1
GET /openapi.json          machine-readable OpenAPI spec
GET /docs                  Swagger UI loading /openapi.json
```

Rules:

- Pydantic owns field names, types, descriptions, and JSON Schema.
- `openapi_spec.py` owns paths, HTTP methods, summaries, request bodies, and response mappings.
- `docs/api-spec.md` is human-readable usage documentation.
- Runtime code should validate or normalize data according to the same schema contract where practical.

Install requirement for OpenAPI generation:

```bash
python3 -m pip install --user 'pydantic>=2.0'
```

Swagger UI itself is served by `/docs` and loads browser assets from a CDN. If the kiosk is offline, `/openapi.json` still works.

## General response rules

- JSON responses use `application/json; charset=utf-8`.
- Static and JSON responses send `Cache-Control: no-store`.
- Runtime JSON endpoints return a missing-runtime object if the backing file does not exist.
- Write endpoints return `{ "ok": true, ... }` on success and `{ "ok": false, "error": "..." }` on failure.
- Failed subprocess endpoints include captured stdout/stderr tails.

## Static and documentation endpoints

### `GET /`

Returns sanitized dashboard HTML.

Implementation note: the served HTML is sanitized by `surface/serve_infoscreen.py` to strip this legacy local-event inline script block before sending HTML to the browser:

```html
<script id="local-event-inline-script">...</script>
```

Only the external `calendar_board.js` local-event renderer should be active in the browser.

### `GET /index.html`

Same behavior as `GET /`.

### `GET /calendar_board.js`

Returns the external JavaScript bundle that owns:

- calendar board rendering from `schedule.json`
- local event card rendering from `/api/local-events/search`
- local event paging/search UI

There must be only one local-event state machine in the browser.

### `GET /openapi.json`

Returns OpenAPI 3.1 JSON generated from:

```text
surface/openapi_spec.py
surface/api_models.py
```

Failure response example if Pydantic is missing or schema generation fails:

```json
{
  "ok": false,
  "error": "openapi_generation_failed: ModuleNotFoundError: No module named 'pydantic'"
}
```

### `GET /docs`

Returns a minimal Swagger UI page that loads:

```text
/openapi.json
```

## Runtime JSON endpoints

The following files are served from `surface/.env/`.

| Endpoint | Backing file | Default if missing | Purpose |
|---|---|---|---|
| `GET /schedule.json` | `surface/.env/schedule.json` | `[]` | calendar board |
| `GET /weather.json` | `surface/.env/weather.json` | `{}` | weather panel |
| `GET /market.json` | `surface/.env/market.json` | `{}` | market panel/ticker |
| `GET /market_config.json` | `surface/.env/market_config.json` | default symbols | market config |
| `GET /event_stream.json` | `surface/.env/event_stream.json` | `{ "items": [] }` | multilingual event/news ticker |
| `GET /photos.json` | `surface/.env/photos.json` | `{ "items": [] }` | photo wall |
| `GET /sync_status.json` | `surface/.env/sync_status.json` | `{}` | sync/runtime state |
| `GET /local_event_search_results.json` | `surface/.env/local_event_search_results.json` | `{ "results": [] }` | local event results |

## API endpoints

### `GET /api/market-config`

Returns active market symbol config.

Resolution order:

1. `surface/.env/market_config.json`
2. `surface/conf/market_config.default.json`
3. hardcoded default symbols

Example response:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

### `POST /api/market-config`

Updates `surface/.env/market_config.json`.

Request body:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT"]
}
```

Validation rules:

- `symbols` must be a list.
- Values are stripped and uppercased.
- Empty values are ignored.
- Duplicates are removed while preserving order.
- At most 12 symbols are stored.
- Empty final symbol list is rejected.

### `POST /api/market-refresh`

Runs:

```bash
python3 surface/fetch_live_data.py
```

Working directory:

```text
surface/
```

Timeout:

```text
60 seconds
```

Response includes:

- `ok`
- `returncode`
- last 2000 characters of stdout
- last 2000 characters of stderr
- current `market.json` runtime payload

### `GET /api/local-events/search`

Returns current runtime payload from:

```text
surface/.env/local_event_search_results.json
```

It does not run a new search.

Expected current extractor after rendered DOM work:

```text
rendered-dom-card-v41
```

### `POST /api/local-events/search`

Runs the local event extractor and then returns the newly written runtime payload.

Request body:

```json
{
  "location": "Punggol Singapore"
}
```

Command executed:

```bash
python3 surface/search_local_events.py "<location>"
```

Working directory:

```text
surface/
```

Timeout:

```text
130 seconds
```

Response includes:

- runtime payload from `local_event_search_results.json`
- `ok` based on subprocess return code
- last 1000 characters of stdout
- last 1000 characters of stderr

## Local event output contract

Each event item should provide:

```json
{
  "title": "required display title",
  "when": "date/date-range substring only",
  "where": "venue or fallback venue",
  "host": "organizer/source display name",
  "source_name": "official source name",
  "url": "https://official.example/detail",
  "summary": "short display summary",
  "start_date": "YYYY-MM-DD when parseable",
  "kind": "event",
  "source_type": "rendered_dom_card"
}
```

Frontend renderability rules:

- `title` must be non-empty.
- `url` must be an HTTP/HTTPS URL.
- `when`, `where`, `summary`, and `source_name` are optional for rendering but should be filled when available.

## Public photo endpoint

### `GET /public_photos/<path>`

Serves files from:

```text
surface/.env/public_photos/<path>
```

### `HEAD /public_photos/<path>`

Returns file metadata if present.

## Error handling requirements

- Do not silently fall back to fake root JSON.
- Do not silently fall back from rendered extraction to the old generic crawler.
- If Playwright or browser runtime is missing, the local event payload/debug should show a clear reason such as `missing_playwright_python_package` or `missing_system_chromium`.
- If OpenAPI generation fails, `/openapi.json` must return an explicit `openapi_generation_failed` error.

## Verification

```bash
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/docs | head
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/ | grep -n "local-event-inline-script" || true
curl -s http://127.0.0.1:8765/calendar_board.js | grep -n "MutationObserver\|watchdog\|external-local-events" || true
```
