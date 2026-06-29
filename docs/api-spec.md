# InfoScreen API usage spec

This document describes the HTTP API exposed by the local InfoScreen server.

## Runtime model

- Server entrypoint: `surface/serve_infoscreen.py`.
- Server bind address: `0.0.0.0:8765`.
- Static web root: `surface/web/`.
- Runtime JSON root: `surface/.env/`.
- Configuration root: `surface/conf/`.
- The server must not read fallback runtime JSON from the repository root.
- Runtime JSON files are intentionally not source-controlled.

## General response rules

- JSON responses use `application/json; charset=utf-8`.
- Static and JSON responses send `Cache-Control: no-store`.
- Runtime JSON endpoints return a missing-runtime object if the backing file does not exist.
- Write endpoints should return `{ "ok": true, ... }` on success and `{ "ok": false, "error": "..." }` on failure.

## Static endpoints

### `GET /`

Returns the dashboard HTML.

Implementation note: the served HTML is sanitized by `surface/serve_infoscreen.py` to strip the legacy local-event inline script block:

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

## Runtime JSON endpoints

The following files are served from `surface/.env/`.

### `GET /schedule.json`

Default payload if missing:

```json
[]
```

Used by the right-side calendar board.

### `GET /weather.json`

Default payload if missing:

```json
{}
```

Used by the weather panel.

### `GET /market.json`

Default payload if missing:

```json
{}
```

Used by the market panel and ticker.

### `GET /market_config.json`

Default payload if missing:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

### `GET /event_stream.json`

Default payload if missing:

```json
{
  "items": []
}
```

Used by the multilingual event/news ticker.

### `GET /photos.json`

Default payload if missing:

```json
{
  "items": []
}
```

Used by the photo wall.

### `GET /sync_status.json`

Default payload if missing:

```json
{}
```

Reserved for sync/runtime state.

### `GET /local_event_search_results.json`

Returns the same runtime data used by the local event API.

Default payload if missing:

```json
{
  "results": []
}
```

## API endpoints

### `GET /api/market-config`

Returns the active market symbol config.

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

Success response:

```json
{
  "ok": true,
  "symbols": ["AAPL", "NVDA", "MSFT"],
  "updated_at": "..."
}
```

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

Expected current extractor after the rendered DOM work:

```text
rendered-dom-card-v41
```

Example response shape:

```json
{
  "ok": true,
  "version": 41,
  "extractor": "rendered-dom-card-v41",
  "updated_at": "...",
  "location": "Punggol Singapore",
  "runtime": {
    "writer": "surface.local_events_runtime.extract.collect_events",
    "pid": 12345,
    "cwd": "/home/rody/infoscreen/surface",
    "python": "/usr/bin/python3",
    "module_file": ".../surface/local_events_runtime/extract.py",
    "git_head": "..."
  },
  "count": 1,
  "results": [
    {
      "title": "Event title",
      "when": "24 May 2025 — 09 Oct 2026",
      "where": "B1 Exhibition Galleries",
      "host": "National Museum Singapore",
      "source_name": "National Museum Singapore",
      "url": "https://...",
      "summary": "...",
      "start_date": "2025-05-24",
      "kind": "event",
      "source_type": "rendered_dom_card"
    }
  ],
  "debug_by_source": []
}
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
  "when": "required date/time text",
  "where": "venue or fallback venue",
  "host": "organizer/source display name",
  "source_name": "official source name",
  "url": "https:// official URL",
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
- Failed subprocess endpoints should return HTTP 500 with captured stderr/stdout.

## Verification

```bash
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/ | grep -n "local-event-inline-script" || true
curl -s http://127.0.0.1:8765/calendar_board.js | grep -n "MutationObserver\|watchdog\|external-local-events" || true
```
