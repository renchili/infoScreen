# InfoScreen Agent Rules

This is the project-specific rule file for agents working on `renchili/infoScreen`.

## Read order

Before planning or editing repository files, read:

1. `AGENTS.md`
2. `AGENT.md`
3. `skills/SKILL.md`
4. `README.md`
5. `docs/design.md`, `docs/api-spec.md`, and `docs/questions.md`
6. relevant source, scripts, deploy files, and configs

## Project identity

InfoScreen is a local kiosk dashboard for a Surface or Ubuntu display.

The repository root is `~/infoscreen`. Do not create another project root.

## Repository root policy

The repository root is for repository control and documentation only.

Do not place project code, local environment files, dashboard runtime JSON, browser CSS, browser JavaScript, local photos, generated output, or caches in the repository root.

Allowed root-level project paths:

```text
README.md
AGENTS.md
AGENT.md
.gitignore
.githooks/
docs/
surface/
skills/
```

Runtime JSON belongs under `surface/.env/`.

Browser CSS and JavaScript belong under `surface/web/assets/`.

Local photo inputs belong under `surface/.env/photos/`.

The local commit guard is `.githooks/pre-commit`. Keep it aligned with this policy and document setup commands when changing it.

Do not replace removed root or legacy static files with placeholders.

## Documentation locations

Project documentation belongs in:

```text
README.md
docs/design.md
docs/api-spec.md
docs/questions.md
AGENTS.md
AGENT.md
skills/SKILL.md
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

Python code under `surface/` must be organized by role.

Target architecture:

```text
surface/app/                 server, routes, runtime helpers, API schemas
surface/jobs/                refresh jobs that write surface/.env/*.json
surface/jobs/local_events/   local event search job implementation
surface/conf/                configuration
surface/web/                 static frontend
```

Compatibility wrappers may remain at `surface/*.py` only when current systemd units, scripts, or HTTP subprocess calls depend on those paths.

## Jobs

A job is a Python command that refreshes or generates runtime state and exits.

Jobs include:

```text
fetch_live_data.py
fetch_event_stream.py
build_photos_json.py
search_local_events.py
```

Local events are a job. If refactoring local events, place implementation under `surface/jobs/local_events/` and keep `surface/search_local_events.py` only as a compatibility wrapper while existing callers need it.

## API support

`openapi_spec.py` and `api_models.py` are support modules for `/openapi.json` and `/docs`.

They are not dashboard runtime files and not jobs.

If `/openapi.json` and `/docs` are removed, remove these modules and their server routes together.

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
find . -maxdepth 1 -type f \( ! -name "README.md" ! -name "AGENTS.md" ! -name "AGENT.md" ! -name ".gitignore" \) -print
find surface/web -maxdepth 1 -type f \( -name "*.js" -o -name "*.css" \) -print
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
git diff --cached --name-only | .githooks/pre-commit
find surface -maxdepth 3 -type f -name "*.py" | sort
curl -s http://127.0.0.1:8765/ | grep -E "assets/js/dashboard.js|assets/js/local_event_card.js"
curl -s http://127.0.0.1:8765/openapi.json >/tmp/infoscreen-openapi.json
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
