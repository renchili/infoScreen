# InfoScreen API interaction spec

The InfoScreen HTTP server is implemented by `surface/serve_infoscreen.py`.

Runtime JSON files are stored under `surface/.env/`.

The schedule endpoint uses `surface/.env/schedule.json`.

The repository root is source layout, not runtime storage. The sample schedule file is `sample/schedule.json`.

Static frontend assets are stored under `surface/web/assets/css/` and `surface/web/assets/js/`.

Endpoint groups:

- dashboard HTML
- runtime JSON
- market config and refresh
- local event search
- OpenAPI JSON
- API docs page
