# InfoScreen project structure and development constraints

This document is the canonical project structure and development-boundary document. If another document disagrees with this file, fix the other document instead of guessing or adding another convention.

## Current verified runtime conventions

These paths reflect the current Surface deployment state and must not be changed without an explicit migration plan and verification commands.

```text
~/infoscreen/schedule.json                  # calendar schedule consumed by /schedule.json
~/infoscreen/surface/.env/logs/http.log     # local HTTP stdout log
~/infoscreen/surface/.env/logs/http.err.log # local HTTP stderr log
```

Do not claim a runtime path is correct unless it has been verified on the Surface host. The minimum verification for `schedule.json` is:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

If another candidate path is suspected, compare its hash with `/tmp/served_schedule.json` before changing scripts or docs.

## Repository layout

```text
repo root
├── deploy/
│   ├── scripts/                  # install/update scripts only
│   └── systemd/user/             # canonical user systemd unit templates
├── docs/                         # documentation; this file is the structure source of truth
├── mac/                          # macOS calendar export/sync only
├── sample/                       # sample JSON fixtures only
├── scripts/                      # repo/dev/status scripts
├── surface/                      # Surface app implementation
│   ├── *.py                      # runtime Python entrypoints and APIs
│   ├── conf/                     # checked-in app configuration
│   ├── local_events_adapters/
│   ├── local_events_runtime/
│   └── web/
│       ├── index.html            # static shell, resource references only
│       └── assets/
│           ├── css/              # all checked-in CSS
│           └── js/               # all checked-in browser JS
├── schedule.json                 # local runtime calendar file, not a source asset
└── README.md
```

## Canonical static asset locations

All checked-in frontend CSS and browser JS must live under:

```text
surface/web/assets/css/
surface/web/assets/js/
```

`surface/web/index.html` should reference only those asset locations, for example:

```html
<link rel="stylesheet" href="assets/css/app.css">
<link rel="stylesheet" href="assets/css/calendar_board.css">
<link rel="stylesheet" href="assets/css/local_events.css">
<link rel="stylesheet" href="assets/css/market_custom.css">

<script src="assets/js/calendar_board.js"></script>
<script src="assets/js/local_events.js"></script>
<script src="assets/js/market_custom.js"></script>
```

Do not add or keep duplicate checked-in frontend assets at these locations:

```text
surface/web/calendar_board.css
surface/web/calendar_board.js
surface/web/local_events.css
surface/web/local_events.js
surface/web/market_custom.css
surface/web/market_custom.js
market_custom.css
market_custom.js
```

## `serve_infoscreen.py` boundaries

`surface/serve_infoscreen.py` is an HTTP/API/static-file server. It must not be used as a frontend patch layer.

Allowed responsibilities:

```text
1. serve index.html and static files
2. expose JSON/API endpoints
3. read explicitly documented runtime files
4. run explicitly requested backend refresh commands
```

Forbidden responsibilities:

```text
1. injecting CSS into index.html
2. replacing script URLs or cache-busting versions at runtime
3. patching HTML structure at serve time
4. guessing or silently changing runtime paths
5. hiding frontend debt by modifying served HTML dynamically
```

Any legacy runtime HTML cleanup must be removed through a normal source change, not by a permanent server-side regex patch.

## Runtime files and logs

Runtime/generated files are local deployment state. They must be protected before destructive git operations and must not be treated as source assets.

Current known runtime/log locations:

```text
schedule.json
surface/.env/
surface/.env/logs/
surface/.env/logs/http.log
surface/.env/logs/http.err.log
```

Before running any destructive command such as `git reset --hard`, `git clean`, file deletion, or branch replacement on a deployed Surface host, create a local backup:

```bash
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
```

Do not run `git clean -fd` on a deployed Surface checkout unless the runtime backup has been made and reviewed.

## Logging requirement

The HTTP service must continue writing local file logs unless a documented migration replaces them. The expected files are:

```text
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

The user systemd unit should include append-style log targets equivalent to:

```ini
StandardOutput=append:%h/infoscreen/surface/.env/logs/http.log
StandardError=append:%h/infoscreen/surface/.env/logs/http.err.log
```

Do not remove local file logging as part of unrelated frontend, crawler, schedule, or docs work.

## macOS schedule sync boundary

The Mac side is only responsible for exporting Apple Calendar through EventKit and copying `schedule.json` to the Surface host.

The Mac side must not depend on the Surface frontend branch. Do not instruct the Mac checkout to switch to a Surface feature branch just to pick up schedule-sync changes.

Current Surface target for the schedule file is:

```text
~/infoscreen/schedule.json
```

If schedule sync code changes are needed, put them in a mac-only patch or cherry-pick only the `mac/` and related docs changes. Do not mix Mac schedule-sync changes with Surface frontend/crawler changes.

## systemd boundaries

The canonical systemd templates live under:

```text
deploy/systemd/user/
```

Install/update helpers live under:

```text
deploy/scripts/
```

Do not create new competing systemd locations. Existing legacy locations such as `surface/systemd/` should not be extended; migrate or remove them in a dedicated cleanup.

## Generated files and pycache

The repository must not track generated Python cache files or runtime data:

```text
__pycache__/
*.pyc
surface/**/__pycache__/
surface/.env/
schedule.json
```

If these appear in a working tree, remove or ignore them in a dedicated cleanup commit. Do not mix cleanup with behavior changes.

## Documentation rules

1. Do not document guessed paths.
2. Do not document a migration before it is implemented and verified.
3. Do not leave two docs with conflicting structure or runtime paths.
4. If a path is environment-specific, say how to verify it instead of presenting it as universal.
5. `docs/project-structure.md` is the source of truth for structure and boundaries.

## Change-scope rules

Use separate commits/branches for separate concerns:

```text
frontend layout/static assets
local event crawler/data quality
schedule sync
systemd/logging/deploy
OpenAPI/API schema
documentation-only changes
repo structure cleanup
```

Do not mix Mac sync changes, Surface frontend changes, crawler changes, service logging changes, and docs rewrites in one patch unless the change is explicitly a repository-wide cleanup and all runtime files have been backed up first.
