# InfoScreen design

This document defines implementation contracts for the local InfoScreen dashboard.

## 1. System boundary

```text
macOS host
  owns: Apple Calendar export only
  writes locally: mac/schedule.json
  pushes remotely: ~/infoscreen/surface/.env/schedule.json

Surface / Ubuntu host
  owns: HTTP server, runtime refresh scripts, systemd units, file logs
  serves: http://0.0.0.0:8765
  runtime root: ~/infoscreen/surface/.env/

Browser / kiosk
  owns: rendering only
  reads: HTTP endpoints from Surface
  writes: only through documented POST APIs
```

## 2. Data flow contracts

| Feature | Producer | Runtime/API boundary | Consumer | Verification |
|---|---|---|---|---|
| Schedule | `mac/export.py` + `mac/sync_schedule.sh` | `surface/.env/schedule.json` and `GET /schedule.json` | calendar frontend | compare response hash with runtime file hash |
| Market | `surface/fetch_live_data.py` | `GET /market.json` | market frontend | `curl -s /market.json | python3 -m json.tool` |
| Weather | `surface/fetch_live_data.py` | `GET /weather.json` | weather frontend | `curl -s /weather.json | python3 -m json.tool` |
| Event stream | `surface/fetch_event_stream.py` | `GET /event_stream.json` | ticker frontend | `curl -s /event_stream.json | python3 -m json.tool` |
| Local events | `surface/search_local_events.py` | `GET/POST /api/local-events/search` | local events frontend | inspect `debug_by_source`, `count`, `results` |
| Photos | `surface/build_photos_json.py` | `GET /photos.json`, `GET /public_photos/...` | photo wall | `curl -I /public_photos/<file>` |

The schedule file is runtime state. It must not be placed in the repository root as a source file. The root-level `sample/schedule.json` fixture is allowed because it is explicitly sample data.

## 3. Target file structure contract

```text
repo root
├── README.md
├── metadata.json
├── deploy/
│   ├── scripts/install-user-systemd.sh
│   └── systemd/user/
├── docs/
│   ├── api-spec.md
│   ├── design.md
│   └── questions.md
├── mac/
│   ├── export.py
│   ├── sync_schedule.sh
│   └── scripts/
├── sample/
│   └── schedule.json
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
    ├── local_events_runtime/
    └── web/
        ├── index.html
        └── assets/
            ├── css/
            └── js/
```

Runtime files are outside the source tree contract even when they live physically inside the checkout under `surface/.env/`:

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/event_stream.json
surface/.env/local_event_search_results.json
surface/.env/logs/http.log
surface/.env/logs/http.err.log
```

Files that should not remain as checked-in source files:

```text
schedule.json
mac/schedule.json
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
```

## 4. Static frontend contract

`surface/web/index.html` should reference checked-in assets through `assets/` only:

```html
<link rel="stylesheet" href="assets/css/app.css">
<link rel="stylesheet" href="assets/css/calendar_board.css">
<link rel="stylesheet" href="assets/css/local_events.css">
<link rel="stylesheet" href="assets/css/market_custom.css">

<script src="assets/js/calendar_board.js"></script>
<script src="assets/js/local_events.js"></script>
<script src="assets/js/market_custom.js"></script>
```

## 5. HTTP server contract

`surface/serve_infoscreen.py` serves static files and JSON/API endpoints. It should read runtime JSON from `surface/.env/`. It should not inject CSS, rewrite script URLs, or patch dashboard HTML as normal behavior.

## 6. Runtime verification

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/surface/.env/schedule.json
systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log
find docs -maxdepth 1 -type f | sort
find surface/web -maxdepth 2 -type f | sort
find . -name '__pycache__' -o -name '*.pyc'
```
