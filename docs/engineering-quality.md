# Engineering Quality Gate

InfoScreen uses three separate environments. These environments must not be mixed.

## 1. Environment roles

### Mac developer environment

The Mac is the normal development machine.

Allowed on Mac:

- edit code
- run lightweight checks
- create commits
- open pull requests
- optionally run Docker if available

Recommended Mac check:

    bash ci/mac_check.sh

### GitHub Actions environment

GitHub Actions is the full automated quality gate.

The GitHub runner is only allowed to:

1. check out the repository
2. build the CI Docker image
3. run the full gate inside Docker

The canonical GitHub CI command is:

    docker build -f ci/Dockerfile -t infoscreen-ci .
    docker run --rm -v "$PWD:/repo" -w /repo infoscreen-ci bash ci/run_all.sh

All full checks must run inside the Docker image. The CI must not rely on the GitHub runner's preinstalled Python, Node, shell tools, or package versions.

### Surface simulation environment

The Surface is a simulation and visual acceptance device, not a CI runner.

Surface responsibilities:

- run the dashboard through systemctl
- simulate the real always-on display environment
- validate the actual small-screen UI
- validate behavior with real runtime JSON files
- validate the systemctl service shape used by deployment

Surface must not be used for automated CI execution.

Do not use these as deployment or test commands on Surface:

- python3 serve_infoscreen.py
- python3 -m http.server
- docker run
- Docker-based checks
- ad-hoc long-running test servers

Surface validation is manual runtime acceptance under systemctl only.

## 2. Surface systemctl contract

The Surface service contract is fixed:

    WorkingDirectory=%h/infoscreen
    ExecStart=/usr/bin/python3 %h/infoscreen/serve_infoscreen.py

The systemd user service is the only runtime entry point for Surface.

The expected service name is:

    infoscreen-http.service

The expected deployment action on Surface is:

    git pull --ff-only origin main
    systemctl --user restart infoscreen-http.service

No documentation should recommend starting the HTTP service manually with Python.

## 3. Runtime files

Runtime data must not be committed.

Forbidden tracked files and folders include:

- schedule.json
- weather.json
- market.json
- event_stream.json
- local_event_search_results.json
- photos.json
- index2.html
- logs/
- photos/
- public_photos/
- *.bak
- *.bak.*

These files may exist on Surface, but they are local runtime state.

## 4. CI gate coverage

The Docker quality gate must check at least these areas:

### Repository hygiene

- runtime files are not tracked
- backup files are not tracked
- local machine paths are not tracked
- private IP addresses are not committed
- obvious secrets are not committed
- temporary generated files are not committed

### Python quality

- Python files compile
- critical static errors fail the build
- tests run under pytest
- API contracts are covered
- runtime cache files created by tests are restored or deleted after tests

### JavaScript and HTML quality

- external JavaScript files pass node --check
- inline scripts extracted from index.html pass node --check
- index.html keeps required dashboard regions
- local-event is not reduced to a single hardcoded item
- forbidden stale UI strings are rejected

### API contract

The local-event API contract must cover:

- GET /api/local-events/search
- POST /api/local-events/search
- result object shape
- cache read behavior
- generated result compatibility with the frontend

### UI contract

index.html must keep the required regions:

- market
- local-event
- local-event form
- local-event input
- local-event list
- event stream
- photo wall
- weather
- metrics
- calendar
- bottom status area

Local-event changes must preserve:

- multiple items
- carousel or rotation behavior
- source display
- date or date fallback display
- title display
- runtime JSON loading

## 5. Local-event change rule

Local-event changes are full-stack changes unless proven otherwise.

A local-event PR should normally include changes or checks for:

- index.html
- serve_infoscreen.py
- search_local_events.py
- tests for API contract
- tests for UI contract
- fixture data or generated sample results

A frontend-only local-event change is not enough when the API response shape or generated JSON shape is involved.

A backend-only local-event change is not enough when the rendered UI behavior may change.

## 6. Documentation quality

README and docs must explain:

- install
- run
- deployment
- test
- troubleshooting
- privacy
- runtime file policy
- Surface simulation role
- GitHub Docker gate
- Mac lightweight check

Documentation must not contain conflicting deployment paths.

Forbidden documentation patterns:

- python3 -m http.server as deployment
- python3 serve_infoscreen.py as Surface deployment
- Surface described as a CI runner
- Docker required on Surface

## 7. Pull request quality

Every PR must make its scope clear.

Feature PRs should not include CI refactors.

CI PRs should not include feature changes.

Runtime JSON files must not be part of any PR.

Before merge, Files changed must be reviewed for scope drift.

## 8. Recovery rule

When a UI feature breaks, do not patch production index.html directly.

Required recovery flow:

1. create a clean branch from origin/main
2. create or update tests first
3. use fixtures to reproduce the broken behavior
4. implement the fix
5. run Mac lightweight checks
6. let GitHub Docker CI run full checks
7. deploy to Surface only after merge or after an explicit simulation branch is chosen
8. validate visually on Surface through systemctl

Surface is used for simulation acceptance, not as a substitute for CI.
