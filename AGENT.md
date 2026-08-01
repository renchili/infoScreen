# InfoScreen Project-Specialized Agent Rules

This file is the InfoScreen-specific specialization of `AGENTS.md`.

It is generated from the bootstrap rules, the user's current requirements and corrections, the product plan, and current repository evidence. It must describe the intended InfoScreen architecture. It must not copy the current file tree into an allowlist and then use that allowlist to prove the current tree is correct.

## Rule interpretation

Apply this order when resolving project-specific facts:

1. explicit user requirements and corrections;
2. the InfoScreen product intent in `metadata.json` and clarified requirements in `docs/questions.md`;
3. architecture and ownership evidence in `docs/design.md`, source, configuration, deployment definitions, and active callers;
4. this generated project specialization;
5. the current repository layout as evidence of implementation state only.

When this file conflicts with a stronger item above, the conflicting rule is a generation error. Do not use it to reject the correction. Correct this file and every enforcement or documentation owner that repeats the same error.

## Required reading order

Before planning or editing repository files, read:

1. `AGENTS.md`;
2. `AGENT.md`;
3. `skills/SKILL.md`;
4. `skills/full-project-acceptance-hard-gates` when validating or accepting the full project;
5. `README.md`;
6. `metadata.json`;
7. `docs/design.md`, `docs/api-spec.md`, and `docs/questions.md`;
8. relevant source, tests, scripts, deployment files, CI workflows, and configuration.

## Project identity

InfoScreen is a local-first kiosk dashboard whose primary runtime host is a Surface or Ubuntu device. A Mac is authoritative only for macOS Calendar/EventKit export and Schedule publication.

The checkout root is `~/infoscreen`. Do not create another project root.

## Ownership model

Top-level organization follows runtime and platform ownership, not generic file function.

### Surface or Ubuntu ownership

Everything used specifically to build, run, configure, deploy, operate, or verify the Surface runtime belongs under `surface/`, including:

- the HTTP server, jobs, runtime libraries, committed configuration, and browser frontend;
- systemd units and the Surface installer;
- Surface operator and diagnostic scripts;
- Surface-specific tests, fixtures, and test configuration;
- compatibility entrypoints required by installed Surface callers.

### Mac ownership

Everything used specifically for macOS Calendar/EventKit belongs under `mac/`, including:

- EventKit export;
- Schedule synchronization and LaunchAgent setup;
- Mac-specific scripts;
- Mac-specific tests, fixtures, and test configuration.

### Repository-wide ownership

Repository-wide material may remain outside device directories only when it genuinely applies to the whole repository:

- project overview and metadata;
- architecture, API, and requirement documentation;
- agent rules and reusable skills;
- Git and GitHub control files;
- CI workflow orchestration, repository contract tests, and CI-only helpers.

A file is not repository-wide merely because it is a test, script, installer, configuration file, or deployment file.

## Repository root policy

The intended root is deliberately small:

```text
README.md
AGENTS.md
AGENT.md
metadata.json
.gitignore
.githooks/
.github/
docs/
skills/
surface/
mac/
```

Do not create generic root-level source or ownership buckets such as:

```text
deploy/
scripts/
tests/
pyproject.toml
```

unless a future explicit project decision establishes that they are genuinely repository-wide and updates this rule, the project plan, enforcement, documentation, and callers together.

### Completed ownership migration

The historical root ownership buckets were removed and their contents were classified by active owner:

```text
deploy/ Surface systemd and installer content
  -> surface/deploy/

scripts/ Surface operational content
  -> surface/scripts/

scripts/ CI-only content
  -> .github/scripts/

tests/ Surface tests and fixtures
  -> surface/tests/

tests/ Mac tests
  -> mac/tests/

repository-wide contract tests
  -> .github/tests/

root pytest configuration
  -> .github/pytest.ini
```

The obsolete duplicate `scripts/setup_surface_go.sh` was removed rather than preserved under a new name.

The migration also updated workflows, installers, test discovery, documentation, `.gitignore`, `.githooks/pre-commit`, and repository path checks. Do not restore compatibility copies at the old root paths. New files must be placed directly with their Surface, Mac, CI, or genuinely repository-wide owner.

## Runtime-state boundary

Runtime and personal state belongs under:

```text
surface/.env/
```

Runtime JSON, machine-local configuration, logs, debug captures, local photos, generated photo output, caches, compiled files, and test artifacts are not source code and must not be committed.

Local photo inputs belong under `surface/.env/photos/`.

Generated test reports, logs, JUnit XML, coverage output, and similar artifacts belong in `${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}` or another ignored local artifact path.

## Surface runtime model

`surface/serve_infoscreen.py` is the local HTTP server. It serves static files and JSON/API endpoints. It must not patch dashboard HTML, inject CSS or JavaScript, or rewrite frontend asset URLs.

