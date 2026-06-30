# InfoScreen decision rationale

This document explains why the project uses its current implementation choices, how each choice is judged, which alternatives were considered, and when a choice may be changed.

It must stay project-focused. It must not record assistant-specific mistakes, conversation blame, or personal postmortem notes.

## Active documentation set

```text
metadata.json        project requirements, constraints, plan, and cleanup backlog
README.md            usage, install, start, verify, and troubleshooting
docs/api-spec.md     endpoint interactions and request/response contracts
docs/design.md       concrete system design contracts
docs/questions.md    decision rationale, judgment criteria, alternatives, and change conditions
```

No other `docs/*.md` files should remain as active documentation.

## Decision format

Each decision should answer:

```text
Decision: what the project currently does.
Reason: why this is the current choice.
How to judge: what evidence shows the choice is correct.
Alternatives: what else was considered.
Change condition: when the decision may be changed.
Verification: exact command or observable result where applicable.
```

## D1. Schedule file stays at repo root

Decision:

```text
The Surface schedule file is currently ~/infoscreen/schedule.json.
```

Reason:

```text
The running dashboard exposes /schedule.json. The schedule producer on Mac only needs to copy one JSON file to the Surface host. Keeping the current verified target avoids a partial migration where Mac writes one path while the server reads another.
```

How to judge:

```text
The served /schedule.json payload must match ~/infoscreen/schedule.json on the Surface host.
```

Verification:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

Alternatives:

```text
1. Move schedule.json under surface/.env/.
2. Move all runtime JSON files to one runtime directory outside the repo.
```

Why not alternatives now:

```text
Those are migrations. They require server, Mac sync, docs, systemd, and verification updates together. A partial path change breaks calendar sync.
```

Change condition:

```text
Only change through a dedicated runtime-path migration that updates all readers, writers, docs, and verification commands in one patch.
```

## D2. Mac schedule sync is independent from Surface feature branches

Decision:

```text
Mac schedule sync is configured through mac/ scripts and mac/local.env. The Mac checkout must not depend on a Surface frontend or crawler branch.
```

Reason:

```text
The Mac only exports Apple Calendar and copies schedule.json. It does not need Surface frontend, crawler, or systemd changes to do that job.
```

How to judge:

```text
A Mac with mac/export.py, mac/sync_schedule.sh, mac/local.env, and SSH access can update the Surface schedule target without checking out a Surface feature branch.
```

Alternatives:

```text
1. Require both Mac and Surface to checkout the same branch.
2. Put Mac runtime configuration into the shared repo state.
```

Why not alternatives now:

```text
They couple two different deployment roles and make calendar sync depend on unrelated Surface work.
```

Change condition:

```text
Only change if the project becomes a single-machine deployment where Mac export and Surface dashboard run from the same checkout.
```

## D3. Frontend assets live under surface/web/assets

Decision:

```text
Checked-in CSS lives under surface/web/assets/css/.
Checked-in browser JS lives under surface/web/assets/js/.
```

Reason:

```text
One canonical asset location prevents the browser from loading an older root-level JS/CSS file while newer files exist elsewhere.
```

How to judge:

```text
index.html references only assets/css and assets/js for checked-in CSS/JS.
No duplicate checked-in JS/CSS remains at surface/web/*.js, surface/web/*.css, or repo root market_custom.*.
```

Verification:

```bash
grep -RIn "calendar_board\|local_events\|market_custom" surface/web/index.html
find surface/web -maxdepth 2 -type f | sort
```

Alternatives:

```text
1. Keep JS/CSS directly under surface/web/.
2. Keep both root-level and assets-level copies.
```

Why not alternatives now:

```text
Keeping both copies makes it unclear which file the kiosk is running. Direct root-level assets can work, but the project already has assets/ and should converge on one convention.
```

Change condition:

```text
Only change if the whole frontend asset structure is migrated in one cleanup and index.html references are updated at the same time.
```

## D4. serve_infoscreen.py is not a frontend patch layer

Decision:

```text
serve_infoscreen.py serves static files and APIs. It must not inject CSS, rewrite script URLs, or patch HTML as normal behavior.
```

Reason:

```text
Runtime HTML patching makes the served dashboard different from source files and hides which frontend code is actually running.
```

How to judge:

```text
serve_infoscreen.py contains no CSS injection, script URL replacement, or permanent HTML cleanup logic.
```

Verification:

```bash
grep -RIn "inject\|replace(.*calendar_board\|local-event-inline-script\|cleaned" surface/serve_infoscreen.py || true
```

Alternatives:

