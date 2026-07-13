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
AGENTS.md          agent bootstrap and required read order
AGENT.md           project-specific repository rules
metadata.json      compact product metadata and product prompt
pyproject.toml     pytest configuration
.github/workflows/ CI workflow definitions, when GitHub Actions is enabled
docs/design.md     runtime architecture and data flow
docs/api-spec.md   HTTP endpoints and Python owners
docs/questions.md  current project decisions
skills/            agent workflow and hard-gate skills
tests/             local closed-loop unit, contract, and runtime tests
```

## Repository root policy

The repository root is for repository control, documentation, project metadata, CI/test configuration, and operator/deployment entrypoints only. Dashboard runtime JSON, local environment files, browser CSS, browser JavaScript, local photos, generated output, caches, and compiled files do not belong in the repository root.

Allowed root-level project paths:

```text
README.md
AGENTS.md
AGENT.md
metadata.json
pyproject.toml
.gitignore
.githooks/
.github/
docs/
skills/
surface/
deploy/
mac/
scripts/
tests/
```

Runtime JSON belongs under `surface/.env/`. Browser CSS and JavaScript belong under `surface/web/assets/`. Local photos belong under `surface/.env/photos/`. Test fixtures belong under `tests/fixtures/`; generated test reports, logs, JUnit XML, OpenAPI snapshots, and other test artifacts belong under `${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}` or another ignored local artifact path.

Enable the local pre-commit guard once per clone:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

The hook blocks staged root project code outside the allowlist, runtime files, local env files, generated test output, `photo/`, `photos/`, `public_photos/`, and legacy `surface/web/*.js` or `surface/web/*.css` files.

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

The card must keep the compact TTY style: no dotted background in the local-event panel, compact `‹` / `›` / `⌕` controls with the counter on the top-right, source/organization at the card top-left, no separate `EVENT` label, compact `WHEN` and `WHERE` rows, and the official link pinned to the bottom of the card.

The local-event backend owns data collection and should provide full available fields without presentation truncation. The frontend owns display fitting: it decides wrapping, clipping, scrolling, and any visual ellipsis based on the current card size.

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

The kiosk dashboard must show a compact market configuration button that does not cover quote rows. Clicking the button opens the symbol editor overlay; market symbols remain configurable through `/api/market-config` and refresh through `/api/market-refresh`.

Photo wall:

```text
surface/.env/photos/
surface/build_photos_json.py
surface/.env/photos.json
surface/.env/public_photos/
```

Put user photos in `surface/.env/photos/`. After adding photos, run the photo builder so `photos.json` and `public_photos/` are regenerated.

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

### Schedule sync — run on the Mac

`schedule.json` is not generated on the Surface. macOS Calendar/EventKit is the data source, so the scheduled export and sync run on the Mac and push the file to the Surface runtime directory.

Run this on the Mac to configure or update the Surface SSH address and install or refresh the LaunchAgent:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user rody \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

This writes the local-only `mac/local.env` and installs `~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist`. Trigger one sync immediately with:

```bash
launchctl kickstart -k gui/$(id -u)/com.renchili.infoscreen.schedule-sync
```

The remote target must remain `~/infoscreen/surface/.env/schedule.json`; `~/infoscreen/schedule.json` is not a valid runtime path.

## Refresh commands

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/build_photos_json.py
python3 surface/search_local_events.py "Punggol Singapore"
```

## Test model

The test suite is a local closed-loop pytest suite. It uses committed fixture JSON and an isolated runtime directory, so tests do not require external network access and do not write into the real `surface/.env/`.

Test groups:

```text
tests/test_backend_api.py          backend helpers, OpenAPI coverage, and Pydantic model contracts
tests/test_frontend_content.py     dashboard HTML, mount points, asset paths, and frontend content contracts
tests/test_style_contract.py       CSS/layout contracts for local events, market controls, and photo wall structure
tests/test_runtime_data_contract.py fixture JSON shape and renderability contracts
tests/test_http_closed_loop.py     in-process HTTP server checks using fixture runtime data
tests/test_scripts_contract.py     shell syntax and workflow configuration checks
tests/fixtures/runtime_data/       closed-loop weather, market, event stream, local events, photo, and schedule data
```

These tests are product and contract tests. They do not replace manual/browser validation, and they should remain focused on stable product behavior, API contracts, UI contracts, fixture data contracts, and script contracts.

## Test and acceptance commands

The local closed-loop runner seeds fixture data and writes logs, JUnit XML, generated OpenAPI, and summary output under `/tmp/infoscreen-acceptance` by default.

```bash
cd ~/infoscreen
python3 -m pip install pytest pydantic
bash scripts/run_full_ci_tests.sh
```

The compatibility entrypoint delegates to the same runner:

```bash
bash scripts/run_acceptance.sh
```

When GitHub Actions is enabled, `.github/workflows/acceptance.yml` runs the same local closed-loop test script. It does not upload test artifacts; the job log remains the CI evidence surface.

Project-direction decisions belong in `docs/questions.md`. If repository policy, test scope, CI behavior, runtime boundaries, or active source paths change, update `docs/questions.md` in the same change set.

## Verify

```bash
cd ~/infoscreen
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 -m pytest
bash scripts/run_full_ci_tests.sh
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/local_event_card.js | grep -n "local-event-source-top"
curl -s http://127.0.0.1:8765/assets/css/local_events.css | grep -n "local-event-desc"
curl -s http://127.0.0.1:8765/assets/js/market_custom.js | grep -n "marketConfigButton"
curl -s http://127.0.0.1:8765/photos.json | grep -n "items"
find . -maxdepth 1 -type f \( ! -name "README.md" ! -name "AGENTS.md" ! -name "AGENT.md" ! -name "metadata.json" ! -name "pyproject.toml" ! -name ".gitignore" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
find surface -maxdepth 3 -type f -name "*.py" | sort
```
