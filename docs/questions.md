# InfoScreen decisions

This file records durable project decisions.

Entries use this shape:

- Decision: accepted project direction.
- Rationale: why the direction was chosen.
- Consequence: what changes for code, tests, docs, or operations.
- Verification: how the decision can be checked.

When implementation or test feedback changes project direction, record the resulting decision and rationale. Temporary execution notes belong outside this file.

## Repository root and source layout

Decision: the repository root is reserved for repository control, documentation, metadata, CI/test configuration, and operator/deployment entrypoints.

Rationale: source files, local runtime data, personal data, generated output, caches, and compiled files need clear separation.

Consequence: allowed root-level paths are README, AGENTS, AGENT, metadata, pyproject, gitignore, githooks, github workflows, docs, skills, surface, deploy, mac, scripts, and tests. Browser assets live under `surface/web/assets`. Runtime data lives under `surface/.env`. Fixtures live under `tests/fixtures`.

Verification: root contents, ignore rules, and pre-commit rules match AGENT.md and README.md.

## Frontend entrypoints

Decision: `surface/web/index.html` is the dashboard shell and checked-in browser files are loaded from `surface/web/assets`.

Rationale: one shell plus one asset tree keeps the kiosk frontend simple and prevents stale duplicate entrypoints.

Consequence: root-level JavaScript/CSS and direct `surface/web` JavaScript/CSS are not active dashboard assets.

Verification: dashboard HTML references assets under `surface/web/assets`.

## Runtime data

Decision: runtime JSON, logs, generated photo indexes, and local photo input live under `surface/.env`.

Rationale: these files are local machine state, not source code.

Consequence: runtime data is ignored by git and is not committed. Local photo input lives under `surface/.env/photos`.

Verification: runtime jobs and dashboard empty states point to `~/infoscreen/surface/.env` paths.

## Python roles

Decision: Python files are grouped by role: HTTP server/API support, refresh jobs, local-event implementation, and static frontend.

Rationale: separating long-running serving code from refresh jobs keeps operations clear.

Consequence: `surface/serve_infoscreen.py` owns local HTTP serving; refresh jobs remain standalone commands; `openapi_spec.py` and `api_models.py` support the API contract.

Verification: compile checks and import tests cover these modules.

Decision: the canonical local event implementation path is `search_local_events.py` to `jobs.local_event_search` to `local_events_runtime`.

Rationale: one active local event path keeps behavior traceable.

Consequence: a new local event engine is only added when this path is intentionally replaced.

Verification: local event refresh and tests route through that path.

## Test model

Decision: use pytest for backend, frontend contract, CSS contract, runtime fixture, HTTP closed-loop, and script/workflow tests.

Rationale: pytest provides deterministic local tests that run without external services.

Consequence: tests use committed fixture JSON and isolated runtime directories.

Verification: `python3 -m pytest` and `bash scripts/run_full_ci_tests.sh` run the local closed-loop suite.

Decision: repository hygiene is enforced through source layout rules, ignore rules, commit guard, and verification commands.

Rationale: product tests should focus on product behavior and stable contracts.

Consequence: broad file-tree policy belongs in repository policy and commit guards, not in product behavior tests.

Verification: review root policy docs, ignore rules, commit guard, and verification commands when source layout changes.

## Acceptance and CI decisions

Decision: GitHub Actions may be disabled by the operator.

Rationale: hosted CI availability is an operator setting, separate from source readiness.

Consequence: missing workflow runs are not a project-code failure when Actions are disabled.

Verification: acceptance reports mark disabled Actions as not run or out of scope.

Decision: the workflow may run `scripts/run_full_ci_tests.sh` when enabled, but does not upload test artifacts unless requested.

Rationale: local and CI job logs are the evidence surface unless downloadable artifacts are requested.

Consequence: workflow configuration has no artifact upload by default.

Verification: inspect the acceptance workflow when CI behavior changes.
