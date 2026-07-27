# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread and the evidence needed to accept their implementation. It is organised by product requirement rather than conversation history.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display requires decorative CRT noise, a dot grid, scanlines, or a pixel wallpaper.

### Why it fails

Those effects compete with information and reduce readability on an always-on display.

### Correct requirement interpretation

TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear boundaries, and a quiet background.

### Required implementation

Use typography, hierarchy, alignment, borders, and state presentation rather than decorative noise. The dashboard background must not add a full-screen repeating pattern.

### Acceptance evidence

Static CSS evidence must contain no active full-screen scanline or repeating-grid overlay. Browser evidence must show readable content at the target display size and no pattern obscuring text.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can act as a second Calendar client, any Python runtime can export EventKit, or copying directly to the final file is safe enough.

### Why it fails

macOS Calendar/EventKit owns accounts, permissions, and authoritative event state. A Python runtime without `import EventKit` cannot export Calendar data. Direct replacement during transfer can expose a partially written JSON file.

### Correct requirement interpretation

Calendar follows EventKit -> Mac export -> temporary remote upload -> atomic remote rename -> Surface runtime JSON -> browser.

### Required implementation

Probe EventKit-capable Python, keep machine settings in uncommitted `mac/local.env`, and publish to `~/infoscreen/surface/.env/schedule.json` through a temporary file in the same remote directory.

### Acceptance evidence

Show unattended LaunchAgent execution, a changed Surface file, current HTTP modification time, visible Calendar output, and a sync script that uploads to a temporary name before publishing the final file.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator, one generic refresh interval, or frequent whole-page rebuilding proves all data is current.

### Why it fails

The server can remain online while individual files are stale, missing, or unreachable. Producer refresh, browser reload, visual rotation, dashboard filtering, isolated preview, persisted collection, and operator-state refresh are different operations.

### Correct requirement interpretation

The Sync ticker observes per-file `Last-Modified`. The Calendar board rotates every seven seconds but reloads Schedule independently. The Local Event Studio refreshes persisted state only on initial load, explicit operations, manual reload, and return to the browser tab.

### Required implementation

Keep per-file freshness checks, reload Schedule without reloading the page, remove idle Studio polling, emit one completed-render event, and restore one stable card anchor or scroll position after that render.

### Acceptance evidence

Leave the Studio idle and during a long operation: it must not flash repeatedly or lose scroll. Static source must not contain `setInterval(loadState, 3000)` or a global timer monkey patch that recognises a magic 3000-millisecond interval.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, recursive crawler, or generic search scraper.

### Why it fails

Official sites differ in rendering, expansion, APIs, detail fields, pagination, anti-bot behaviour, and timing.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official institutions, allowed domains, configured list URLs, and adapter behaviour. A rendered card on an official list proves membership.

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

The official list proves membership. Date and venue can be obtained after admission by following the card’s official detail link.

### Required implementation

Do not require a list-card date. Preserve listing evidence, follow the detail URL, and show exact detail status/errors.

### Acceptance evidence

A date-less list card with one official detail link must be admitted and enriched from its detail page.

## Local Events manual correct-list-page entry

### Easy-to-make interpretation

The operator can only accept or reject URLs discovered by the system, a correct URL must be added by editing committed configuration, or a page must be confirmed before it can be inspected with the collector.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entrypoint. Requiring confirmation before any preview forces the operator to mutate the real decision merely to validate a candidate.

### Correct requirement interpretation

The Studio lets the operator select one global institution, enter a correct official Event list URL, save it as `pending`, preview that one page in isolated temporary state, and separately choose the real list-page decision.

### Required implementation

Provide an always-visible URL field and `ADD LIST PAGE` button. Send `source_id` and `url` to `POST /api/local-events/review/listing-page`. Validate the configured institution and its allowed domains. Save as `pending`; do not edit committed `event_sources.json` and do not run a persisted collection automatically. `PREVIEW EVENTS` sends only `listing_url` to the isolated preview endpoint and must not change the real decision.

