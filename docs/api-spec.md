# InfoScreen API interaction spec

The HTTP server is `surface/serve_infoscreen.py`.

Runtime JSON is stored under `surface/.env/`.

## Pages

```text
/             dashboard HTML from surface/web/index.html
/index.html   dashboard HTML
/docs         Swagger UI
/openapi.json OpenAPI JSON
```

## Runtime JSON

```text
/schedule.json                   surface/.env/schedule.json
/weather.json                    surface/.env/weather.json
/market.json                     surface/.env/market.json
/market_config.json              surface/.env/market_config.json
/event_stream.json               surface/.env/event_stream.json
/local_event_search_results.json surface/.env/local_event_search_results.json
/photos.json                     surface/.env/photos.json
/sync_status.json                surface/.env/sync_status.json
```

## Local API

```text
/api/market-config
/api/market-refresh
/api/local-events/search
```

## Static frontend files

The dashboard loads CSS and JavaScript from `surface/web/assets/`.

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
