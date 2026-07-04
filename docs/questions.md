# InfoScreen decisions

This file records the current choices only.

## Repository root policy

The repository root is for repository control and documentation only.

Allowed root-level project paths:

```text
README.md
AGENTS.md
AGENT.md
.gitignore
.githooks/
docs/
skills/
surface/
```

Project code, local environment files, runtime JSON, browser CSS, browser JavaScript, photos, generated output, and caches do not belong in the root.

Local commit protection is implemented by `.githooks/pre-commit`. Enable it once per clone:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

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
surface/.env/photos.json
surface/.env/public_photos/
surface/.env/logs/http.log
surface/.env/logs/http.err.log
```

Local photo input lives under:

```text
surface/.env/photos/
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

Direct `surface/web/*.js` and `surface/web/*.css` files are also not active source paths.

## Python roles

Entrypoints:

```text
surface/serve_infoscreen.py     HTTP server and local API
surface/fetch_live_data.py      market and weather refresh
surface/search_local_events.py  local official event refresh wrapper
surface/openapi_spec.py         OpenAPI payload builder
```

Canonical local event implementation:

```text
surface/jobs/local_event_search.py
surface/local_events_runtime/__init__.py
surface/local_events_runtime/extract.py
surface/local_events_runtime/browser.py
```

The active crawler path is `search_local_events.py` -> `jobs.local_event_search` -> `local_events_runtime`. Do not add another local event engine or adapter package unless this path is being intentionally replaced.

## Server boundary

`surface/serve_infoscreen.py` serves files and JSON. It must not rewrite dashboard HTML to fix frontend layout.

## Verification

```bash
cd ~/infoscreen
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/dashboard.js | grep -n "market-arrow"
find . -maxdepth 1 -type f \( ! -name "README.md" ! -name "AGENTS.md" ! -name "AGENT.md" ! -name ".gitignore" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
find surface -maxdepth 3 -type f -name "*.py" | sort
```