Adding the same institution/URL again resets it to `pending`, allowing a rejected or stale decision to be reconsidered.

### Acceptance evidence

Select an institution, add a valid allowed-domain URL, observe it immediately in the left-side list, and preview it while still pending. Verify that the preview returns only that page’s candidates and diagnostics while persisted Review state remains byte-equivalent. Then confirm it and verify that normal confirmed-page collection includes it. Invalid institution, malformed URL, disallowed domain, and unknown preview URL must return HTTP `400` without changing Review state.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves activity intent.

### Why it fails

Facilities, memberships, promotions, and navigation records can be event-shaped or typed as Events. The SAFRA `Carpark Rates` record demonstrated this failure mode.

### Correct requirement interpretation

Positive Event intent means membership in the correct official activity list. Structured data and detail pages cannot independently create output rows.

### Required implementation

Require rendered official list evidence and match enrichment back to that card. Do not replace this positive authority with title blacklists.

### Acceptance evidence

Reject unmatched typed Event objects and accept matched enrichment without adding title blacklists. Preserve the SAFRA facility regression case.

## Local Events zero-result diagnostics

### Easy-to-make interpretation

A zero count can be displayed as “no Events returned” without explaining the failed extraction stage.

### Why it fails

The operator cannot distinguish a load failure from unrecognised detail routes, card-boundary failure, selector failure, or detail-page failure.

### Correct requirement interpretation

Every attempted list page produces a diagnostic tied to that exact canonical URL and reports the first failed stage.

### Required implementation

Return HTTP status, visible links, allowed-domain links, possible detail links, extracted/admitted cards, DOM evidence, selectors, candidates, and detail results. Normal collection persists diagnostics; isolated preview returns temporary diagnostics without replacing persisted state.

### Acceptance evidence

A zero-result normal collection and a zero-result isolated preview must both show a stable `reason_code`, reason text, stage counts, and sample detail links when available.

## Local Events HTTP/2 handling

### Easy-to-make interpretation

The collector should first try normal Chromium HTTP/2 navigation, catch `ERR_HTTP2_PROTOCOL_ERROR`, then retry with another browser or protocol.

### Why it fails

That approach doubles navigation behaviour, complicates diagnostics, and still starts every collection with the known failing protocol.

### Correct requirement interpretation

Supported collection entrypoints disable HTTP/2 before Chromium launches. No HTTP/2-first request and no protocol retry loop should occur.

### Required implementation

Apply `surface/local_events_runtime/http1_browser.py` before importing collection code in both server and scheduled/HTTP wrappers. Every patched Chromium launch must include `--disable-http2`, including isolated preview.

### Acceptance evidence

Runtime launch evidence must show `--disable-http2` on Studio discovery, isolated preview, normal Review collection, and scheduled/HTTP-triggered collection. A failing navigation must be reported directly, not hidden behind a first-attempt/retry sequence.

## Generated helper and archive boundary

### Easy-to-make interpretation

A browser interaction requirement can be solved by generating a ZIP, asking the user to extract it, and loading an unpacked Chrome extension.

### Why it fails

This adds an unrequested generated deliverable and installation workflow, violates repository artifact constraints, and changes the product boundary.

### Correct requirement interpretation

Do not generate a ZIP, extension bundle, helper archive, or extra installation flow unless explicitly requested.

### Required implementation

Keep the ZIP builder, download button, extension files, remote `feedback:` transport, and helper submission route removed. Until an accepted interaction design exists, the Studio states that Ability 2 is not implemented.

### Acceptance evidence

Repository search and the rendered Studio contain no active helper-download control, extension source directory, ZIP-building JavaScript, or remote helper submission route. No archive is generated at runtime.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every completed crawl should replace the primary file.

### Why it fails

Failure can occur at page access, expansion, card discovery, detail enrichment, date parsing, normalisation, or budget. A smaller partial run can erase valid results. Counting `debug_by_source` rows does not prove completion because failed sources also produce debug rows.

