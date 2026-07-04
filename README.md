# InfoScreen

Local kiosk dashboard for a Surface or Ubuntu display.

## Run

```bash
cd ~/infoscreen
systemctl --user restart infoscreen-http.service
```

Open `http://127.0.0.1:8765/`.

Manual run:

```bash
cd ~/infoscreen
python3 surface/serve_infoscreen.py
```

## Documentation map

```text
README.md          run, verify, and source overview
docs/design.md     runtime architecture and data flow
docs/api-spec.md   HTTP endpoints and Python owners
docs/questions.md  current project decisions
```

## Repository root policy

The repository root is for control files and documentation only. Dashboard runtime JSON, CSS, and JavaScript files do not belong in the root.

Allowed root-level project files include:

```text
README.md
AGENTS.md
AGENT.md
.gitignore
docs/
surface/
```

Runtime JSON belongs under `surface/.env/`. Browser CSS and JavaScript belong under `surface/web/assets/`.

## Active source overview

Server and API support:

```text
surface/serve_infoscreen.py       HTTP server and local API
surface/openapi_spec.py           support module for /openapi.json
surface/api_models.py             schema support module for openapi_spec.py
```

Jobs and wrappers:

```text
surface/fetch_live_data.py         weather and market refresh
surface/fetch_event_stream.py      event/news stream refresh
surface/build_photos_json.py       photo wall JSON builder
surface/search_local_events.py     wrapper for local event refresh
surface/jobs/local_event_search.py local event refresh job
```

Local event extraction support:

```text
surface/local_events_runtime/__init__.py
surface/local_events_runtime/browser.py
surface/local_events_runtime/extract.py
```

Browser dashboard files live under:

```text
surface/web/index.html
surface/web/assets/css/
surface/web/assets/js/
```

## Frontend behavior notes

Local event card:

```text
surface/web/assets/js/local_event_card.js
surface/web/assets/css/local_events.css
```

The card must keep the compact TTY style: no dotted background in the local-event panel, compact `‹` / `›` / `⌕` controls, the counter next to those controls on the right, source/organization at the card top-left, no separate `EVENT` label, compact `WHEN` and `WHERE` rows, and the official link directly after the content rather than pushed to the bottom.

Sync ticker:

```text
surface/web/assets/js/local_event_card.js
```

The left sync ticker must show file freshness, not only source counts. It checks `Last-Modified` through `HEAD` requests and displays `OK` / `STALE` / `MISS` / `ERR`, `LATEST`, and `AGE` for schedule, weather, market, and news runtime JSON.

Market panel:

```text
surface/web/assets/js/dashboard.js
surface/web/assets/js/market_custom.js
surface/web/assets/css/market_custom.css
```

The kiosk dashboard must show a compact market configuration button, not an always-visible inline editor that shifts the market rows. Clicking the button opens the symbol editor overlay; market symbols remain configurable through `/api/market-config` and refresh through `/api/market-refresh`.

Photo wall:

```text
photos/
photo/
surface/.env/photos/
surface/build_photos_json.py
surface/.env/photos.json
surface/.env/public_photos/
```

Put user photos in the repository-level `photos/` directory. `surface/build_photos_json.py` also supports the singular root `photo/` directory and the legacy `surface/.env/photos/` directory. After adding photos, run the photo builder so `photos.json` and `public_photos/` are regenerated.

## Runtime files

Runtime files live under `~/infoscreen/surface/.env/` and are not source files.

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/market_config.json
surface/.env/event_stream.json
surface/.env/local_event_search_results.json
surface/.env/photos.json
surface/.env/sync_status.json
surface/.env/logs/http.log
surface/.env/logs/http.err.log
```

## Refresh commands

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/build_photos_json.py
python3 surface/search_local_events.py "Punggol Singapore"
```

## Verify

```bash
cd ~/infoscreen
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 surface/build_photos_json.py
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/local_event_card.js | grep -n "local-event-source-top"
curl -s http://127.0.0.1:8765/assets/css/local_events.css | grep -n "local-event-source-top"
curl -s http://127.0.0.1:8765/assets/js/market_custom.js | grep -n "marketConfigButton"
curl -s http://127.0.0.1:8765/photos.json | grep -n "items"
find . -maxdepth 1 -type f \( -name "*.json" -o -name "*.js" -o -name "*.css" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
find surface -maxdepth 3 -type f -name "*.py" | sort
```
