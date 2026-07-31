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

Static CSS evidence must contain no full-screen scanline or repeating-grid overlay. Browser evidence must show readable content at the target display size and no pattern obscuring text.

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

Show unattended LaunchAgent execution, a changed Surface file, current HTTP modification time, visible Calendar output, and a sync script that uploads to a temporary name before `mv` publishes the final file.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator, one generic refresh interval, or frequent whole-page rebuilding proves all data is current.

### Why it fails

The server can remain online while individual files are stale, missing, or unreachable. Producer refresh, browser data reload, visual rotation, dashboard filtering, and operator-state refresh are different operations. Rebuilding the Studio repeatedly also destroys scroll context.

### Correct requirement interpretation

The Sync ticker observes per-file `Last-Modified`. The Calendar board rotates every seven seconds but reloads Schedule data independently. The Local Event Studio refreshes only on initial load, explicit operations, manual reload, and return to the browser tab.

### Required implementation

Keep per-file freshness checks, reload Schedule data without reloading the page, remove idle Studio polling, emit one completed-render event, and restore one stable card anchor or scroll position after that render.

### Acceptance evidence

Leave the Studio idle and during a long operation: it must not flash repeatedly or lose scroll. Static source must not contain `setInterval(loadState, 3000)` or a global timer monkey patch that recognises a magic 3000-millisecond interval.

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

The operator can only accept or reject URLs discovered by the system, a correct URL must be added by editing committed configuration, a manually added page cannot be inspected until it is confirmed, or a browser-restored Preview panel is sufficient proof that its candidate set is still current.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entrypoint that cannot be discovered reliably. Without a manual input, the user cannot correct the workflow. Requiring confirmation before preview forces a decision before the operator can inspect the Event evidence used to make that decision. Browser session state can outlive a service restart, manifest expiry, newer Preview, or List Page revision change and therefore cannot be the server’s candidate-set authority.

### Correct requirement interpretation

The Studio lets the user select one global institution, enter a correct official Event list URL, save it into review state as pending, preview that saved page without changing its decision, classify every Preview candidate as REAL EVENT or NOT EVENT, then save the complete selection set together with the List Page decision. The submitted identities and original/final URLs must exactly match the latest unexpired server Preview manifest for the unchanged List Page revision. Normal persisted collection requires a confirmed page with committed REAL EVENT selections and collects only those selected rows.

### Required implementation

Provide an always-visible URL field and `ADD LIST PAGE` button. Send `source_id` and `url` to `POST /api/local-events/review/listing-page`. Validate the configured institution and its allowed domains. Save the page as `pending`; do not collect automatically and do not edit committed `event_sources.json`. Adding the same URL again must discard its old committed Preview selection and process-local manifest before starting a fresh pending review, with selection rollback if the Review-state write fails.

Expose isolated preview for every saved decision state. `POST /api/local-events/review/preview-events` must receive the saved `listing_url`, copy Review state into a temporary store, keep only that list page, mark only the temporary copy confirmed, clear copied Event candidates and feedback, run the final collector and final detail/redirect owner, and return the temporary result. It must not call the list-decision API or change persisted Review state.

After final detail enrichment and redirect handling, the server records the exact returned candidate IDs, original `listing_detail_url` values, final `detail_url` values, and List Page revision in a process-local manifest. The default lifetime is 21,600 seconds, configurable through `INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS` with a 60-second minimum. A service restart, expiry, newer Preview, List Page state change, reset, rejection, manual re-add, or discovery retirement invalidates the manifest and requires another Preview.

The Studio must require a decision for every returned Preview candidate. It sends the complete set to `POST /api/local-events/review/listing-decision` in the `preview-review-v1:` envelope, including the original candidate identity, original `listing_detail_url`, final redirected/public `detail_url`, and REAL EVENT / NOT EVENT decision. The backend compares the submitted set with the latest eligible manifest, stores the reviewed set in `preview_event_selections.json`, writes the List Page decision, and restores the prior selection file when the state write raises. A failed state write keeps the manifest available for retry.

Scoped discovery must retire no-longer-discovered non-manual pages together with their committed Preview selections. It removes the selection before writing the new Review state, restores the prior selection bytes if that write fails, and invalidates the process-local manifest only after success. A later discovery of the same URL must therefore start without an eligible old selection and require a fresh Preview.

`POST /api/local-events/review/collect-events` remains the persisted path, but it admits only committed REAL EVENT selections from pages currently marked `confirmed`.

### Acceptance evidence

Select an institution, add a valid allowed-domain URL, observe it immediately in the left-side list as pending, and preview it before confirmation. The preview must return only that page’s candidates while the persisted page decision, Event candidates, feedback, collection metadata, `state.json`, and `preview_event_selections.json` remain byte-for-byte or model-equivalent to their pre-preview state.

Classify every candidate, save the List Page review, and verify the committed selection set and List Page decision agree. Confirming requires at least one REAL EVENT; rejecting forbids a REAL EVENT. Formal collection must open and persist only selected REAL EVENT candidates, including a selected candidate whose original list link redirects to a different final public URL.

Invalid institution, malformed URL, disallowed domain, missing preview URL, unknown preview URL, missing/expired/superseded manifest, List Page revision mismatch, incomplete candidate set, duplicate identities, mismatched identities, changed original/final URLs, and disallowed original or final detail URLs must fail without leaving a partial saved review. A failed List Page state write must restore the prior selection and permit retry against the same manifest.

A discovery-retirement fixture must prove that a no-longer-discovered non-manual page loses its committed selection and manifest, while a manually added page remains. A forced Review-state save failure must restore the old selection. If the retired URL later reappears, ordinary confirmation must fail until a new Preview selection is committed.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves activity intent.

### Why it fails