```text
1. Patch HTML at serve time.
2. Keep duplicate frontend owners and strip one from the response.
```

Why not alternatives now:

```text
They make source review unreliable and create different behavior between file inspection and browser execution.
```

Change condition:

```text
Temporary serve-time compatibility code is allowed only during a documented migration and must include a removal condition.
```

## D5. HTTP logs stay as local files under surface/.env/logs

Decision:

```text
The HTTP service writes stdout to surface/.env/logs/http.log and stderr to surface/.env/logs/http.err.log.
```

Reason:

```text
The Surface deployment needs easy local debugging without relying only on journald retention. File logs also make kiosk runtime problems visible from the repo checkout.
```

How to judge:

```text
The user service contains append log targets and the files receive new lines after service restart or HTTP requests.
```

Verification:

```bash
systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log
```

Alternatives:

```text
1. Use journald only.
2. Move logs to /var/log.
3. Move logs to a runtime directory outside the repo.
```

Why not alternatives now:

```text
They require an explicit logging migration. The current deployment expects local file logs under surface/.env/logs/.
```

Change condition:

```text
Only change through a logging migration that updates systemd units, README troubleshooting, and status scripts together.
```

## D6. Runtime files are protected before source cleanup

Decision:

```text
Before source cleanup on a deployed Surface checkout, back up schedule.json and surface/.env/.
```

Reason:

```text
Runtime files live inside the deployed checkout. Source cleanup can otherwise remove or overwrite local state that is not reproducible from Git.
```

How to judge:

```text
A backup directory exists before cleanup and contains schedule.json and the surface runtime directory when they exist.
```

Verification:

```bash
cd ~/infoscreen
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
find "$backup" -maxdepth 2 -type f -o -type d
```

Alternatives:

```text
1. Keep runtime files inside Git.
2. Ignore runtime state during cleanup.
3. Move all runtime state outside the repo immediately.
```

Why not alternatives now:

```text
Runtime files contain local/private state and should not be committed. Moving runtime state is a separate migration.
```

Change condition:

```text
If runtime state is migrated outside the repo, update this backup scope to the new runtime root.
```

## D7. Local event extraction quality is judged by fields, not source count

Decision:

```text
Improve rendered card extraction, pagination, date/venue splitting, and debug output before expanding source count.
```

Reason:

```text
More sources do not fix bad extraction. The useful output is determined by title, date, venue, source, URL, and readable summary quality.
```

How to judge:

```text
For each source, debug output shows cards found, accepted count, rejection reasons, and sample results with correct title/when/where/source/url fields.
```

Verification:

```bash
python3 surface/search_local_events.py "Punggol Singapore"
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 160
```

Alternatives:

```text
1. Add more sources first.
2. Use third-party aggregators.
3. Use OCR/VLM by default.
```

Why not alternatives now:

```text
They hide extraction quality problems or add unnecessary dependencies. Official rendered DOM extraction should be correct first.
```

Change condition:

```text
After field quality is verified, source expansion can be considered using verified official listing entrypoints only.
```

## D8. Local-events timer remains off during extractor debugging

Decision:

```text
The local-events timer should stay disabled while extractor output is being debugged manually.
```

Reason:

```text
A timer can overwrite manual output and make it unclear which run produced the current result file.
```

How to judge:

```text
Manual search output remains stable until another explicit manual run or API request is made.
```

Verification:

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

Alternatives:

```text
1. Keep timer enabled during debugging.
2. Write manual and timer output to separate files.
```

Why not alternatives now:

```text
The first makes debugging unreliable. The second is a larger runtime-output design change.
```

Change condition:

```text
Re-enable the timer only after extractor quality and output ownership are verified.
```

## D9. OCR/VLM is not part of the default local event path

Decision:

```text
Default local event extraction uses browser-rendered DOM, not OCR/VLM or a large local model.
```

Reason:

```text
The first target is reliable extraction from official web pages. OCR/VLM adds dependencies, runtime cost, and nondeterministic output before the DOM path is proven insufficient.
```

How to judge:

```text
If official pages expose title/date/venue in DOM text or structured attributes, DOM extraction should handle them without OCR/VLM.
```

Alternatives:

```text
1. Add optional OCR for image-only cards.
2. Add VLM extraction for screenshots.
```

Why not alternatives now:

```text
They should be optional extensions, not default dependencies.
```

Change condition:

```text
Add optional OCR only if verified official sources expose important event data only inside images and the feature is explicitly configured.
```

## Open decisions

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
7. Runtime files and generated files are ignored by Git.
```
