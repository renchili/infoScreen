# InfoScreen decisions

This file records current project decisions that affect repository direction, source layout, runtime boundaries, test scope, CI behavior, and operator workflow.

Decision records should describe the target state of the project. They should not preserve implementation mistakes, cleanup history, incident narratives, or blame. When a review changes project policy, record the resulting decision here in neutral project language.

## Repository root policy

The repository root is for repository control, documentation, project metadata, CI/test configuration, and operator/deployment entrypoints only.

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

Dashboard runtime JSON, local environment files, browser CSS, browser JavaScript, photos, generated output, caches, and compiled files do not belong in the repository root.

Root-level browser assets such as `*.js` and `*.css` are not active source files. Active browser assets must live under `surface/web/assets/`.

Direct `surface/web/*.js` and `surface/web/*.css` files are not active source paths.

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
surface/.env/market_config.json
surface/.env/event_stream.json
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

Test fixtures live under:

```text
tests/fixtures/
```

Generated test outputs are local artifacts and should not be committed.

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

## Python roles

Entrypoints:

```text
surface/serve_infoscreen.py     HTTP server and local API
surface/fetch_live_data.py      market and weather refresh
surface/search_local_events.py  local official event refresh wrapper
surface/openapi_spec.py         OpenAPI payload builder
surface/api_models.py           Pydantic model definitions
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

The server supports `INFOSCREEN_ENV_DIR` so tests can run against isolated fixture runtime data instead of the real `surface/.env/`.

## Test model

Use `pytest` for project tests. Tests should validate product behavior, data contracts, UI contracts, HTTP serving behavior, and script contracts.

Current test groups:

```text
tests/test_backend_api.py          backend helpers, OpenAPI, and Pydantic model contracts
tests/test_frontend_content.py     dashboard HTML and frontend content contracts
tests/test_style_contract.py       CSS/layout contract checks
tests/test_runtime_data_contract.py fixture runtime data contracts
tests/test_http_closed_loop.py     in-process HTTP server checks with fixture runtime data
tests/test_scripts_contract.py     shell script and workflow configuration checks
tests/fixtures/runtime_data/       local closed-loop JSON fixtures
```

The closed-loop tests must not require external network access. Runtime data used by tests comes from committed fixtures and is copied into a temporary or ignored runtime directory.

Repository hygiene is enforced through source layout rules, `.gitignore`, `.githooks/pre-commit`, and documented verification commands. Product tests should stay focused on product behavior and stable contracts.

## Acceptance and CI decisions

GitHub Actions may be disabled by the operator. When Actions are disabled, missing workflow runs are not a project-code failure.

The workflow may run `bash scripts/run_full_ci_tests.sh` when enabled, but it should not upload test artifacts unless explicitly requested. Job logs are enough for CI log visibility in this project.

`bash scripts/run_full_ci_tests.sh` is the local closed-loop test runner. It seeds fixture runtime data under `${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}` and runs the normal product tests.

`bash scripts/run_acceptance.sh` is a compatibility entrypoint and delegates to the same runner.

Static acceptance reports must distinguish:

```text
code issue
policy/documentation issue
test coverage gap
runtime evidence gap
CI not run because Actions disabled
```

## Verification

```bash
cd ~/infoscreen
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 -m pytest
bash scripts/run_full_ci_tests.sh
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/assets/js/dashboard.js | grep -n "market-arrow"
find . -maxdepth 1 -type f \( ! -name "README.md" ! -name "AGENTS.md" ! -name "AGENT.md" ! -name "metadata.json" ! -name "pyproject.toml" ! -name ".gitignore" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
find surface -maxdepth 3 -type f -name "*.py" | sort
```
