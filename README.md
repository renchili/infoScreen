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

## Active source overview

Python entrypoints and support modules:

```text
surface/serve_infoscreen.py       HTTP server and local API
surface/fetch_live_data.py        weather and market refresh
surface/fetch_event_stream.py     event/news stream refresh
surface/build_photos_json.py      photo wall JSON builder
surface/search_local_events.py    local event refresh CLI used by the API
surface/openapi_spec.py           support module for /openapi.json
surface/api_models.py             schema support module for openapi_spec.py
```

Local event implementation package:

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
python3 -m py_compile surface/*.py surface/local_events_runtime/*.py
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/dashboard.js | grep -n "market-arrow"
curl -s http://127.0.0.1:8765/assets/css/market_custom.css | grep -n "price.up"
find surface -maxdepth 2 -type f -name "*.py" | sort
```
