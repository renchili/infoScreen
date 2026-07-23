# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread and the evidence needed to accept their implementation. It is organised by product requirement rather than conversation history.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display requires decorative CRT noise, a dot grid, or a pixel wallpaper.

### Why it fails

Those effects compete with information and reduce readability on an always-on display.

### Correct requirement interpretation

TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear boundaries, and a quiet background.

### Required implementation

Use typography, hierarchy, alignment, borders, and state presentation rather than decorative noise.

### Acceptance evidence

Browser evidence must show readable content at the target display size and no pattern obscuring text.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can act as a second Calendar client or any Python runtime can export EventKit.

### Why it fails

macOS Calendar owns accounts, permissions, and authoritative event state. A Python runtime without `import EventKit` cannot export Calendar data.

### Correct requirement interpretation

Calendar follows EventKit -> Mac export -> SSH/SCP -> Surface runtime JSON -> browser.

### Required implementation

Probe EventKit-capable Python, keep machine settings in uncommitted `mac/local.env`, and copy to the canonical Surface runtime file.

### Acceptance evidence

Show unattended LaunchAgent execution, a changed Surface file, current HTTP modification time, and visible Calendar output.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator or one generic refresh interval proves all data is current.

### Why it fails

The server can remain online while individual files are stale, missing, or unreachable. Producer refresh, browser reload, visual rotation, and operator-state refresh are different operations.

### Correct requirement interpretation

The Sync ticker observes per-file `Last-Modified`. The Local Event review page refreshes only at explicit operations, manual reload, and tab return.

### Required implementation

Keep per-file freshness checks and do not clear/rebuild all review cards every three seconds.

### Acceptance evidence

Leave the review page idle and during a long operation: it must not flash repeatedly or lose scroll.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, recursive crawler, or generic search scraper.

### Why it fails

Official sites differ in rendering, expansion, APIs, detail fields, pagination, anti-bot behavior, and timing.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official institutions, allowed domains, configured list URLs, and adapter behavior. A rendered card on an official list proves membership.

### Required implementation

Render and expand each configured list, isolate activity cards with one official detail URL and a usable title, then enrich those cards from detail pages.

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

The operator can only accept or reject URLs discovered by the system, or a correct URL must be added by editing committed configuration.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entrypoint that cannot be discovered reliably. Without a manual input, the user cannot correct the workflow.

### Correct requirement interpretation

The Studio must let the user select one global institution, enter a correct official Event list URL, save it into review state, and then use the same preview/confirm/reject workflow as discovered pages.

### Required implementation

Provide an always-visible URL field and `ADD LIST PAGE` button. Send `source_id` and `url` to `POST /api/local-events/review/listing-page`. Validate the configured institution and its allowed domains. Save the page as `pending`; do not collect automatically and do not edit committed `event_sources.json`.

Adding the same institution/URL again resets it to `pending`, allowing a rejected or stale decision to be reconsidered.

### Acceptance evidence

Select an institution, add a valid allowed-domain URL, observe it immediately in the left-side list, preview it, and confirm/reject it. Invalid institution, malformed URL, and disallowed domain must return HTTP `400` without changing review state.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves activity intent.

### Why it fails

Facilities, memberships, promotions, and navigation records can be event-shaped or typed as Events.

### Correct requirement interpretation

Positive Event intent means membership in the correct official activity list. Structured data and detail pages cannot independently create output rows.

### Required implementation

Require rendered official list evidence and match enrichment back to that card.

### Acceptance evidence

Reject unmatched typed Event objects and accept matched enrichment without adding title blacklists.

## Local Events zero-result diagnostics

### Easy-to-make interpretation

A zero count can be displayed as “no Events returned” without explaining the failed extraction stage.

### Why it fails

The operator cannot distinguish a load failure from unrecognized detail routes, card-boundary failure, selector failure, or detail-page failure.

### Correct requirement interpretation

Every attempted list page produces a diagnostic tied to that exact canonical URL and reports the first failed stage.

### Required implementation

Persist and display HTTP status, visible links, allowed-domain links, possible detail links, extracted/admitted cards, DOM evidence, selectors, candidates, and detail results.

### Acceptance evidence

A zero-result collection must show a stable `reason_code`, reason text, stage counts, and sample detail links when available.

## Local Events HTTP/2 handling

### Easy-to-make interpretation

