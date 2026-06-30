# InfoScreen implementation questions and resolution log

This document records implementation issues, user-confirmed constraints, mistakes found during development, and the resolution plan.

Use this file for interaction/problem history. Do not use it as the API spec or architecture document.

## User-confirmed documentation split

The active documentation set must be:

```text
metadata.json        all project requirements, constraints, plan, and cleanup backlog
README.md            how to use, install, start, verify, and troubleshoot
docs/api-spec.md     endpoint interactions and request/response contracts
docs/design.md       whole-project design
docs/questions.md    implementation questions, mistakes, and solutions
```

No other `docs/*.md` files should remain as active documentation.

## Confirmed hard constraints

```text
1. Do not guess runtime paths.
2. schedule.json current target is ~/infoscreen/schedule.json unless verified otherwise.
3. Surface HTTP logs must continue writing under surface/.env/logs/.
4. Mac schedule sync must not depend on a Surface frontend/crawler branch.
5. Frontend assets must be normalized under surface/web/assets/css and surface/web/assets/js.
6. serve_infoscreen.py must not inject CSS, patch HTML, or replace JS versions as a normal solution.
7. Runtime files, logs, pycache, and local data must not be destroyed by git cleanup.
8. Local event source registry must not contain listing/detail/ticket/aggregator URLs.
9. event_sources.json owns verified listing entrypoints.
10. No Qwen/OCR/VLM/large local model in the default local-event extraction path.
11. No hidden fallback to old crawler or fake data.
```

## Mistakes found in this branch

### 1. Runtime path was guessed incorrectly

Problem:

```text
Docs and Mac schedule-sync changes claimed the Surface should read:
~/infoscreen/surface/.env/schedule.json
```

User-provided audit showed the fresh runtime schedule file at:

```text
~/infoscreen/schedule.json
```

Resolution:

```text
1. metadata.json records ~/infoscreen/schedule.json as the current runtime contract.
2. Future path changes require curl + sha256 verification before code/doc changes.
3. Mac sync docs are folded into README.md and docs/design.md instead of a separate docs/mac-schedule-sync.md file.
```

Verification command:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

### 2. Mac sync changes were mixed into a Surface branch

Problem:

```text
Mac schedule-sync files were changed on fix/local-event-one-card, a Surface frontend/local-event branch.
```

Why this is wrong:

```text
1. The Mac checkout may not have or need that Surface branch.
2. Mac schedule export is operationally independent from Surface frontend/crawler work.
3. It makes deployment instructions unsafe.
```

Resolution:

```text
Mac changes should be delivered as a mac-only patch or as local mac/local.env configuration.
Do not require Mac to checkout a Surface branch.
```

### 3. Frontend assets became duplicated

Problem:

Current tree contains both:

```text
surface/web/assets/css/*.css
surface/web/assets/js/*.js
surface/web/*.css
surface/web/*.js
root-level market_custom.css
root-level market_custom.js
```

Resolution plan:

```text
1. Keep checked-in CSS only in surface/web/assets/css/.
2. Keep checked-in JS only in surface/web/assets/js/.
3. Update index.html to reference assets only.
4. Delete duplicate surface/web/*.css|*.js and root market_custom files in a dedicated cleanup.
```

### 4. Server was used as a frontend patch layer

Problem:

```text
serve_infoscreen.py was modified to inject CSS and replace JS version strings.
```

Why this is wrong:

```text
1. It hides source-level frontend problems.
2. It makes the served page different from the checked-in page.
3. It complicates debugging and violates separation of concerns.
```

Resolution plan:

```text
1. Fix source HTML/CSS/JS directly.
2. Remove CSS injection and script replacement from serve_infoscreen.py.
3. Keep serve_infoscreen.py limited to HTTP/API/static serving.
```

### 5. File logging was broken or stopped

Problem:

User reported Surface logs stopped after local files were removed/changed. Audit found existing log files under:

```text
~/infoscreen/surface/.env/logs/http.log
~/infoscreen/surface/.env/logs/http.err.log
```

but they were no longer being written.

Resolution plan:

```text
1. Restore infoscreen-http.service append logging.
2. Keep logs under surface/.env/logs/.
3. Do not remove file logging during unrelated changes.
```

Expected systemd settings:

```ini
StandardOutput=append:%h/infoscreen/surface/.env/logs/http.log
StandardError=append:%h/infoscreen/surface/.env/logs/http.err.log
```

### 6. Destructive git operations were suggested without runtime backup

Problem:

Commands like `git reset --hard` were suggested while runtime files and logs existed inside the working checkout.

Resolution:

Before destructive operations on Surface:

```bash
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
```

Do not use `git clean -fd` on a deployed Surface checkout without explicit backup and review.

## Current implementation questions

### Q1. Should schedule runtime remain at repo root?

Current answer:

```text
Yes, keep ~/infoscreen/schedule.json for now because that is the user-confirmed current target.
```

Open condition:

```text
Only change this through a separate migration that updates server, Mac sync, docs, and verification commands together.
```

### Q2. How should frontend assets be cleaned?

Current answer:

```text
Canonical target is surface/web/assets/css and surface/web/assets/js.
```

Pending work:

```text
1. Check which duplicate files are actually referenced.
2. Move/merge content if needed.
3. Update index.html references.
4. Delete duplicates in one cleanup commit.
5. Verify browser behavior.
```

### Q3. Should local event frontend be one-card or compact-list?

Current answer:

```text
The one-card large layout caused overflow and poor information density.
The immediate recovery direction is compact rows that show multiple items and keep buttons small.
```

Pending work:

```text
Verify actual browser rendering after asset cleanup. Do not keep patching via serve_infoscreen.py.
```

### Q4. When can the local-events timer be re-enabled?

Current answer:

```text
Only after extractor output is verified and the timer cannot overwrite manual debugging unexpectedly.
```

Verification:

```bash
python3 surface/search_local_events.py "Punggol Singapore"
python3 -m json.tool <runtime-local-event-json> | head -n 120
systemctl --user list-timers --all | grep -i infoscreen || true
```

### Q5. Should OCR/VLM be added for event cards?

Current answer:

```text
No default OCR/VLM. Optional OCR can be considered later only behind explicit configuration.
```

### Q6. Where should systemd files live?

Current answer:

```text
deploy/systemd/user/ is canonical.
```

Pending work:

```text
Do not extend surface/systemd/. Migrate or remove legacy systemd locations in cleanup.
```

## Immediate resolution plan

```text
1. Finish documentation reset: metadata.json, README.md, api-spec, design, questions.
2. Add/repair .gitignore for runtime files, logs, pycache, and schedule.json.
3. Restore HTTP file logging in deploy/systemd/user/infoscreen-http.service.
4. Normalize frontend assets to surface/web/assets/.
5. Remove serve_infoscreen.py frontend patching.
6. Restore Mac schedule docs/scripts to target ~/infoscreen/schedule.json.
7. Verify /schedule.json, HTTP logs, and frontend rendering on Surface.
8. Continue local event extraction quality work only after repo structure is stable.
```

## Do not claim yet

Do not claim any of these until verified on the Surface host:

```text
1. schedule sync is restored
2. HTTP logs are restored
3. frontend layout is fixed
4. local event extraction quality is fixed
5. duplicate assets are removed
6. serve_infoscreen.py is clean
7. docs are fully consistent beyond this documentation reset
```
