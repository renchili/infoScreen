# InfoScreen design

This document defines concrete implementation contracts. It is not a prose overview.

## 1. System boundary

```text
macOS host
  owns: Apple Calendar export only
  writes: mac/schedule.json
  pushes: ~/infoscreen/schedule.json on Surface through SSH/SCP

Surface / Ubuntu host
  owns: HTTP server, runtime refresh scripts, systemd units, file logs
  serves: http://0.0.0.0:8765
  stores runtime state under the deployed checkout

Browser / kiosk
  owns: rendering only
  reads: HTTP endpoints from Surface
  writes: only through documented POST APIs
```

Forbidden coupling:

```text
Mac checkout must not switch to a Surface frontend/crawler branch.
Surface runtime must not depend on Mac repo state except the pushed schedule.json file.
Browser must not contain two JS state machines for the same panel.
```

## 2. Data flow contracts

| Feature | Producer | File/API boundary | Consumer | Verification |
|---|---|---|---|---|
| Schedule | `mac/export.py` + `mac/sync_schedule.sh` | `~/infoscreen/schedule.json` and `GET /schedule.json` | calendar frontend | `sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json` |
| Market | `surface/fetch_live_data.py` | `GET /market.json` | market frontend | `curl -s /market.json | python3 -m json.tool` |
| Weather | `surface/fetch_live_data.py` | `GET /weather.json` | weather frontend | `curl -s /weather.json | python3 -m json.tool` |
| Event stream | `surface/fetch_event_stream.py` | `GET /event_stream.json` | ticker frontend | `curl -s /event_stream.json | python3 -m json.tool` |
| Local events | `surface/search_local_events.py` | `GET/POST /api/local-events/search` | local events frontend | inspect `debug_by_source`, `count`, `results` |
| Photos | `surface/build_photos_json.py` | `GET /photos.json`, `GET /public_photos/...` | photo wall | `curl -I /public_photos/<file>` |
| Runtime status | refresh scripts / status script | `GET /sync_status.json` if implemented | status panel | `curl -s /sync_status.json` |

Schedule path is currently fixed to:

```text
~/infoscreen/schedule.json
```

Do not document or configure `~/infoscreen/surface/.env/schedule.json` unless the server is changed and verified to read it.

## 3. Target file structure contract

Final desired tree:

```text
repo root
├── README.md
├── metadata.json
├── schedule.json                         # runtime only; ignored
├── deploy/
│   ├── scripts/install-user-systemd.sh
│   └── systemd/user/
│       ├── infoscreen-http.service
│       ├── infoscreen-live-data.service
│       ├── infoscreen-live-data.timer
│       ├── infoscreen-event-stream.service
│       ├── infoscreen-event-stream.timer
│       ├── infoscreen-local-events.service
│       └── infoscreen-local-events.timer
├── docs/
│   ├── api-spec.md
│   ├── design.md
│   └── questions.md
├── mac/
│   ├── export.py
│   ├── sync_schedule.sh
│   └── scripts/
├── sample/
├── scripts/
└── surface/
    ├── serve_infoscreen.py
    ├── fetch_live_data.py
    ├── fetch_event_stream.py
    ├── search_local_events.py
    ├── build_photos_json.py
    ├── api_models.py
    ├── openapi_spec.py
    ├── conf/
    │   ├── official_source_registry.json
    │   ├── event_sources.json
    │   └── market_config.default.json
    ├── local_events_runtime/
    └── web/
        ├── index.html
        └── assets/
            ├── css/
            │   ├── app.css
            │   ├── calendar_board.css
            │   ├── local_events.css
            │   └── market_custom.css
            └── js/
                ├── calendar_board.js
                ├── local_events.js
                └── market_custom.js
```

Files/directories that must be removed or ignored during cleanup:

```text
surface/web/calendar_board.css
surface/web/calendar_board.js
surface/web/local_events.css
surface/web/local_events.js
surface/web/market_custom.css
surface/web/market_custom.js
market_custom.css
market_custom.js
surface/systemd/
__pycache__/
surface/**/__pycache__/
*.pyc
surface/.env/
surface/.env/logs/
```

Acceptance commands:

```bash
find docs -maxdepth 1 -type f | sort
find surface/web -maxdepth 2 -type f | sort
find . -name '__pycache__' -o -name '*.pyc'
git status --short
```

Expected docs files only:

```text
docs/api-spec.md
docs/design.md
docs/questions.md
```

Expected checked-in frontend JS/CSS only under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

## 4. Static frontend contract

`surface/web/index.html` must reference assets with these paths:

```html
<link rel="stylesheet" href="assets/css/app.css">
<link rel="stylesheet" href="assets/css/calendar_board.css">
<link rel="stylesheet" href="assets/css/local_events.css">
<link rel="stylesheet" href="assets/css/market_custom.css">

<script src="assets/js/calendar_board.js"></script>
<script src="assets/js/local_events.js"></script>
<script src="assets/js/market_custom.js"></script>
```

Invalid references after cleanup:

```text
calendar_board.css
calendar_board.js
local_events.css
local_events.js
market_custom.css
market_custom.js
../market_custom.js
/market_custom.js
```

Verification:

```bash
grep -RIn "calendar_board\|local_events\|market_custom" surface/web/index.html
curl -s http://127.0.0.1:8765/ | grep -n "assets/css\|assets/js" | head -n 40
```

## 5. Browser state ownership contract

