# InfoScreen implementation questions and project risks

This document tracks project-level implementation questions, risks, decisions, and pending resolutions. It must not record assistant-specific mistakes or conversation blame.

## Active documentation set

```text
metadata.json        project requirements, constraints, plan, and cleanup backlog
README.md            usage, install, start, verify, and troubleshooting
docs/api-spec.md     endpoint interactions and request/response contracts
docs/design.md       concrete system design contracts
docs/questions.md    project questions, risks, decisions, and pending resolutions
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
7. Runtime files, logs, pycache, and local data must not be destroyed by git cleanup.
8. Local event source registry must not contain listing/detail/ticket/aggregator URLs.
9. event_sources.json owns verified listing entrypoints.
10. No Qwen/OCR/VLM/large local model in the default local-event extraction path.
11. No hidden fallback to old crawler or fake data.
```

## Project risks and pending resolutions

### R1. Runtime schedule path drift

Risk:

```text
Mac sync, Surface server, frontend, and docs can drift if schedule.json path is changed in only one place.
```

Current decision:

```text
Keep the current verified target at ~/infoscreen/schedule.json.
```

Required verification:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

Resolution path:

```text
Any future path migration must update server code, Mac sync configuration, docs, and verification commands in one dedicated migration.
```

### R2. Mac schedule sync branch coupling

Risk:

```text
Mac calendar export can become coupled to an unrelated Surface feature branch.
```

Current decision:

```text
Mac schedule sync must be deployable from mac/ files and local mac/local.env configuration only.
```

Resolution path:

```text
Deliver Mac sync changes as a mac-only patch or local configuration change. Do not require the Mac checkout to switch to a Surface frontend/crawler branch.
```

### R3. Duplicated frontend assets

Risk:

```text
The browser can load old JS/CSS from surface/web root while newer files exist under surface/web/assets/.
```

Current target:

```text
surface/web/assets/css/*.css
surface/web/assets/js/*.js
```

Pending cleanup:

```text
1. Check current index.html references.
2. Move or merge any required content into assets/.
3. Update index.html to reference assets only.
4. Delete duplicate surface/web/*.css|*.js and root market_custom files.
5. Verify served HTML and browser rendering.
```

### R4. HTTP server frontend patching

Risk:

```text
Server-side HTML/CSS/JS patching can make the served dashboard differ from checked-in source files.
```

Current target:

```text
serve_infoscreen.py serves files and APIs only. Source HTML/CSS/JS should contain the actual frontend fix.
```

Pending cleanup:

```text
Remove CSS injection, script URL replacement, and HTML patching from serve_infoscreen.py after source files are normalized.
```

### R5. HTTP file logging regression

Risk:

```text
The HTTP service can continue running while local file logs stop being written.
```

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

Verification:

```bash
systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log
```

### R6. Runtime data loss during cleanup

Risk:

```text
Runtime files live inside the deployed checkout, so destructive git commands can damage local runtime state if used carelessly.
```

Required backup before destructive operations:

```bash
cd ~/infoscreen
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
echo "$backup"
```

### R7. Local event extraction quality

Risk:

```text
Source count can increase while actual title/date/venue extraction remains poor.
```

Current decision:

```text
Fix card rendering, pagination, date/venue splitting, and debug output before expanding source count.
```

Verification:

```bash
python3 surface/search_local_events.py "Punggol Singapore"
python3 - <<'PY'
import json
from pathlib import Path
candidates = [
    Path('surface/.env/local_event_search_results.json'),
    Path('local_event_search_results.json'),
]
for p in candidates:
    if p.exists():
        d=json.load(open(p))
        print('file=', p)
        print('extractor=', d.get('extractor'))
        print('source_count=', d.get('source_count'))
        print('count=', d.get('count'))
        for src in d.get('debug_by_source', []):
            print('\nSOURCE:', src.get('source'))
            print('cards=', src.get('cards_found'), 'accepted=', src.get('accepted'))
            print('reasons=', src.get('reason_counts'))
        for x in d.get('results', [])[:20]:
            print('\nTITLE:', x.get('title'))
            print('WHEN :', x.get('when'))
            print('WHERE:', x.get('where'))
            print('SRC  :', x.get('source_name'))
        break
else:
    print('local event runtime file not found')
PY
```

### R8. Local-events timer overwrites manual debugging

Risk:

```text
A timer refresh can overwrite manual local event output during debugging.
```

Current decision:

```text
Keep local-events timer disabled until extraction output is verified.
```

Verification:

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

### R9. Optional OCR/VLM scope

Risk:

```text
Adding OCR/VLM by default increases dependencies and hides extractor logic problems.
```

Current decision:

```text
No default OCR/VLM. Optional OCR can be considered later only behind explicit configuration.
```

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
1. Finish docs reset and keep docs project-only.
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
