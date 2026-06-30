# InfoScreen decision rationale

This document explains the design decisions that affect implementation. It records the current choice, why the project uses it, how to verify it, what alternatives exist, and when the choice can change.

## D1. Schedule runtime location

**Decision.** `schedule.json` is runtime state, not a source file. It belongs under the Surface runtime directory:

```text
~/infoscreen/surface/.env/schedule.json
```

The repository root must not contain a committed `schedule.json`. The only checked-in schedule fixture is `sample/schedule.json`.

**Reason.** The schedule is produced outside the Surface app by macOS calendar export and consumed by the Surface HTTP server. It changes over time and can contain personal calendar data, so it should live with runtime data, not beside source files in the repo root.

**How to judge.** `GET /schedule.json` is correct only when it returns the same content as the runtime file under `surface/.env/`.

```bash
cd ~/infoscreen
curl -s http://127.0.0.1:8765/schedule.json -o /tmp/served_schedule.json
sha256sum /tmp/served_schedule.json ~/infoscreen/surface/.env/schedule.json
```

**Alternatives.** Keeping `schedule.json` in the repo root is easier to type, but it mixes runtime data with source files and makes accidental commits more likely. Moving all runtime state outside the repo can be considered later as a broader runtime-layout migration.

**Change condition.** The path can change only when the Mac sync target, Surface HTTP reader, README, API docs, and verification commands are changed together.

## D2. Mac schedule sync boundary

**Decision.** macOS schedule sync is owned by `mac/` scripts and local `mac/local.env` configuration.

**Reason.** The Mac only exports Apple Calendar and copies the resulting JSON to the Surface runtime path. It does not need Surface frontend, crawler, or service files to perform that role.

**How to judge.** A Mac checkout with `mac/export.py`, `mac/sync_schedule.sh`, `mac/local.env`, and SSH access can update `~/infoscreen/surface/.env/schedule.json` on the Surface host.

**Alternatives.** Requiring Mac and Surface checkouts to use the same feature branch couples two different deployment roles and makes calendar sync depend on unrelated Surface work.

**Change condition.** Change only if the deployment model becomes single-host and Mac export no longer runs independently.

## D3. Frontend asset location

**Decision.** Checked-in CSS lives under `surface/web/assets/css/`. Checked-in browser JavaScript lives under `surface/web/assets/js/`.

**Reason.** One canonical asset location makes it clear which frontend files the dashboard loads.

**How to judge.** `surface/web/index.html` references `assets/css` and `assets/js` only for checked-in CSS and JavaScript.

```bash
grep -RIn "calendar_board\|local_events\|market_custom" surface/web/index.html
find surface/web -maxdepth 2 -type f | sort
```

**Alternatives.** Keeping assets directly under `surface/web/` can work, but keeping both `surface/web/` and `surface/web/assets/` copies creates ambiguity.

**Change condition.** Change only if the whole frontend asset layout is migrated together with `index.html` references.

## D4. HTTP server responsibility boundary

**Decision.** `surface/serve_infoscreen.py` serves static files and API responses. Frontend layout and behavior belong in HTML, CSS, and JavaScript source files.

**Reason.** A clear server/frontend boundary makes browser behavior match checked-in frontend files and keeps source review reliable.

**How to judge.** `serve_infoscreen.py` does not inject CSS, rewrite script URLs, or transform dashboard HTML as normal behavior.

```bash
grep -RIn "inject\|replace(.*calendar_board\|local-event-inline-script\|cleaned" surface/serve_infoscreen.py || true
```

**Alternatives.** Response-time HTML rewriting is acceptable only as temporary compatibility code with a removal condition. It should not be the normal design.

**Change condition.** Temporary compatibility logic must be removed after the source files express the intended frontend behavior.

## D5. HTTP file logs

**Decision.** `infoscreen-http.service` writes stdout to `surface/.env/logs/http.log` and stderr to `surface/.env/logs/http.err.log`.

**Reason.** The Surface deployment needs simple local debugging from the checkout directory in addition to systemd journal access.

**How to judge.** The user service contains append log targets and the files receive new lines after service restart or HTTP requests.

```bash
systemctl --user cat infoscreen-http.service
tail -n 40 ~/infoscreen/surface/.env/logs/http.log
tail -n 40 ~/infoscreen/surface/.env/logs/http.err.log
```

**Alternatives.** Journald-only logging, `/var/log`, or an external runtime directory are all logging migrations and must update service files, README commands, and status checks together.

**Change condition.** Change only through a dedicated logging migration.

## D6. Runtime file protection

**Decision.** Runtime files under `surface/.env/` are local deployment state and are not committed.

**Reason.** Runtime files can contain local machine state, private calendar data, logs, and generated JSON. They are not reproducible from Git.

**How to judge.** `.gitignore` excludes runtime data, and source changes do not rely on committing files from `surface/.env/`.

**Alternatives.** Committing runtime files would make local/private data part of source history. Moving runtime files outside the repo is possible later as a separate runtime layout migration.

**Change condition.** If runtime files move to a dedicated runtime root outside the repo, update the server paths, service files, Mac sync target, README, and verification commands together.

## D7. Local event quality metric

**Decision.** Local event quality is judged by extracted fields, not by source count.

**Reason.** Useful output requires correct title, date, venue, source, URL, and summary. Adding more sources does not improve quality if field extraction is wrong.

**How to judge.** For each source, debug output shows cards found, accepted count, rejection reasons, and sample results with correct fields.

```bash
python3 surface/search_local_events.py "Punggol Singapore"
curl -s http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 160
```

**Alternatives.** Adding more sources first, using third-party aggregators, or adding OCR/VLM by default can hide extraction defects or add unnecessary dependencies before the official DOM path is proven insufficient.

**Change condition.** After field quality is verified, source expansion can be considered using verified official listing entrypoints only.

## D8. Local event refresh timing

**Decision.** Local event refresh should be timer-driven only after extractor output is verified.

**Reason.** A timer-controlled output file should represent trusted periodic data, not an unstable validation run.

**How to judge.** Manual search output is reviewed first. Timer refresh is enabled only after the output contract is stable.

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

**Alternatives.** Keeping the timer always enabled makes output ownership unclear during validation. Separate manual and timer outputs are a larger runtime-output design change.

**Change condition.** Enable the timer after extractor quality and output ownership are verified.

## D9. OCR and VLM scope

**Decision.** Default local event extraction uses browser-rendered DOM, not OCR, VLM, or a large local model.

**Reason.** The default path should be deterministic, lightweight, and explainable. OCR/VLM should not be required unless official sources expose important event data only inside images.

**How to judge.** If title, date, venue, and detail URL are available in DOM text or structured attributes, DOM extraction should handle the source.

**Alternatives.** Optional OCR or VLM can be added later for verified image-only official sources.

**Change condition.** Add optional OCR only behind explicit configuration and only for sources that cannot be extracted from DOM content.

## Open decisions

1. Should local events filter by geographic relevance or show all official events?
2. Should local event debug screenshots be cleaned automatically?
3. Should Python dependencies be managed through `requirements.txt`, `pyproject.toml`, or README commands?
4. What refresh cadence should local-events use after output is verified?
5. Should legacy local event engine/adapters remain after rendered DOM extraction is stable?
6. Should runtime JSON files remain under `surface/.env/` or migrate to a single runtime root outside the repo?
