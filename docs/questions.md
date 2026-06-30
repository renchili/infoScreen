# InfoScreen decision rationale

This document records the project decisions that need an explicit reason. Each entry states the current decision, the reason for it, how to judge whether it is correct, the alternatives, and the condition for changing it.

## D1. Schedule file path

Decision:

```text
The Surface schedule file is ~/infoscreen/schedule.json.
```

Reason:

```text
The schedule has one producer on macOS and one consumer on the Surface dashboard. A single root-level target keeps the Mac copy step and the Surface /schedule.json endpoint aligned.
```

How to judge:

```text
The served /schedule.json payload matches ~/infoscreen/schedule.json on the Surface host.
```

Verification:

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/schedule.json
```

Alternatives:

```text
1. Store schedule.json under surface/.env/.
2. Store all runtime JSON under a separate runtime directory outside the repo.
```

Why not alternatives now:

```text
Both alternatives are runtime-path migrations. They require coordinated changes to the server, Mac sync, documentation, and verification commands.
```

Change condition:

```text
Change only through a dedicated runtime-path migration that updates all readers and writers together.
```

## D2. Mac schedule sync boundary

Decision:

```text
macOS schedule sync is owned by mac/ scripts and local mac/local.env configuration.
```

Reason:

```text
The Mac only exports Apple Calendar and copies schedule.json to the Surface host. It does not need Surface frontend, crawler, or service files to perform that role.
```

How to judge:

```text
A Mac checkout with mac/export.py, mac/sync_schedule.sh, mac/local.env, and SSH access can update the Surface schedule target.
```

Alternatives:

```text
1. Require Mac and Surface checkouts to use the same feature branch.
2. Store Mac runtime configuration in committed repo files.
```

Why not alternatives now:

```text
They couple two different deployment roles and make calendar sync depend on unrelated Surface work.
```

Change condition:

```text
Change only if the deployment model becomes single-host and Mac export no longer runs independently.
```

## D3. Frontend asset location

Decision:

```text
Checked-in CSS lives under surface/web/assets/css/.
Checked-in browser JavaScript lives under surface/web/assets/js/.
```

Reason:

```text
One canonical asset location makes it clear which frontend files the dashboard should load.
```

How to judge:

```text
surface/web/index.html references assets/css and assets/js only for checked-in CSS and JavaScript.
```

Verification:

```bash
grep -RIn "calendar_board\|local_events\|market_custom" surface/web/index.html
find surface/web -maxdepth 2 -type f | sort
```

Alternatives:

```text
1. Keep assets directly under surface/web/.
2. Keep both surface/web/ and surface/web/assets/ copies.
```

Why not alternatives now:

```text
A single convention is easier to verify and avoids ambiguity. The project already has assets/ directories, so assets/ is the target convention.
```

Change condition:

```text
Change only if the whole frontend asset layout is migrated together with index.html references.
```

## D4. HTTP server responsibility boundary

Decision:

```text
surface/serve_infoscreen.py serves static files and API responses. Frontend layout and behavior belong in HTML, CSS, and JavaScript source files.
```

Reason:

```text
A clear server/frontend boundary makes the browser behavior match the checked-in frontend files and keeps source review reliable.
```

How to judge:

```text
serve_infoscreen.py does not inject CSS, rewrite script URLs, or transform dashboard HTML as normal behavior.
```

Verification:

```bash
grep -RIn "inject\|replace(.*calendar_board\|local-event-inline-script\|cleaned" surface/serve_infoscreen.py || true
```

Alternatives:

```text
1. Transform HTML at response time.
2. Keep compatibility rewrites inside the server.
```

Why not alternatives now:

```text
They make the served dashboard different from source files and make frontend behavior harder to audit.
```

Change condition:

```text
Temporary compatibility logic must have a documented removal condition and should not become the normal design.
```

## D5. HTTP file logs

Decision:

```text
infoscreen-http.service writes stdout to surface/.env/logs/http.log and stderr to surface/.env/logs/http.err.log.
```

Reason:

```text
The Surface deployment needs simple local debugging from the checkout directory in addition to systemd journal access.
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
Each alternative is a logging migration and must update service files, README commands, and status checks together.
```

Change condition:

```text
Change only through a dedicated logging migration.
```

## D6. Runtime file protection

Decision:

```text
Before modifying source files on the deployed Surface checkout, preserve schedule.json and surface/.env/ if they exist.
```

Reason:

```text
Those files are local runtime state. They are not reproducible from Git.
```

How to judge:

```text
A backup exists before file layout changes and contains the runtime files that existed at the time.
```

Verification:

```bash
cd ~/infoscreen
backup="$HOME/infoscreen-runtime-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a schedule.json "$backup/" 2>/dev/null || true
cp -a surface/.env "$backup/surface-env" 2>/dev/null || true
find "$backup" -maxdepth 2 -print
```

Alternatives:

```text
1. Commit runtime files.
2. Move runtime files outside the repo.
```

Why not alternatives now:

```text
Runtime files are local state and may contain private data. Moving them outside the repo is a separate runtime layout migration.
```

Change condition:

```text
If runtime files are moved to a dedicated runtime root, update the backup scope to that root.
```

## D7. Local event quality metric

Decision:

```text
Local event quality is judged by extracted fields, not by source count.
```

Reason:

```text
Useful output requires correct title, date, venue, source, URL, and summary. Adding more sources does not improve quality if field extraction is wrong.
```

How to judge:

```text
For each source, debug output shows cards found, accepted count, rejection reasons, and sample results with correct fields.
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
3. Use OCR or VLM by default.
```

Why not alternatives now:

```text
They can hide extraction defects or add unnecessary dependencies before the official DOM path is proven insufficient.
```

Change condition:

```text
After field quality is verified, source expansion can be considered using verified official listing entrypoints only.
```

## D8. Local event refresh timing

Decision:

```text
Local event refresh should be timer-driven only after extractor output is verified.
```

Reason:

```text
A timer-controlled output file should represent trusted periodic data, not an unstable debugging run.
```

How to judge:

```text
Manual search output is reviewed first. Timer refresh is enabled only after the output contract is stable.
```

Verification:

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

Alternatives:

```text
1. Keep the timer always enabled.
2. Write manual and timer output to separate files.
```

Why not alternatives now:

```text
The first makes output ownership unclear during validation. The second is a larger runtime-output design change.
```

Change condition:

```text
Enable the timer after extractor quality and output ownership are verified.
```

## D9. OCR and VLM scope

Decision:

```text
Default local event extraction uses browser-rendered DOM, not OCR, VLM, or a large local model.
```

Reason:

```text
The default path should be deterministic, lightweight, and explainable. OCR/VLM should not be required unless official sources expose important event data only inside images.
```

How to judge:

```text
If title, date, venue, and detail URL are available in DOM text or structured attributes, DOM extraction should handle the source.
```

Alternatives:

```text
1. Add optional OCR for image-only cards.
2. Add VLM extraction for screenshots.
```

Why not alternatives now:

```text
They are optional extensions, not baseline dependencies.
```

Change condition:

```text
Add optional OCR only behind explicit configuration and only for verified image-only official sources.
```

## Open decisions

```text
1. Should local events filter by geographic relevance or show all official events?
2. Should local event debug screenshots be cleaned automatically?
3. Should Python dependencies be managed through requirements.txt, pyproject.toml, or README commands?
4. What refresh cadence should local-events use after output is verified?
5. Should legacy local event engine/adapters remain after rendered DOM extraction is stable?
6. Should runtime JSON files other than schedule.json remain under surface/.env/ or migrate to a single runtime root?
```