| UI panel | JS owner | CSS owner | State owner rule |
|---|---|---|---|
| Calendar board | `assets/js/calendar_board.js` | `assets/css/calendar_board.css` | only this module paginates/renders calendar rows |
| Local events | `assets/js/local_events.js` | `assets/css/local_events.css` | only this module owns search, paging, current item list |
| Market controls | `assets/js/market_custom.js` | `assets/css/market_custom.css` | only this module owns market config edit/refresh |
| Base layout | inline minimal boot or future `assets/js/app.js` | `assets/css/app.css` | no duplicated panel-specific state |

Invalid design:

```text
local event inline script inside index.html plus local_events.js
calendar_board.js also owning local event state after local_events.js exists
serve_infoscreen.py stripping one frontend owner to hide duplicate state
```

## 6. HTTP server contract

Module:

```text
surface/serve_infoscreen.py
```

Allowed:

```text
GET static files
GET runtime JSON
GET /openapi.json
GET /docs
POST /api/market-config
POST /api/market-refresh
GET /api/local-events/search
POST /api/local-events/search
```

Forbidden:

```text
inject CSS into index.html
rewrite script URLs
change cache-busting values
strip frontend scripts as permanent behavior
serve fake success data when backend command failed
silently choose a different runtime path
```

Cleanup acceptance:

```bash
grep -RIn "replace(.*calendar_board\|toolbar\|inject\|local-event-inline-script\|cleaned" surface/serve_infoscreen.py || true
```

Expected after cleanup: no frontend patching logic remains.

## 7. Runtime file contract

Current verified runtime files:

```text
~/infoscreen/schedule.json
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

Runtime files are deployment state. They must not be deleted by source cleanup.

Before destructive git operations:

```bash
cd ~/infoscreen
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
echo "$backup"
```

`.gitignore` must include:

```gitignore
schedule.json
surface/.env/
*.log
__pycache__/
*.pyc
```

## 8. Error handling contract

Errors must have one of these categories:

| Category | Example | HTTP behavior | JSON behavior | Log behavior | Frontend behavior |
|---|---|---|---|---|---|
| Missing runtime file | no schedule file | `200` for read endpoints if empty state is acceptable; otherwise `500` | include empty/default plus `stale` or explicit error when implemented | write file path and endpoint | show empty/stale, not fake fresh data |
| Backend subprocess failure | local event search exits non-zero | `500` or `200` with `ok:false` for legacy compatibility | `ok:false`, `returncode`, `stdout`, `stderr`, `error` | append stderr/stdout tail to service log | show failure message/status |
| Missing dependency | no Playwright/Pydantic/browser | `500` for API/doc generation; payload error for extractor | machine-readable reason such as `missing_playwright_python_package` | log import/path failure | show unavailable, not old data as new |
| Source extraction failure | source page changed | `200` with empty/partial results only if payload includes debug | `debug_by_source`, `reason_counts`, `accepted`, `rejected` | log source/reason counts | show available results and stale/failure status |
| Invalid request | bad JSON/body | `400` | `ok:false`, `error:"invalid_request"` | log request path only, not secrets | keep previous state |
| Network/source timeout | market/weather/source request timeout | API refresh returns `ok:false` or status with stale data | include `error`, `updated_at`, `source` if possible | log timeout source | show stale badge/status |

Minimum API error shape:

```json
{
  "ok": false,
  "error": "machine_readable_reason",
  "returncode": 1,
  "stdout": "tail if any",
  "stderr": "tail if any"
}
```

Rules:

```text
No fake events.
No fake market/weather values.
No hidden fallback to the old crawler.
No claiming fresh data when file mtime or payload updated_at is stale.
No swallowing stderr from subprocess APIs.
```

## 9. Logging contract

HTTP service must append logs to:

```text
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

Systemd unit must contain:

```ini
StandardOutput=append:%h/infoscreen/surface/.env/logs/http.log
StandardError=append:%h/infoscreen/surface/.env/logs/http.err.log
```

Verification:

```bash
systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log
```

Do not remove file logging as part of frontend, crawler, docs, or schedule work.

## 10. Local event source contract

`surface/conf/official_source_registry.json` stores only:

```text
official institution id
official institution name
official homepage
allowed official domains
```

It must not store:

```text
event listing URLs
event detail URLs
ticketing URLs
third-party aggregators
```

`surface/conf/event_sources.json` stores:

```text
verified listing entrypoints
adapter/extraction strategy
default venue/source metadata
```

Extractor quality rule:

```text
Do not delete valid sources to make one source look better.
Do not add random source count to hide poor extraction.
Fix card rendering, pagination, and field extraction quality first.
```

## 11. Deployment contract

Canonical systemd source:

```text
deploy/systemd/user/
```

Canonical installer:

```text
deploy/scripts/install-user-systemd.sh
```

Invalid competing source after cleanup:

```text
surface/systemd/
```

Service types:

```text
infoscreen-http.service          long-running service
infoscreen-live-data.service     oneshot refresh
infoscreen-event-stream.service  oneshot refresh
infoscreen-local-events.service  oneshot refresh after extractor is verified
```

Timer rule:

```text
Timers trigger oneshot refresh jobs.
Timers must not overwrite manual debugging output while a feature is under active debugging.
```

## 12. Verification gate

After cleanup, run:

```bash
cd ~/infoscreen

python3 -m py_compile surface/*.py mac/*.py scripts/ci/*.py
python3 surface/search_local_events.py --self-test

curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
curl -s http://127.0.0.1:8765/api/market-config | python3 -m json.tool
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80

systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log

find docs -maxdepth 1 -type f | sort
find surface/web -maxdepth 2 -type f | sort
find . -name '__pycache__' -o -name '*.pyc'
```

Do not claim cleanup complete until these checks match the contracts above.
