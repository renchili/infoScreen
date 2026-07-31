# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread, the correct implementation boundary, and the evidence needed to accept a repair. It is organised by product requirement rather than conversation history.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display requires decorative CRT noise, scanlines, a dot grid, or a repeating pixel background.

### Why it fails

Those effects compete with information and reduce readability on an always-on display.

### Correct requirement interpretation

TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear boundaries, and a quiet background.

### Required implementation

Use typography, hierarchy, alignment, borders, and state presentation rather than decorative noise. The dashboard background must not add a full-screen repeating pattern.

### Acceptance evidence

Static CSS evidence must contain no full-screen scanline or repeating-grid overlay. Browser evidence must show readable content at the target display size and no pattern obscuring text.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can act as a second Calendar client, any Python runtime can export EventKit, or a stale Schedule failure can be repaired from the Surface alone.

### Why it fails

macOS Calendar/EventKit owns accounts, permissions, and authoritative event state. A Python runtime without `import EventKit` cannot export Calendar data. The Surface only receives the published JSON and cannot explain a Mac-side permission, configuration, SSH, upload, or launch failure by itself.

### Correct requirement interpretation

Calendar follows EventKit -> Mac export -> temporary remote upload -> atomic remote rename -> Surface runtime JSON -> browser. Failure diagnosis begins on the Mac at the exact failed stage.

### Required implementation

Probe an EventKit-capable Python, keep machine settings in uncommitted `mac/local.env`, and publish to `~/infoscreen/surface/.env/schedule.json` through a temporary file in the same remote directory. `mac/sync_schedule.sh` must start logging before it reads machine configuration, record each stage, validate local JSON, verify the remotely published JSON, and write:

```text
~/Library/Logs/infoscreen-sync/push_schedule.log
~/Library/Logs/infoscreen-sync/schedule_sync_status.json
```

Use the first failed stage as the repair boundary:

- `load configuration`: rerun the setup script and restore `mac/local.env`;
- `export EventKit schedule`: repair Calendar permission or the configured EventKit Python;
- `ensure Surface runtime directory`, `upload temporary schedule`, or `publish schedule atomically`: repair SSH identity, host reachability, user, or remote path;
- `verify published schedule`: repair the remote file, JSON format, or Surface Python/runtime path.

### Acceptance evidence

Show an unattended LaunchAgent run, a current Mac log entry ending in `sync ok`, an `OK` local status JSON, a changed Surface file, current HTTP modification time, valid JSON, and visible Calendar output.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

A red Sync ticker, one generic online indicator, or manually refreshing the browser explains why data failed and how to repair it.

### Why it fails

The ticker reports a symptom, not the failed producer stage. Producer refresh, browser data reload, visual rotation, dashboard filtering, and operator-state refresh are different operations. A producer may retain old content, a service may exit unsuccessfully, a runtime file may be invalid, or HTTP may serve a different file than the producer wrote.

### Correct requirement interpretation

Diagnosis must compare four layers in order: producer result and logs, runtime JSON contents and timestamps, HTTP response and `Last-Modified`, then browser rendering. The Calendar board rotates every seven seconds but reloads Schedule independently. Weather and Market are produced together but must expose separate success or failure fields.

### Required implementation

Run `scripts/infoscreen_status.sh` first. Its output must include producer `Result` and exit status, recent journal excerpts, runtime file age and mtime, JSON validity, `status`, `error`, `updated_at`, `last_attempt_at`, `last_success_at`, and the HTTP payload served for Schedule, Weather, and Market.

Weather failure must preserve the last successful `updated_at`, add a new `last_attempt_at`, retain `last_success_at`, record the exception, emit a timestamped failure line, and return a non-zero producer result. A stale cached payload must not erase the distinction between the last successful data and the latest failed attempt.

For a Schedule failure, inspect the Mac log and status JSON above. For a Weather failure, use the status script to identify whether the timer/service, provider request, runtime JSON, HTTP layer, or browser is the first failing layer. Repair that layer, run the documented producer or sync command again, then confirm both the file and HTTP timestamps advance.

### Acceptance evidence

