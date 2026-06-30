# InfoScreen design

This document describes the intended project design. It does not replace `README.md` usage instructions or `docs/api-spec.md` endpoint details.

## Purpose

InfoScreen is a local kiosk dashboard for an always-on Surface/Ubuntu display.

The dashboard should show:

```text
1. local clock/date
2. calendar schedule
3. market watchlist
4. weather
5. event/news stream
6. local official events
7. photo wall
8. runtime/sync status
```

The system should be simple to operate locally and easy to debug through files, logs, systemd units, and HTTP endpoints.

## Hosts and ownership

### Surface / Ubuntu host

The Surface host owns:

```text
1. HTTP dashboard server
2. static frontend files
3. market/weather refresh
4. event/news stream refresh
5. local official event search
6. systemd user services/timers
7. local logs
```

Main entrypoints:

```text
surface/serve_infoscreen.py
surface/fetch_live_data.py
surface/fetch_event_stream.py
surface/search_local_events.py
surface/build_photos_json.py
```

### macOS host

The Mac host owns only Apple Calendar export and schedule sync.

Main entrypoints:

```text
mac/export.py
mac/sync_schedule.sh
mac/scripts/setup-schedule-sync.sh
```

The Mac checkout must not depend on a Surface frontend/crawler feature branch.

## Data flow

### Calendar schedule

```text
Apple Calendar on Mac
  -> mac/export.py
  -> mac/schedule.json
  -> mac/sync_schedule.sh over SSH/SCP
  -> ~/infoscreen/schedule.json on Surface
  -> GET /schedule.json
  -> calendar board frontend
```

Current verified Surface target:

```text
~/infoscreen/schedule.json
```

Do not move this path without a separate migration and verification.

### Market and weather

```text
surface/fetch_live_data.py
  -> runtime weather JSON
  -> runtime market JSON
  -> GET /weather.json and GET /market.json
  -> dashboard panels and tickers
```

The exact runtime file path must match the current server implementation and docs before changing systemd timers or frontend fetches.

### Event/news stream

```text
surface/fetch_event_stream.py
  -> runtime event_stream.json
  -> GET /event_stream.json
  -> multilingual event/news ticker
```

### Local official events

```text
surface/conf/official_source_registry.json
surface/conf/event_sources.json
  -> surface/search_local_events.py
  -> surface/local_events_runtime/
  -> runtime local_event_search_results.json
  -> GET/POST /api/local-events/search
  -> local events frontend
```

Local event source rules:

```text
official_source_registry.json = official homepage/domain identity only
event_sources.json = verified event listing entrypoints
no third-party aggregators
no guessed domains or guessed /events paths
no silent fallback to old crawler or fake data
```

## HTTP server design

`surface/serve_infoscreen.py` should remain a small local HTTP/API/static-file server.

Allowed responsibilities:

```text
1. serve surface/web/index.html
2. serve static files from surface/web/
3. expose runtime JSON endpoints
4. expose API endpoints
5. expose /openapi.json and /docs
6. run explicitly requested backend refresh commands
```

Forbidden responsibilities:

```text
1. injecting CSS into HTML
2. replacing script URLs or cache-busting versions at runtime
3. patching HTML structure at runtime
4. hiding frontend duplication by server-side regex cleanup
5. guessing runtime file paths
```

Frontend cleanup should happen in source files, not in the server.

## Frontend design

Canonical checked-in frontend files live under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

The target browser asset ownership is:

```text
assets/css/app.css              base layout/theme
assets/css/calendar_board.css   calendar board styles
assets/css/local_events.css     local events styles
assets/css/market_custom.css    market custom styles
assets/js/calendar_board.js     calendar board behavior
assets/js/local_events.js       local event behavior
assets/js/market_custom.js      market custom behavior
```

`surface/web/index.html` should reference assets only. Root-level duplicates and `surface/web/*.js|*.css` duplicates are cleanup debt.

Each browser panel should have one owner module. Do not keep multiple state machines controlling the same UI widget.

## Runtime files and logs

Runtime files are deployment state, not source code.

Known current files:

```text
~/infoscreen/schedule.json
~/infoscreen/surface/.env/
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

The HTTP service must keep append-style file logs unless a documented migration replaces them:

```ini
StandardOutput=append:%h/infoscreen/surface/.env/logs/http.log
StandardError=append:%h/infoscreen/surface/.env/logs/http.err.log
```

Before destructive git operations on a deployed Surface host, backup:

```text
schedule.json
surface/.env/
```

## API and schema design

The project uses a framework-independent API schema layer.

```text
surface/api_models.py      Pydantic schemas
surface/openapi_spec.py    OpenAPI route/spec builder
GET /openapi.json          machine-readable OpenAPI
GET /docs                  Swagger UI
```

The server should not be migrated to FastAPI solely for OpenAPI support.

## Local event extraction design

Main path:

```text
surface/search_local_events.py
  -> surface/local_events_runtime.extract.collect_events
  -> surface/local_events_runtime.browser.render_listing_cards
  -> local_event_search_results.json
```

Rendered DOM extraction uses Playwright as a browser-control layer. It should not import or require large local LLM/VLM/OCR models by default.

Output should include debug information when possible:

```text
source_count
count
debug_by_source
reason_counts
accepted_preview
not_output_preview
```

Do not claim extractor quality is fixed until real output and debug data are reviewed on the Surface host.

## systemd design

Canonical user systemd templates live under:

```text
deploy/systemd/user/
```

Install/update scripts live under:

```text
deploy/scripts/
```

Do not extend competing locations such as `surface/systemd/`. Move or remove legacy locations in a dedicated cleanup.

Expected user units include:

```text
infoscreen-http.service
infoscreen-live-data.service
infoscreen-live-data.timer
infoscreen-event-stream.service
infoscreen-event-stream.timer
infoscreen-local-events.service
infoscreen-local-events.timer
```

Refresh jobs should be timer-driven oneshot services where appropriate.

## Documentation design

Documentation responsibilities:

```text
metadata.json              project requirements, constraints, plan
README.md                  user-facing setup/start/use/troubleshooting
docs/api-spec.md           endpoint interactions
docs/design.md             system design
docs/questions.md          implementation issues and resolution notes
docs/project-structure.md  repository and development-boundary constraints
```

Do not keep conflicting copies of structure/runtime rules in multiple docs.

## Non-goals

```text
1. no default large local model dependency
2. no Qwen/OCR/VLM in the default local event path
3. no third-party event aggregators as official source truth
4. no hidden fallback to old crawler/fake data
5. no frontend patches from serve_infoscreen.py
6. no Mac checkout dependency on Surface feature branches
```

## Cleanup backlog

Current cleanup still needed:

```text
1. normalize frontend assets under surface/web/assets/
2. remove duplicate root and surface/web JS/CSS files
3. remove server-side CSS/script injection from serve_infoscreen.py
4. restore and verify HTTP file logging
5. align schedule sync docs/scripts/server behavior to ~/infoscreen/schedule.json
6. add/repair .gitignore for runtime files and pycache
7. prune or convert conflicting docs into pointers
8. split Mac schedule sync changes from Surface frontend/crawler changes
```