Facilities, memberships, promotions, and navigation records can be event-shaped or typed as Events. The SAFRA `Carpark Rates` record demonstrated this failure mode.

### Correct requirement interpretation

Positive event intent means membership in the correct official activity list. Structured data and detail pages cannot independently create output rows.

### Required implementation

Require rendered official list evidence and match enrichment back to that card. Do not replace this positive authority with title blacklists.

### Acceptance evidence

Reject unmatched typed Event objects and accept matched enrichment without adding title blacklists. Preserve the SAFRA facility regression case.

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

The supported collection entrypoints disable HTTP/2 before Chromium launches. No HTTP/2-first request and no protocol retry loop should occur.

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

Remove the ZIP builder, download button, extension files, remote `feedback:` transport, and documentation that instructs the operator to install them. Until an accepted interaction design exists, the Studio states that Ability 2 is not implemented rather than pretending it works.

### Acceptance evidence

Repository search and the rendered Studio contain no active helper-download control, extension source directory, ZIP-building JavaScript, or remote helper submission route. No archive is generated at runtime.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every completed crawl should replace the primary file.

### Why it fails

Failure can occur at page access, expansion, card discovery, detail enrichment, date parsing, normalization, or budget. A smaller partial run can erase valid results. Counting `debug_by_source` rows does not prove completion because failed sources also produce debug rows.

### Correct requirement interpretation

Runtime output includes explicit per-source completion states and evidence. A smaller partial run does not replace a larger verified collector snapshot.

### Required implementation

Record per-source evidence, calculate partial coverage from source completion states, preserve the producer-owned `local_event_collector_results.json` snapshot when required, retain `local_event_search_results.partial.json`, and rebuild the kiosk primary from the retained collector snapshot plus current Review decisions. The retained write policy remains visible as `kept_previous_complete_result` when applicable.

### Acceptance evidence

Tests and runtime evidence must cover verified-to-partial transitions, timed-out sources with retained `debug_by_source`, retained collector rows, and reapplication of confirmed/rejected Review decisions.

## Local Events Review publication and kiosk authority

### Easy-to-make interpretation

The Studio can display corrected fields while the kiosk continues rendering a separate collector row, a preview may temporarily rewrite the selected or unrelated list-page decisions and restore them later, or any browser-restored Preview panel may be submitted without proving it is the server’s latest candidate set.

### Why it fails

That creates multiple visible truths and makes Review state vulnerable to interruption. A failed client rollback can leave one or more pages in the wrong decision state. Requiring confirmation before preview also couples evidence gathering to a persisted review mutation. Trusting stale browser state permits omitted, changed, or retired candidates to be committed.

### Correct requirement interpretation

Review state and collector output may be stored separately, but the kiosk primary is one deterministic projection. Preview is an isolated, decision-independent read/collection operation. Candidate submission must equal the latest unexpired process-local server Preview manifest. Normal Event collection persists only committed REAL EVENT selections from confirmed pages.

### Required implementation

Persist producer output to `local_event_collector_results.json`. Build `local_event_search_results.json` from that clean snapshot plus current Review decisions after every accepted producer run and Event decision. For the same canonical detail URL, a confirmed Review candidate is authoritative for non-empty title, date, venue, and description fields; a rejected candidate suppresses the collector row; pending restores it.

Preview must use `/api/local-events/review/preview-events`, must not call the list-decision API, and must not publish to the kiosk. The server must create an isolated temporary Review store containing only the selected page, confirmed only inside that copy, with copied Events and feedback cleared. The real Review state remains untouched even when preview collection fails.

The final Preview handoff must invalidate the old manifest before collection and issue the new manifest only after detail enrichment and redirect handling. The Preview panel must preserve original list-card identity separately from the final redirected/public detail URL. Saving the List Page review validates every candidate decision against that manifest. Formal collection must prefilter unselected list cards before detail navigation, retain only results matching the selected identity or original/final URL, and never treat a confirmed page as unrestricted merely because it has no saved selection record.

List Page lifecycle owners must remove stale authority: RESET, REJECT, manual re-add, and discovery retirement clear committed selection state and invalidate the manifest. State-write failures restore the previous selection bytes before returning an error.

### Acceptance evidence

A fixture with stale collector fields and a confirmed candidate sharing the same canonical URL must produce exactly one kiosk row with the confirmed fields and preserved collector ordering metadata. `NOT RELATED` must remove the matching row, `RESET` must restore the clean collector row, and a later producer run must reapply the decision.

A separate pending-page fixture must prove that preview succeeds before confirmation, the temporary collector sees one confirmed page, and persisted list decisions, Event candidates, feedback, collection metadata, selection state, and kiosk output do not change. Frontend source must contain the isolated preview endpoint and no temporary list-decision writes or confirmation gate.

A selection fixture must prove that incomplete decisions cannot confirm a page, the submitted exact set must equal the latest server manifest, expired/restarted/revision-changed submissions require a new Preview, unselected list cards are rejected before detail navigation, selected rows are persisted as confirmed, and a redirected selected candidate remains linked to the original candidate identity while matching its final public URL after enrichment.

A discovery lifecycle fixture must prove that retired non-manual pages cannot leave an old selection eligible for reuse when the same URL later appears again.

## Dashboard Local Events filtering and collection boundary

### Easy-to-make interpretation

The kiosk card’s `SEARCH` control should submit the displayed text as a new collection location and call `POST /api/local-events/search` every time the user wants to narrow the visible events.

### Why it fails

Collection is an expensive producer operation that opens many official pages and rewrites runtime state. It does not provide an immediate or predictable filter over the events already displayed.

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

A final acceptance record states the exact revision, checks run, checks not run, remaining gaps, and a verdict no stronger than the evidence. Without live-source and device evidence, the affected behavior remains partially verified.