A forced Weather provider failure must leave the previous successful data timestamp intact, record a later attempt timestamp and exact error, and produce a failed service result. A Schedule configuration, export, SSH, upload, publish, or verification failure must identify its stage in the Mac log. Successful recovery must advance the runtime and HTTP timestamps and update the visible card without a whole-page reload.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, recursive crawler, or generic search scraper.

### Why it fails

Official sites differ in rendering, expansion, APIs, detail fields, pagination, anti-bot behavior, and timing.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official institutions, allowed domains, configured list URLs, and adapter behavior. A rendered card on an official list proves membership.

### Required implementation

Render and expand each configured list, isolate activity cards with one official detail URL and a usable title, then enrich those cards from detail pages through `surface/local_events_runtime/`.

### Acceptance evidence

For an affected organisation, evidence must include a real collector run, list-card evidence, diagnostics, final runtime JSON, and visible output.

## Local Events listing-date authority

### Easy-to-make interpretation

A list card should be rejected unless it already contains a date.

### Why it fails

Correct official Event lists may show only an image, title, category, and detail link. Date and venue may exist only on the detail page.

### Correct requirement interpretation

The official list proves membership. Date and venue can be obtained after admission by following the card's official detail link.

### Required implementation

Do not require a list-card date. Preserve listing evidence, follow the detail URL, and show exact detail status and errors.

### Acceptance evidence

A date-less list card with one official detail link must be admitted and enriched from its detail page.

## Local Events manual correct-list-page entry

### Easy-to-make interpretation

The operator can only accept or reject URLs discovered by the system, or a correct URL must be added by editing committed configuration.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entrypoint that cannot be discovered reliably.

### Correct requirement interpretation

The Studio lets the user select one global institution, enter a correct official Event list URL, save it into review state as pending, review that page, and use the same confirmed-page collection flow as discovered pages.

### Required implementation

Provide an always-visible URL field and `ADD LIST PAGE` button. Send `source_id` and `url` to `POST /api/local-events/review/listing-page`. Validate the configured institution and its allowed domains. Save the page as `pending`; do not collect automatically and do not edit committed `event_sources.json`.

### Acceptance evidence

Add a valid allowed-domain URL and observe it immediately in the list-page review. Invalid institution, malformed URL, and disallowed domain must return HTTP `400` without changing review state.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves activity intent.

### Why it fails

Facilities, memberships, promotions, and navigation records can be event-shaped or typed as Events.

### Correct requirement interpretation

Positive event intent means membership in the correct official activity list. Structured data and detail pages cannot independently create output rows.

### Required implementation

Require rendered official list evidence and match enrichment back to that card. Do not replace this positive authority with title blacklists.

### Acceptance evidence

Reject unmatched typed Event objects and accept matched enrichment without adding title blacklists.

## Local Events zero-result diagnostics

### Easy-to-make interpretation

A zero count can be displayed as `no Events returned` without explaining the failed extraction stage.

### Why it fails

The operator cannot distinguish a load failure from unrecognized detail routes, card-boundary failure, selector failure, or detail-page failure.

### Correct requirement interpretation

Every attempted list page produces a diagnostic tied to that exact canonical URL and reports the first failed stage.

### Required implementation

Persist and display HTTP status, visible links, allowed-domain links, possible detail links, extracted and admitted cards, DOM evidence, selectors, candidates, detail results, and `debug_by_source` completion evidence.

### Acceptance evidence

A zero-result collection must show a stable `reason_code`, reason text, stage counts, and sample detail links when available.

## Local Events HTTP/2 handling

### Easy-to-make interpretation

The collector should first try normal Chromium HTTP/2 navigation, catch `ERR_HTTP2_PROTOCOL_ERROR`, then retry with another browser or protocol.

### Why it fails

That approach doubles navigation behavior, complicates diagnostics, and still starts every collection with the known failing protocol.

### Correct requirement interpretation

The supported collection entrypoints disable HTTP/2 before Chromium launches. No HTTP/2-first request and no protocol retry loop should occur.

### Required implementation

Apply `surface/local_events_runtime/http1_browser.py` before importing collection code in both `surface/serve_infoscreen.py` and `surface/search_local_events.py`. Every patched Chromium launch must include `--disable-http2`.

### Acceptance evidence

