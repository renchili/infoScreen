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

## Active source files

```text
surface/serve_infoscreen.py               HTTP server and local API
surface/fetch_live_data.py                weather and market refresh
surface/search_local_events.py            local event refresh
surface/web/index.html                    dashboard shell
surface/web/assets/css/app.css            base layout
surface/web/assets/css/calendar_board.css calendar panel
surface/web/assets/css/local_events.css   local event panel
surface/web/assets/css/market_custom.css  market controls and colors
surface/web/assets/js/dashboard.js        clock/weather/market/event stream
surface/web/assets/js/calendar_board.js   calendar panel
surface/web/assets/js/local_event_card.js local event panel
surface/web/assets/js/market_custom.js    market controls
```

The active browser CSS and JS files are under `surface/web/assets/`. Root-level web JS/CSS files are not active entrypoints.

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
python3 surface/search_local_events.py "Punggol Singapore"
```

## Verify

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/dashboard.js | grep -n "market-arrow"
curl -s http://127.0.0.1:8765/assets/css/market_custom.css | grep -n "price.up"
find surface/web -maxdepth 1 -type f | sort
```
