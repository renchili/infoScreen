# InfoScreen API interaction spec

This document is the human-readable API interaction contract for the local InfoScreen HTTP server.

The implementation entrypoint is:

```text
surface/serve_infoscreen.py
```

Default local URL:

```text
http://127.0.0.1:8765
```

## Scope

This file documents HTTP interactions only:

```text
1. static dashboard routes
2. runtime JSON routes
3. API routes
4. request/response examples
5. verification commands
```

Repository structure rules belong in `docs/project-structure.md`. Overall architecture belongs in `docs/design.md`. Implementation problems and resolution notes belong in `docs/questions.md`.

## General behavior

Expected server behavior:

```text
Content-Type for JSON: application/json; charset=utf-8
Cache-Control: no-store
Static root: surface/web/
API server: Python standard-library HTTP server
```

The server must not silently invent or fake runtime data. Missing runtime data should be explicit in the response or visible from the backing file state.

## Runtime-path rule

The currently verified calendar runtime target is:

```text
~/infoscreen/schedule.json
```

Do not change this path in docs or Mac sync scripts unless the running Surface server is verified to read a different path.

Verification:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
head -n 20 /tmp/served_schedule.json
```

Other runtime files may be under `surface/.env/` depending on endpoint implementation. If a path matters for a change, verify it with `curl`, `sha256sum`, `stat`, or `systemctl cat` before editing code or documentation.

## Static routes

### `GET /`

Returns the dashboard HTML.

Expected use:

```bash
curl -i http://127.0.0.1:8765/
```

The server should serve source HTML and static assets. It should not inject CSS, replace script URLs, or patch HTML at runtime as a long-term solution.

### `GET /index.html`

Same intended behavior as `GET /`.

### Static assets

Canonical checked-in static assets should be referenced from:

```text
/assets/css/... via surface/web/assets/css/...
/assets/js/...  via surface/web/assets/js/...
```

The desired source references in `surface/web/index.html` are:

```html
<link rel="stylesheet" href="assets/css/app.css">
<link rel="stylesheet" href="assets/css/calendar_board.css">
<link rel="stylesheet" href="assets/css/local_events.css">
<link rel="stylesheet" href="assets/css/market_custom.css">

<script src="assets/js/calendar_board.js"></script>
<script src="assets/js/local_events.js"></script>
<script src="assets/js/market_custom.js"></script>
```

Root-level or `surface/web/` duplicate CSS/JS files are cleanup debt, not a desired API/static contract.

## Runtime JSON routes

### `GET /schedule.json`

Returns calendar/schedule rows for the calendar board.

Current verified target file:

```text
~/infoscreen/schedule.json
```

Expected item shape:

```json
[
  {
    "time": "09:30",
    "text": "Example meeting"
  }
]
```

Verification:

```bash
curl -s http://127.0.0.1:8765/schedule.json | python3 -m json.tool | head -n 40
```

### `GET /weather.json`

Returns weather runtime data.

Expected fields may include:

```json
{
  "updated_at": "2026-06-30T00:00:00+00:00",
  "location": "Singapore",
  "source": "open-meteo",
  "status": "OK",
  "temp_c": 30.0,
  "feels_like_c": 35.0,
  "humidity": 80,
  "desc": "partly cloudy"
}
```

### `GET /market.json`

Returns market watchlist quote data.

Expected fields may include:

```json
{
  "updated_at": "2026-06-30T00:00:00+00:00",
  "source": "nasdaq+cnbc+stooq+yahoo",
  "status": "OK",
  "symbols": ["AAPL", "NVDA"],
  "items": [
    {
      "symbol": "AAPL",
      "price": "200.00",
      "percent": "+1.23%",
      "session": "NSDQ"
    }
  ]
}
```

### `GET /event_stream.json`

Returns event/news ticker data.

Expected grouped form:

```json
{
  "items_by_lang": {
    "en": [],
    "fr": [],
    "zh": []
  }
}
```

### `GET /local_event_search_results.json`

Returns the latest local official event search result payload if the server exposes it as a runtime JSON route.

The API route `GET /api/local-events/search` is preferred for browser use.

### `GET /photos.json`

Returns photo wall metadata if photo wall generation is enabled.

### `GET /sync_status.json`

Returns sync/runtime state if implemented by the runtime scripts.

## API routes

### `GET /api/market-config`

Returns active market symbol configuration.

Example response:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

Verification:

```bash
curl -s http://127.0.0.1:8765/api/market-config | python3 -m json.tool
```

### `POST /api/market-config`

Updates the market watchlist config.

Request:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT"]
}
```

Rules:

```text
1. symbols must be a list
2. values are stripped and uppercased
3. empty values are ignored
4. duplicates are removed while preserving order
5. at most 12 symbols are stored
6. empty final list is rejected
```

Example:

```bash
curl -s -X POST http://127.0.0.1:8765/api/market-config \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["AAPL","NVDA","MSFT"]}' | python3 -m json.tool
```

### `POST /api/market-refresh`

Runs the live-data refresh script.

Expected command:

```bash
python3 surface/fetch_live_data.py
```

Expected response fields:

```text
ok
returncode
stdout
stderr
market
weather, if implemented by current server version
```

Example:

```bash
curl -s -X POST http://127.0.0.1:8765/api/market-refresh | python3 -m json.tool | head -n 80
```

### `GET /api/local-events/search`

Returns the latest local event search payload. It should not start a new search.

Example:

```bash
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
```

### `POST /api/local-events/search`

Runs a local official event search and returns the newly written payload.

Request:

```json
{
  "location": "Punggol Singapore"
}
```

Expected command:

```bash
python3 surface/search_local_events.py "Punggol Singapore"
```

Expected response fields:

```text
ok
stdout
stderr
results
count
source_count
debug_by_source, if generated by extractor
```

Example:

```bash
curl -s -X POST http://127.0.0.1:8765/api/local-events/search \
  -H 'Content-Type: application/json' \
  -d '{"location":"Punggol Singapore"}' | python3 -m json.tool | head -n 120
```

## OpenAPI routes

### `GET /openapi.json`

Returns generated OpenAPI JSON if Pydantic is installed and schema generation succeeds.

Verification:

```bash
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80
```

Failure must be explicit, for example:

```json
{
  "ok": false,
  "error": "openapi_generation_failed: ModuleNotFoundError: No module named 'pydantic'"
}
```

### `GET /docs`

Returns Swagger UI HTML that loads `/openapi.json`.

Verification:

```bash
curl -s http://127.0.0.1:8765/docs | head
```

## Public photo route

### `GET /public_photos/<path>`

Serves generated public photo files if photo export has produced them.

The exact backing path must be verified from the current server implementation before changing docs or scripts.

## Error-handling rules

```text
1. Do not silently fall back to fake JSON.
2. Do not silently fall back from rendered local-event extraction to an old crawler.
3. If a dependency is missing, return or write a clear error reason.
4. Failed subprocess endpoints should include stdout/stderr tails.
5. Browser should show unavailable/stale state rather than stale data disguised as fresh data.
```

## API verification checklist

```bash
cd ~/infoscreen

curl -s http://127.0.0.1:8765/schedule.json | python3 -m json.tool | head -n 40
curl -s http://127.0.0.1:8765/api/market-config | python3 -m json.tool
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/docs | head
```