Runtime process evidence must show `--disable-http2` on Studio collection and scheduled or HTTP-triggered Local Event collection.

## Generated helper and archive boundary

### Easy-to-make interpretation

A browser interaction requirement can be solved by generating a ZIP, asking the user to extract it, and loading an unpacked Chrome extension.

### Why it fails

This adds an unrequested generated deliverable and installation workflow, violates repository artifact constraints, and changes the product boundary.

### Correct requirement interpretation

Do not generate a ZIP, extension bundle, helper archive, or extra installation flow unless the user explicitly requests it.

### Required implementation

Remove the ZIP builder, download button, extension files, remote feedback transport, and installation documentation. Until an accepted design exists, the Studio states that Ability 2 is not implemented.

### Acceptance evidence

Repository search and the rendered Studio contain no active helper-download control, extension source directory, ZIP-building JavaScript, or remote helper submission route.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every completed crawl should replace the primary file.

### Why it fails

Failure can occur at page access, expansion, card discovery, detail enrichment, date parsing, normalization, or budget. A smaller partial run can erase valid results.

### Correct requirement interpretation

Runtime output includes explicit per-source completion states and evidence. A smaller partial run does not replace a larger verified collector snapshot.

### Required implementation

Record per-source evidence, calculate partial coverage from source completion states, preserve the producer-owned collector snapshot when required, retain `local_event_search_results.partial.json`, and rebuild the kiosk primary from the retained snapshot plus current Review decisions.

### Acceptance evidence

Tests and runtime evidence must cover verified-to-partial transitions, timed-out sources with retained `debug_by_source`, retained collector rows, and reapplication of confirmed or rejected Review decisions.

## Local Events Review publication and kiosk authority

### Easy-to-make interpretation

The Studio can display corrected fields while the kiosk continues rendering a separate collector row, or a preview may temporarily rewrite unrelated decisions and restore them later.

### Why it fails

That creates multiple visible truths and makes Review state vulnerable to interruption.

### Correct requirement interpretation

Review state and collector output may be stored separately, but the kiosk primary is one deterministic projection. Preview and collection read confirmed pages without temporarily changing unrelated decisions.

### Required implementation

Persist producer output to `local_event_collector_results.json`. Build `local_event_search_results.json` from that clean snapshot plus current Review decisions after every accepted producer run and Event decision.

### Acceptance evidence

Confirmed Review fields must override matching stale collector fields, rejected candidates must suppress matching rows, reset must restore the clean collector row, and preview source must contain no temporary list-decision writes.

## Dashboard Local Events filtering and collection boundary

### Easy-to-make interpretation

The kiosk card's filter control should submit displayed text as a new collection location and run the collector.

### Why it fails

Collection is an expensive producer operation that opens official pages and rewrites runtime state. It is not an immediate filter over the rows already displayed.

### Correct requirement interpretation

The dashboard filter operates only on the current `local_event_search_results.json` payload. Collection remains a timer-driven or explicit API operation outside the kiosk filter.

### Required implementation

Load current rows with `GET /api/local-events/search`, retain the unfiltered row set in browser memory, populate institution choices from current rows, and apply institution and text filters locally. Reapply active filters after periodic GET reloads.

### Acceptance evidence

Pressing `FILTER` must cause no collection POST. Clearing both controls must restore all current rows, and a later GET refresh must keep the active filter applied.

## Validation boundaries

### Easy-to-make interpretation

Static review or a successful fixture test proves live sources, services, SSH, LAN access, timers, and visible UI all work.

### Why it fails

Offline checks cannot prove current reachability, live provider behavior, process state, file publication, or browser rendering.

### Correct requirement interpretation

Static inspection, offline tests, live producer runs, service execution, file and HTTP evidence, and visible UI acceptance are separate evidence levels.

### Required implementation

Tie each claim to the exact revision and actual command, log, runtime file, HTTP response, process state, screenshot, or interaction. Use the status script and producer-specific logs instead of inferring success from a green page or an old runtime file.

### Acceptance evidence

A final acceptance record states the exact revision, checks run, checks not run, remaining gaps, and a verdict no stronger than the evidence. Without live-source and device evidence, the affected behavior remains partially verified.
