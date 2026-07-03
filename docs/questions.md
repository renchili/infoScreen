# InfoScreen decisions

This file records the current choices only.

## Runtime data

Runtime JSON and logs live under:

```text
surface/.env/
```

Important runtime files:

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/local_event_search_results.json
surface/.env/logs/http.log
surface/.env/logs/http.err.log
```

## Frontend entrypoints

The dashboard shell is:

```text
surface/web/index.html
```

Checked-in browser files are loaded from `surface/web/assets/`:

```text
surface/web/assets/css/app.css
surface/web/assets/css/calendar_board.css
surface/web/assets/css/local_events.css
surface/web/assets/css/market_custom.css
surface/web/assets/js/dashboard.js
surface/web/assets/js/calendar_board.js
surface/web/assets/js/local_event_card.js
surface/web/assets/js/market_custom.js
```

Root-level web JavaScript and CSS files are not dashboard entrypoints.

## Python roles

```text
surface/serve_infoscreen.py     HTTP server and local API
surface/fetch_live_data.py      market and weather refresh
surface/search_local_events.py  local official event refresh
```

Other Python files should be treated as support code only when imported by those entrypoints.

## Server boundary

`surface/serve_infoscreen.py` serves files and JSON. It must not rewrite dashboard HTML to fix frontend layout.

## Verification

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/dashboard.js | grep -n "market-arrow"
find surface/web -maxdepth 1 -type f | sort
```
