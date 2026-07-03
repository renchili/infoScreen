# InfoScreen API interaction spec

The HTTP server is `surface/serve_infoscreen.py`.

Runtime JSON is stored under `surface/.env/`.

Pydantic schemas live in `surface/api_models.py`.

OpenAPI generation lives in `surface/openapi_spec.py` and is served at `/openapi.json`.

## Pages

| Endpoint | Python owner | Source/runtime file |
|---|---|---|
| `/` | `serve_infoscreen.py` | `surface/web/index.html` |
| `/index.html` | `serve_infoscreen.py` | `surface/web/index.html` |
| `/docs` | `serve_infoscreen.py` | Swagger UI wrapper |
| `/openapi.json` | `serve_infoscreen.py`, `openapi_spec.py`, `api_models.py` | generated OpenAPI JSON |

## Runtime JSON reads

| Endpoint | Python owner | Runtime file |
|---|---|---|
| `/schedule.json` | `serve_infoscreen.py` | `surface/.env/schedule.json` |
| `/weather.json` | `serve_infoscreen.py` | `surface/.env/weather.json` |
| `/market.json` | `serve_infoscreen.py` | `surface/.env/market.json` |
| `/market_config.json` | `serve_infoscreen.py` | `surface/.env/market_config.json` |
| `/event_stream.json` | `serve_infoscreen.py` | `surface/.env/event_stream.json` |
| `/local_event_search_results.json` | `serve_infoscreen.py` | `surface/.env/local_event_search_results.json` |
| `/photos.json` | `serve_infoscreen.py` | `surface/.env/photos.json` |
| `/sync_status.json` | `serve_infoscreen.py` | `surface/.env/sync_status.json` |

## Local APIs

| Endpoint | Method | Python owner | Behavior |
|---|---|---|---|
| `/api/market-config` | GET | `serve_infoscreen.py` | read active market symbol config |
| `/api/market-config` | POST | `serve_infoscreen.py` | write `surface/.env/market_config.json` |
| `/api/market-refresh` | POST | `serve_infoscreen.py`, `fetch_live_data.py` | refresh `weather.json` and `market.json` |
| `/api/local-events/search` | GET | `serve_infoscreen.py` | read `local_event_search_results.json` |
| `/api/local-events/search` | POST | `serve_infoscreen.py`, `search_local_events.py`, `local_events_runtime/` | run local event search and return runtime JSON |

## Runtime writers not directly called by HTTP

| Python file | Output |
|---|---|
| `fetch_event_stream.py` | `surface/.env/event_stream.json` |
| `build_photos_json.py` | `surface/.env/photos.json`, `surface/.env/public_photos/` |

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
