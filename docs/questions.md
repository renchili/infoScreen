# InfoScreen implementation questions and issues

This document tracks project-level implementation questions, known issues, decisions, and pending resolutions.

It must stay project-focused. It must not record assistant-specific mistakes, conversation blame, or personal postmortem notes.

## Active documentation set

```text
metadata.json        project requirements, constraints, plan, and cleanup backlog
README.md            usage, install, start, verify, and troubleshooting
docs/api-spec.md     endpoint interactions and request/response contracts
docs/design.md       concrete system design contracts
docs/questions.md    implementation questions, known issues, decisions, and pending resolutions
```

No other `docs/*.md` files should remain as active documentation.

## Confirmed project constraints

```text
1. Runtime paths require verification on the running Surface host before being changed.
2. Current schedule target is ~/infoscreen/schedule.json unless a verified migration changes it.
3. Surface HTTP logs must continue writing under surface/.env/logs/.
4. Mac schedule sync must remain independent from Surface frontend/crawler branches.
5. Frontend assets must be normalized under surface/web/assets/css and surface/web/assets/js.
6. serve_infoscreen.py must not inject CSS, patch HTML, or replace JS versions as normal behavior.
7. Runtime files, logs, pycache, and local data must not be removed by source cleanup.
8. Local event source registry must not contain listing/detail/ticket/aggregator URLs.
9. event_sources.json owns verified listing entrypoints.
10. No Qwen/OCR/VLM/large local model in the default local-event extraction path.
11. No hidden fallback to old crawler or placeholder data.
```

## Known implementation issues

### I1. Runtime schedule path alignment

Issue: Mac sync, Surface server, frontend, and docs must agree on the schedule file path.

Current decision: keep the current verified target at `~/infoscreen/schedule.json`.

Resolution: any future path migration must update server code, Mac sync configuration, docs, and verification commands in one dedicated migration.

### I2. Mac schedule sync branch boundary

Issue: Mac calendar export must not depend on an unrelated Surface feature branch.

Current decision: Mac schedule sync must be deployable from `mac/` files and local `mac/local.env` configuration only.

Resolution: deliver Mac sync changes as a mac-only patch or local configuration change.

### I3. Duplicated frontend assets

Issue: the browser can load old JS/CSS from `surface/web` while newer files exist under `surface/web/assets/`.

Current target:

```text
surface/web/assets/css/*.css
surface/web/assets/js/*.js
```

Pending cleanup:

```text
1. Check current index.html references.
2. Move or merge required content into assets/.
3. Update index.html to reference assets only.
4. Delete duplicate surface/web/*.css|*.js and root market_custom files.
5. Verify served HTML and browser rendering.
```

### I4. HTTP server frontend patching

Issue: server-side HTML/CSS/JS patching can make the served dashboard differ from checked-in source files.

Current target: `serve_infoscreen.py` serves files and APIs only. Source HTML/CSS/JS should contain the actual frontend fix.

Pending cleanup: remove CSS injection, script URL replacement, and HTML patching from `serve_infoscreen.py` after source files are normalized.

### I5. HTTP file logging

Issue: the HTTP service can continue running while local file logs stop being written.

Current required log files:

```text
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

Required systemd settings:

```ini
StandardOutput=append:%h/infoscreen/surface/.env/logs/http.log
StandardError=append:%h/infoscreen/surface/.env/logs/http.err.log
```

### I6. Runtime data protection during source cleanup

Issue: runtime files live inside the deployed checkout, so source cleanup must not remove local runtime state.

Required backup scope before cleanup:

```text
schedule.json
surface/.env/
```

### I7. Local event extraction quality

Issue: source count can increase while actual title/date/venue extraction remains poor.

Current decision: fix card rendering, pagination, date/venue splitting, and debug output before expanding source count.

### I8. Local-events timer overwrites manual debugging

Issue: a timer refresh can overwrite manual local event output during debugging.

Current decision: keep local-events timer disabled until extraction output is verified.

### I9. Optional OCR/VLM scope

Issue: adding OCR/VLM by default increases dependencies and hides extractor logic problems.

Current decision: no default OCR/VLM. Optional OCR can be considered later only behind explicit configuration.

## Open implementation questions

```text
1. Should local events eventually filter by geographic relevance or show all official events?
2. Should local event debug screenshots be automatically cleaned up?
3. Should Python dependencies be managed through requirements.txt, pyproject.toml, or docs-only commands?
4. Should local-events refresh cadence be manual, hourly, daily, or on-login plus daily after quality is verified?
5. Should legacy local event engine/adapters be removed after rendered DOM extraction is stable?
6. Should runtime JSON files other than schedule.json remain under surface/.env/ or be migrated consistently?
```

## Resolution order

```text
1. Keep docs project-only.
2. Add/repair .gitignore for runtime files, logs, schedule.json, pycache, and pyc.
3. Restore/verify HTTP file logging.
4. Normalize frontend assets to surface/web/assets/.
5. Remove serve_infoscreen.py frontend patching.
6. Keep schedule sync aligned to ~/infoscreen/schedule.json.
7. Verify /schedule.json, HTTP logs, and frontend rendering on Surface.
8. Continue local event extraction quality work after repo structure is stable.
```

## Acceptance criteria

```text
1. docs/ contains only api-spec.md, design.md, and questions.md.
2. metadata.json is valid JSON and contains the active cleanup plan.
3. README starts the project from a clean checkout and from systemd.
4. /schedule.json matches the verified Surface schedule file.
5. HTTP service writes http.log and http.err.log.
6. Browser static assets are referenced only through surface/web/assets/.
7. Runtime files and generated files are ignored by git.
```
