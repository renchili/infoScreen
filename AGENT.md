# InfoScreen Agent Rules

This is the project-specific rule file for agents working on `renchili/infoScreen`.

## Read order

Before planning or editing repository files, read:

1. `AGENTS.md`
2. `AGENT.md`
3. `skills/SKILL.md`
4. `skills/full-project-acceptance-hard-gates` when validating or accepting the full project
5. `README.md`
6. `metadata.json`
7. `docs/design.md`, `docs/api-spec.md`, and `docs/questions.md`
8. relevant source, tests, scripts, deploy files, CI workflows, and configs

## Project identity

InfoScreen is a local kiosk dashboard for a Surface or Ubuntu display.

The repository root is `~/infoscreen`. Do not create another project root.

## Repository root policy

The repository root is for repository control, documentation, project metadata, CI, test configuration, and operator/deployment entrypoints only.

Do not place dashboard runtime JSON, local environment files, browser CSS, browser JavaScript, local photos, generated output, caches, or compiled files in the repository root.

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

Runtime JSON belongs under `surface/.env/`.

Browser CSS and JavaScript belong under `surface/web/assets/`.

Local photo inputs belong under `surface/.env/photos/`.

Test fixtures belong under `tests/fixtures/`. Test reports, logs, JUnit XML, and other generated artifacts must be written to `${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}` or another ignored local artifact path, not committed.

The local commit guard is `.githooks/pre-commit`. Keep it aligned with this policy and document setup commands when changing it.

Do not replace removed root or legacy static files with placeholders.

## Documentation locations

Project documentation belongs in:

```text
README.md
metadata.json
docs/design.md
docs/api-spec.md
docs/questions.md
AGENTS.md
AGENT.md
skills/SKILL.md
skills/full-project-acceptance-hard-gates
```

Do not add nested source-directory README files such as `surface/README.md` unless the user explicitly asks for one.

## Runtime model

Runtime state belongs under:

```text
surface/.env/
```

Runtime state is not source code.

`surface/serve_infoscreen.py` is the local HTTP server. It serves static files and JSON/API endpoints. It must not patch dashboard HTML, inject CSS, inject JavaScript, or rewrite frontend asset URLs.

## Frontend model

The dashboard HTML entrypoint is:

```text
surface/web/index.html
```

Active browser assets must live under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

Do not restore root-level `surface/web/*.js` or `surface/web/*.css` as active dashboard entrypoints.

Do not keep stale compatibility placeholders for removed frontend files.

## Python model

Python code under `surface/` is organized by role.

The current canonical architecture is:

```text
surface/serve_infoscreen.py          local HTTP server and route handling
surface/jobs/                        one-shot job orchestration
surface/jobs/local_event_search.py   Local Events job entrypoint
surface/local_events_runtime/        canonical Local Events collection and extraction library
surface/conf/                        committed configuration
surface/web/                         static frontend
```

`surface/local_events_runtime/` is intentional and canonical. Do not create a duplicate `surface/jobs/local_events/` implementation. A future package move requires an explicit migration that updates imports, compatibility wrappers, systemd and HTTP callers, tests, README, design, and repository rules in one change set.

Compatibility wrappers may remain at `surface/*.py` only when current systemd units, scripts, or HTTP subprocess calls depend on those paths.

## Test model

Use `pytest` for unit and contract tests.

Required test categories:

```text
tests/test_backend_*.py       backend/API/schema/runtime JSON unit tests
tests/test_frontend_*.py      frontend DOM/content contract tests
tests/test_style_*.py         CSS/layout contract tests
tests/test_scripts_*.py       shell/script/CI entrypoint tests
tests/fixtures/               closed-loop fixture data
```

Tests must not require external network access. When a test needs runtime data, use committed fixtures and copy them into a temporary or ignored runtime directory.

## Jobs

A job is a Python command that refreshes or generates runtime state and exits.

Jobs include:

```text
fetch_live_data.py
fetch_event_stream.py
build_photos_json.py
search_local_events.py
```

Local Events orchestration belongs in `surface/jobs/local_event_search.py`. Source-specific collection, extraction, browser handling, normalization, and evidence logic belong in `surface/local_events_runtime/`. Keep `surface/search_local_events.py` as a compatibility wrapper while existing callers need it.

## API support

`openapi_spec.py` and `api_models.py` are support modules for `/openapi.json` and `/docs`.

They are not dashboard runtime files and not jobs.

If `/openapi.json` and `/docs` are removed, remove these modules and their server routes together.

## Logging and command-output model

The generic logging contract in `skills/SKILL.md` is narrowed for this local, systemd-user-service project.

- systemd captures stdout and stderr for the HTTP service and producer jobs;
- short-lived producer jobs may emit concise human-readable start, completion, skip, and failure lines to stdout or stderr;
- `surface/jobs/local_event_search.py` may emit the final JSON payload to stdout because that is a deliberate command result consumed by callers, not a log record;
- the standard-library HTTP server may use `SimpleHTTPRequestHandler` request diagnostics and a concise startup line;
- structured JSON logs, request IDs, trace IDs, and an additional logging framework are not current product requirements;
- output must remain free of credentials, tokens, full request bodies, private file contents, and unnecessary personal-data values;
- do not describe deliberate command results as ad-hoc logging, and do not replace machine-readable command output with log formatting;
- a future logging redesign must update implementation, tests, `docs/design.md`, and this rule together.

This repository-specific boundary intentionally accepts concise stdout/stderr operation output. Do not weaken or broaden it implicitly in individual files.

## Refactor rules

Before moving files:

1. identify active callers and imports.
2. provide a file-level change set.
3. keep compatibility wrappers for existing external callers.
4. update docs and verification commands in the same change set.
5. avoid placeholders and unrelated cleanup.

## Validation

Report only checks actually run.

Useful checks:

```bash
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 -m json.tool metadata.json >/tmp/infoscreen-metadata.json
python3 - <<'PY'
from surface.openapi_spec import build_openapi
build_openapi()
PY
python3 -m pytest
find . -maxdepth 1 -type f \( ! -name "README.md" ! -name "AGENTS.md" ! -name "AGENT.md" ! -name "metadata.json" ! -name "pyproject.toml" ! -name ".gitignore" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
git diff --cached --name-only | .githooks/pre-commit
find surface -maxdepth 3 -type f -name "*.py" | sort
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/openapi.json >/tmp/infoscreen-openapi.json
bash scripts/run_acceptance.sh
ACCEPTANCE_START_SERVER=1 bash scripts/run_acceptance.sh
```

When paths change, update the compile command.

## Final response

For repository work, include:

- exact files changed.
- branch name.
- commits created.
- checks run.
- checks not run.
- remaining evidence gaps or risks.

Use the conclusion format from `skills/SKILL.md`.