The collector should first try normal Chromium HTTP/2 navigation, catch `ERR_HTTP2_PROTOCOL_ERROR`, then retry with another browser or protocol.

### Why it fails

That approach doubles navigation behavior, complicates diagnostics, and still starts every collection with the known failing protocol.

### Correct requirement interpretation

The supported collection entrypoints must disable HTTP/2 before Chromium launches. No HTTP/2-first request and no protocol retry loop should occur.

### Required implementation

Apply `surface/local_events_runtime/http1_browser.py` before importing collection code in both `surface/serve_infoscreen.py` and `surface/search_local_events.py`. Every patched Chromium launch must include `--disable-http2`.

### Acceptance evidence

Runtime process/launch evidence must show `--disable-http2` on Studio collection and scheduled/HTTP-triggered Local Event collection. A failing navigation must be reported as its direct error, not as a hidden first-attempt/retry sequence.

## Generated helper and archive boundary

### Easy-to-make interpretation

A browser interaction requirement can be solved by generating a ZIP, asking the user to extract it, and loading an unpacked Chrome extension.

### Why it fails

This adds an unrequested generated deliverable and installation workflow, violates repository artifact constraints, and changes the product/deployment boundary.

### Correct requirement interpretation

Do not generate a ZIP, extension bundle, helper archive, or extra installation flow unless the user explicitly requests that artifact and workflow.

### Required implementation

Remove the ZIP builder, download button, extension files, remote `feedback:` transport, and documentation that instructs the operator to install them. Until an accepted interaction design exists, the Studio must state that Ability 2 is not implemented rather than pretending it works.

### Acceptance evidence

Repository search and the rendered Studio must contain no active helper-download control, extension source directory, ZIP-building JavaScript, or remote helper submission route. No archive is generated at runtime.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every completed crawl should replace the primary file.

### Why it fails

Failure can occur at page access, expansion, card discovery, detail enrichment, date parsing, normalization, or budget. A smaller partial run can erase valid results.

### Correct requirement interpretation

Runtime output includes per-source evidence. A smaller partial run does not replace a larger verified result.

### Required implementation

Record per-source evidence, calculate partial coverage, preserve verified primary rows when required, and retain a partial payload.

### Acceptance evidence

Tests and runtime evidence must cover verified-to-partial transitions and retained debug data.

## Dashboard Local Events filtering and collection boundary

### Easy-to-make interpretation

The kiosk card’s `SEARCH` control should submit the displayed text as a new collection location and call `POST /api/local-events/search` every time the user wants to narrow the visible events.

### Why it fails

Collection is an expensive producer operation that opens many official pages and rewrites runtime state. It does not provide an immediate or predictable filter over the events already displayed, so a search control can appear to do nothing while unnecessarily starting another crawl.

### Correct requirement interpretation

The dashboard filter operates only on the current `local_event_search_results.json` payload. The institution dropdown is populated from the current event rows, and typed text filters title, institution/source, date/time, venue/place, and description. Collection remains a timer-driven or explicit API operation outside the kiosk filter.

### Required implementation

Load current rows with `GET /api/local-events/search`, retain the unfiltered row set in browser memory, populate `ALL INSTITUTIONS` plus the distinct current institutions, and apply institution and text filters locally. Persist only the browser filter choices. Do not send a POST, launch Chromium, or write runtime JSON when the filter button is pressed. Reapply active filters after periodic GET reloads.

### Acceptance evidence

Browser network evidence must show that pressing `FILTER` causes no `POST /api/local-events/search`. Selecting one institution must display only that institution’s rows; text terms must match across the documented fields; clearing both controls must restore all current rows; and a later GET refresh must keep the active filter applied.

## Validation boundaries

### Easy-to-make interpretation

Static review or a successful fixture test proves live sources, Chromium flags, services, LAN access, and visible UI all work.

### Why it fails

Offline checks cannot prove current reachability, live DOM/API structure, process arguments, service deployment, or browser behavior.

### Correct requirement interpretation

Static inspection, offline tests, live producer runs, service execution, and visible UI acceptance are separate evidence levels.

### Required implementation

Tie each claim to the exact revision and actual command, test, log, runtime file, process argument, screenshot, or interaction.

### Acceptance evidence

A final acceptance record must state the exact revision, checks run, checks not run, remaining gaps, and a verdict no stronger than the evidence.