### Correct requirement interpretation

Runtime output includes explicit per-source completion states and evidence. A smaller partial run does not replace a larger verified collector snapshot.

### Required implementation

Record per-source evidence, calculate partial coverage from source completion states, preserve `local_event_collector_results.json` when required, retain `local_event_search_results.partial.json`, and rebuild the kiosk primary from the retained collector snapshot plus current Review decisions.

### Acceptance evidence

Tests and runtime evidence must cover verified-to-partial transitions, timed-out sources with retained `debug_by_source`, retained collector rows, and reapplication of confirmed/rejected Review decisions.

## Local Events Review publication and kiosk authority

### Easy-to-make interpretation

The Studio can display corrected fields while the kiosk renders a separate collector truth, or preview may temporarily rewrite persisted list-page decisions and roll them back later.

### Why it fails

That creates multiple visible truths and makes Review state vulnerable to interruption. A failed rollback can leave unrelated pages in the wrong decision state.

### Correct requirement interpretation

Review state and collector output may be stored separately, but the kiosk primary is one deterministic projection. Normal collection reads all confirmed pages. Preview copies Review state into a temporary store, confirms only the selected page inside that copy, and never writes the real state.

### Required implementation

Persist producer output to `local_event_collector_results.json`. Build `local_event_search_results.json` from that clean snapshot plus current Review decisions after every accepted producer run and Event decision. For the same canonical detail URL, a confirmed Review candidate owns non-empty title, date, venue, and description fields; a rejected candidate suppresses the collector row; pending restores it. `POST /api/local-events/review/preview-events` must accept one existing `listing_url`, use a temporary directory, and perform no persisted write.

### Acceptance evidence

A fixture with stale collector fields and a confirmed candidate sharing the same canonical URL must produce exactly one kiosk row with confirmed fields and preserved collector ordering. `NOT RELATED` must remove the matching row, `RESET` must restore the clean collector row, and a later producer run must reapply the decision. For pending isolated preview, capture Review state before and after, require equality, require only the selected listing in temporary collection evidence, and require no call to the list-decision endpoint.

## Dashboard Local Events filtering and collection boundary

### Easy-to-make interpretation

The kiosk card’s `SEARCH` control should submit the displayed text as a new collection location and call `POST /api/local-events/search` whenever the user narrows visible events.

### Why it fails

Collection is an expensive producer operation that opens official pages and rewrites runtime state. It does not provide an immediate filter over already displayed events.

### Correct requirement interpretation

The dashboard filter operates only on the current `local_event_search_results.json` payload. The institution dropdown is populated from current event rows, and typed text filters documented fields. Collection remains a timer-driven or explicit API operation outside the kiosk filter.

### Required implementation

Load rows with `GET /api/local-events/search`, retain the unfiltered set in browser memory, populate `ALL INSTITUTIONS`, and apply institution/text filters locally. Persist only browser filter choices. Do not send POST, launch Chromium, or write runtime JSON when `FILTER` is pressed.

### Acceptance evidence

Browser network evidence must show that pressing `FILTER` causes no `POST /api/local-events/search`. Institution and text filters must match documented fields, clearing both controls must restore all rows, and a later GET refresh must keep the active filter applied.

## Validation boundaries

### Easy-to-make interpretation

Static review or a successful fixture test proves live sources, Chromium flags, services, LAN access, and visible UI all work.

### Why it fails

Offline checks cannot prove current reachability, live DOM/API structure, process arguments, service deployment, or browser behaviour.

### Correct requirement interpretation

Static inspection, offline tests, live producer runs, service execution, and visible UI acceptance are separate evidence levels.

### Required implementation

Tie each claim to the exact revision and actual command, test, log, runtime file, process argument, screenshot, or interaction.

### Acceptance evidence

A final acceptance record states the exact revision, checks run, checks not run, remaining gaps, and a verdict no stronger than the evidence. Without live-source and device evidence, affected behaviour remains partially verified.