The canonical Surface architecture is:

```text
surface/serve_infoscreen.py          local HTTP server and route handling
surface/jobs/                        one-shot job orchestration
surface/jobs/local_event_search.py   Local Events job entrypoint
surface/local_events_runtime/        canonical Local Events collection and extraction library
surface/conf/                        committed configuration
surface/web/                         static frontend
surface/deploy/                      Surface systemd units and installer
surface/scripts/                     Surface operator and diagnostic scripts
surface/tests/                       Surface test definitions and fixtures
surface/.env/                        uncommitted runtime and personal state
```

`surface/local_events_runtime/` is intentional and canonical. Do not create a duplicate `surface/jobs/local_events/` implementation. A future package move requires an explicit migration that updates imports, compatibility wrappers, systemd and HTTP callers, tests, README, design, and repository rules together.

Compatibility wrappers may remain at `surface/*.py` only while current systemd units, scripts, or HTTP subprocess calls require those paths.

## Frontend model

The dashboard entrypoint is:

```text
surface/web/index.html
```

Active browser assets belong under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

Do not restore direct `surface/web/*.js` or `surface/web/*.css` as active entrypoints. Do not keep stale compatibility placeholders for removed frontend files.

## Mac model

The Mac is authoritative only for Calendar/EventKit:

```text
macOS Calendar/EventKit
  -> Mac export and sync code under mac/
  -> SSH/SCP temporary publication and atomic rename
  -> surface/.env/schedule.json
```

The Surface does not generate Calendar data. Mac-specific tests and setup logic belong under `mac/`, not in a generic root test or script directory.

## Test model

Use `pytest` for Python unit and contract tests, but locate tests by owner.

Surface categories belong under `surface/tests/`, for example:

```text
surface/tests/test_backend_*.py
surface/tests/test_frontend_*.py
surface/tests/test_style_*.py
surface/tests/test_scripts_*.py
surface/tests/fixtures/
```

Mac Schedule and LaunchAgent tests belong under `mac/tests/`.

Repository-wide path, documentation, and workflow contract tests belong under `.github/tests/`. Shared pytest discovery and marker configuration belongs in `.github/pytest.ini`.

Tests must not require external network access. Tests that need runtime data must use committed fixtures and copy them into a temporary or ignored runtime directory.

A shared test label or shared runner does not justify mixing platform-owned tests in a root `tests/` directory.

## Jobs

A job is a Python command that refreshes or generates runtime state and exits.

Surface jobs include the supported entrypoints for live data, News, Photos, and Local Events. Local Events orchestration belongs in `surface/jobs/local_event_search.py`. Source-specific collection, extraction, browser handling, normalization, and evidence logic belong in `surface/local_events_runtime/`. Keep `surface/search_local_events.py` as a compatibility wrapper while installed callers require it.

## API support

`surface/openapi_spec.py` and `surface/api_models.py` support `/openapi.json` and `/docs`.

They are not jobs or runtime JSON. If `/openapi.json` and `/docs` are removed, remove the support modules and server routes together.

## Logging and command output

This local systemd-user-service project permits concise operational stdout and stderr:

- systemd captures service and producer output;
- short-lived producers may emit concise start, completion, skip, and failure lines;
- `surface/jobs/local_event_search.py` may emit its final JSON command result to stdout;
- the standard-library HTTP server may emit request diagnostics and a concise startup line.

Structured JSON logs, request IDs, trace IDs, and an additional logging framework are not current product requirements. Output must remain free of credentials, tokens, full request bodies, private file contents, and unnecessary personal data.

A future logging redesign must update implementation, tests, `docs/design.md`, and this rule together.

## Refactor and migration rules

Before moving files:

1. identify every active caller, import, workflow, installer, test, and documentation reference;
2. classify each file by Surface, Mac, CI, or genuine repository-wide ownership;
3. define the complete file-level move set;
4. preserve compatibility only for external installed callers that cannot move atomically;
5. update path enforcement and documentation in the same change set;
6. do not leave placeholders or duplicate old and new owners;
7. do not describe a partially migrated layout as complete.

## Validation and execution boundary

`skills/SKILL.md` currently governs repository generation and repair as static-only work. Under that workflow, agents must not run project code, tests, repository scripts, services, browsers, deployments, or CI.

Commands shown in README, workflow files, or operator documentation are command inventory and future evidence paths; their presence is not permission for an agent to execute them.

Only report checks actually run under an explicitly applicable and authorized workflow. Static inspection must never be described as runtime, test, browser, device, deployment, or CI acceptance.

When paths are migrated, update every documented and automated command that refers to the old paths.

## Final response

For repository work, include:

- exact files changed;
- branch name;
- commits created;
- static inspection performed;
- commands, tests, services, browsers, deployments, and CI not run;
- remaining migration, runtime, or acceptance gaps.
