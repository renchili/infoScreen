# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread, the operational evidence needed to diagnose failures, and the evidence needed to accept their implementation. It is organised by product requirement rather than conversation history.

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

Calendar sync settings can be supplied with one-off shell environment assignments whenever the script is run, the remote Schedule target must begin with `~/`, or a successful upload is enough even when the already-open kiosk page keeps displaying the previous Schedule payload.

### Why it fails

A prefix such as `REMOTE_SCHEDULE_JSON=... bash mac/sync_schedule.sh` applies only to that one process. A later LaunchAgent run does not inherit values assigned in a terminal session. The remote target may also be a valid absolute path below the SSH user's home directory, so rejecting every path except `~/...` can stop an otherwise correct unattended sync before EventKit export or upload begins. Producer refresh and browser refresh are separate layers: replacing `schedule.json` does not help an already-open page unless the Calendar browser owner reloads that file independently.

### Correct requirement interpretation

macOS Calendar/EventKit remains authoritative. The setup command persists the resolved Python executable, Surface host, SSH user, remote Schedule path, local JSON name, and log directory in the LaunchAgent `ProgramArguments`. Those explicit arguments are the authoritative unattended runtime configuration. The sync script accepts either an absolute remote path or a `~/` home-relative path, validates and publishes the JSON atomically, and the Calendar board reloads Schedule data without requiring a full-page refresh.

### Required implementation

`mac/scripts/setup-schedule-sync.sh` must serialize the resolved values into the LaunchAgent argument list. `mac/local.env` may be read only as migration input for an older installation; it must not remain a runtime dependency for future LaunchAgent executions. `mac/sync_schedule.sh` must parse explicit arguments, accept safe absolute and `~/` remote paths, export EventKit data, validate the local JSON, upload to a temporary remote name, rename atomically, verify the published JSON, and record the final stage. The browser Calendar owner must poll or otherwise reload `schedule.json` independently of page reload and visual rotation.

### Acceptance evidence

Static evidence must show the Schedule values in LaunchAgent `ProgramArguments`, command-line arguments taking precedence over compatibility environment values, support for both absolute and `~/` remote paths, atomic remote publication, and independent browser Schedule reload. Device evidence must show an unattended LaunchAgent run with exit code `0`, a changed and valid remote `schedule.json`, and the new Calendar content appearing in an already-open kiosk page without a forced page refresh. A one-off environment-prefixed manual invocation is not evidence that unattended configuration is persisted.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator, one generic refresh interval, frequent whole-page rebuilding, or the Sync ticker’s `FAIL` label alone explains why data did not update.

### Why it fails

The server can remain online while individual files are stale, missing, or unreachable. Producer refresh, browser data reload, visual rotation, dashboard filtering, and operator-state refresh are different operations. Rebuilding the Studio repeatedly also destroys scroll context. The ticker proves a freshness or reachability failure, but it does not identify the producer exit result, provider exception, retained last-success time, malformed JSON, missing runtime file, or HTTP payload actually being served.

### Correct requirement interpretation

The Sync ticker observes per-file `Last-Modified`. The Calendar board rotates every seven seconds but reloads Schedule data independently. The Local Event Studio refreshes only on initial load, explicit operations, manual reload, and return to the browser tab. When Schedule, Weather, or Market shows `FAIL`, diagnosis combines the producer result, recent producer output, runtime-file validity and metadata, and the HTTP response currently seen by the browser.

### Required implementation

Keep per-file freshness checks, reload Schedule data without reloading the page, remove idle Studio polling, emit one completed-render event, and restore one stable card anchor or scroll position after that render. Weather and Market producers must log timestamped `component` and `state` fields, preserve distinct `last_attempt_at` and `last_success_at` values, retain the provider exception in the runtime payload, and exit non-zero when a required live-data component fails. `surface/scripts/infoscreen_status.sh` must expose producer results and exit status, recent producer output, timer state, runtime-file age and JSON validity, `status`, `error`, `updated_at`, `last_attempt_at`, `last_success_at`, and the Schedule/Weather/Market HTTP payloads.

### Acceptance evidence

Leave the Studio idle and during a long operation: it must not flash repeatedly or lose scroll. Static source must not contain `setInterval(loadState, 3000)` or a global timer monkey patch that recognises a magic 3000-millisecond interval. For a live-data failure, evidence must show a non-zero producer result, a timestamped component failure line, an `ERR` runtime payload with the provider error, an unchanged last-success timestamp, and matching status-script and HTTP observations. For a successful later run, the result returns to success and `last_success_at` advances.

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

The official list proves membership. Date and venue can be obtained after admission by following the card’s official detail link. Explicit detail labels such as `Opening Hours`, `Date`, `Time`, and `Location` outrank unlabeled date/venue matches elsewhere in the same document.

### Required implementation

Do not require a list-card date. Preserve listing evidence, follow the detail URL, keep labeled schedule/location values ahead of generic selector candidates, and show exact detail status/errors.

### Acceptance evidence

A date-less list card with one official detail link must be admitted and enriched from its detail page. A fixture containing an explicit activity schedule/location plus promotional dates and advisory copy must return only the labeled activity fields.

## Local Events manual correct-list-page entry

### Easy-to-make interpretation

The operator can only accept or reject URLs discovered by the system, a correct URL must be added by editing committed configuration, any same-domain archive page is a valid current List Page, a manually added page cannot be inspected until it is confirmed, a browser-restored Preview panel is sufficient proof that its candidate set is still current, or an official candidate whose event date has passed should disappear before the operator can classify it.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entrypoint that cannot be discovered reliably. Without a manual input, the user cannot correct the workflow. A same-domain archive or past-activities page is historical evidence, not a current collection authority. Requiring confirmation before preview forces a decision before the operator can inspect the Event evidence used to make that decision. Browser session state can outlive a service restart, manifest expiry, newer Preview, or List Page revision change and therefore cannot be the server’s candidate-set authority. Expired official candidates are still classification evidence; hiding them during Preview prevents the operator from recording whether the official list item is a real Event.

### Correct requirement interpretation

The Studio lets the user select one global institution, enter a correct current official Event list URL, save it into review state as pending, preview that saved page without changing its decision, classify every Preview candidate as REAL EVENT or NOT EVENT, then save the complete selection set together with the List Page decision. Archive and past-activities pages are rejected as current List Pages even when they use an allowed hostname. The submitted identities and original/final URLs must exactly match the latest unexpired server Preview manifest for the unchanged List Page revision. Preview keeps expired official candidates visible for classification, while formal persisted collection and kiosk publication retain normal event-expiry filtering. Normal persisted collection requires a current confirmed page with committed REAL EVENT selections and collects only those selected rows.

### Required implementation

Provide an always-visible URL field and `ADD LIST PAGE` button. Send `source_id` and `url` to `POST /api/local-events/review/listing-page`. Validate the configured institution, its allowed domains, and the current-page policy that rejects archive/past URLs and labels. Save the page as `pending`; do not collect automatically and do not edit committed `event_sources.json`. Adding the same URL again must discard its old committed Preview selection and process-local manifest before starting a fresh pending review, with selection rollback if the Review-state write fails.

Expose isolated preview for every saved decision state. `POST /api/local-events/review/preview-events` must receive the saved `listing_url`, copy Review state into a temporary store, keep only that list page, mark only the temporary copy confirmed, clear copied Event candidates and feedback, and return the temporary result without changing persisted Review state.

The direct Preview owner must use one Playwright manager and the source-specific browser lifecycle required by the official site. Non-ArtScience sources may reuse one Chromium process/context for the listing and details. ArtScience Museum / Marina Bay Sands must close the listing browser and open each admitted detail as the first document in a fresh sequential Chromium process/context so the detail does not inherit the listing process’s network/HTTP2 connection state. Both modes must preserve original list-card identity across redirects. The final handoff must fail without issuing a manifest if listing-only evidence remains; it must not start an additional post-collector fallback browser.

Successful non-ArtScience same-context metadata must report `preview_browser_process_count: 1`, `preview_browser_reuse: listing_and_details`, `preview_detail_context_count: 1`, and `preview_detail_transport: same_browser_context`. Successful ArtScience/MBS metadata must report `preview_detail_fresh_browser_count`, `preview_browser_process_count: 1 + preview_detail_fresh_browser_count`, `preview_browser_reuse: single_playwright_sequential_browsers`, `preview_detail_context_count: preview_detail_fresh_browser_count`, and `preview_detail_transport: sequential_browser_processes`.

The final Preview handoff must retain expired official candidates in the isolated temporary Preview store and report `preview_expiry_policy: retain_for_operator_review`. Non-Preview collection must continue through the normal expiry owners; the Preview exception must not alter persisted collection or kiosk publication.

After final detail collection and redirect handling, the server records the exact returned candidate IDs, original `listing_detail_url` values, final `detail_url` values, and List Page revision in a process-local manifest. The default lifetime is 21,600 seconds, configurable through `INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS` with a 60-second minimum. A service restart, expiry, newer Preview, List Page state change, reset, rejection, manual re-add, or discovery retirement invalidates the manifest and requires another Preview.

The Studio must require a decision for every returned Preview candidate. It sends the complete set to `POST /api/local-events/review/listing-decision` in the `preview-review-v1:` envelope, including the original candidate identity, original `listing_detail_url`, final redirected/public `detail_url`, and REAL EVENT / NOT EVENT decision. The backend compares the submitted set with the latest eligible manifest, stores the reviewed set in `preview_event_selections.json`, writes the List Page decision, and restores the prior selection file when the state write raises. A failed state write keeps the manifest available for retry.

Scoped discovery must retire no-longer-discovered non-manual pages together with their committed Preview selections. It removes the selection before writing the new Review state, restores the prior selection bytes if that write fails, and invalidates the process-local manifest only after success. A later discovery of the same URL must therefore start without an eligible old selection and require a fresh Preview.

`POST /api/local-events/review/collect-events` remains the persisted path. It admits only committed REAL EVENT selections from pages currently marked `confirmed`, and it excludes archive/past pages again at the formal selection boundary even when an older persisted state still contains them.

### Acceptance evidence

Select an institution, add a valid allowed-domain current URL, observe it immediately in the left-side list as pending, and preview it before confirmation. The preview must return only that page’s candidates while the persisted page decision, Event candidates, feedback, collection metadata, `state.json`, and `preview_event_selections.json` remain byte-for-byte or model-equivalent to their pre-preview state. A same-domain archive or past-activities URL must return HTTP `400` without persistence.

Direct-collector fixtures must prove both supported lifecycles. A non-ArtScience fixture proves listing and details reuse one browser context. An ArtScience/MBS fixture proves one Playwright manager, listing-browser closure before detail collection, one fresh sequential browser/context per attempted detail, and no reuse of listing network state. Both fixtures must prove redirected final URLs retain the original candidate identity and the final handoff rejects remaining listing-only candidates without opening a post-collector fallback browser.

The Preview fixtures must also prove that an expired official detail result remains in Preview, the response reports `preview_expiry_policy: retain_for_operator_review`, and a non-Preview store still follows the normal expiry handoff.

Classify every candidate, save the List Page review, and verify the committed selection set and List Page decision agree. Confirming requires at least one REAL EVENT; rejecting forbids a REAL EVENT. Formal collection must open and persist only selected REAL EVENT candidates, including a selected candidate whose original list link redirects to a different final public URL. A legacy confirmed archive page with an old committed selection must not be admitted into formal collection.

Invalid institution, malformed URL, disallowed domain, archive/past URL, missing preview URL, unknown preview URL, missing/expired/superseded manifest, List Page revision mismatch, incomplete candidate set, duplicate identities, mismatched identities, changed original/final URLs, and disallowed original or final detail URLs must fail without leaving a partial saved review. A failed List Page state write must restore the prior selection and permit retry against the same manifest.

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

Every Local Event browser path must either use HTTP/2 first and retry, or every path must be forced to HTTP/1 regardless of its deployed evidence.

### Why it fails

An HTTP/2-first retry doubles formal navigation behavior and hides the first failure. Conversely, forcing isolated Marina Bay Sands Preview to HTTP/1 contradicts the deployed headed-browser/NetLog evidence and changes the direct Preview transport unnecessarily. Reusing the listing Chromium network process for ArtScience/MBS detail pages can also preserve the failing connection pool even when the page object or context changes.

### Correct requirement interpretation

Scoped discovery, confirmed-page formal collection, scheduled collection, and direct search disable HTTP/2 before Chromium launches and do not retry protocols. Isolated Preview is a separate direct collector with normal Chromium protocol negotiation and one Playwright manager. Most sources can reuse one browser context. ArtScience/MBS uses sequential fresh Chromium processes so every detail is the first document in its process, may run headed, and records NetLog diagnostics.

### Required implementation

Apply `surface/local_events_runtime/http1_browser.py` before formal collection code in `surface/serve_infoscreen.py` and `surface/search_local_events.py`. Formal-path Chromium launches include `--disable-http2`. `preview_direct_detail_collector_authority.py` must not add a second protocol owner, retry loop, or `--disable-http2`; it may own the source-specific fresh-process lifecycle. `preview_transport_authority.py` owns Preview mode and diagnostics only.

### Acceptance evidence

Static and runtime evidence must distinguish the paths. Formal discovery/collection process arguments show `--disable-http2` and no hidden retry. Non-ArtScience Preview shows the documented same-context lifecycle with normal protocol negotiation. ArtScience/MBS Preview shows listing-process closure, sequential fresh detail processes, the required headed mode when applicable, normal protocol negotiation, and NetLog diagnostics on failure.

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

Review state and collector output may be stored separately, but the kiosk primary is one deterministic projection. Preview is an isolated, decision-independent read/collection operation. Candidate submission must equal the latest unexpired process-local server Preview manifest. Normal Event collection persists only committed REAL EVENT selections from current confirmed pages.

### Required implementation

Persist producer output to `local_event_collector_results.json`. Build `local_event_search_results.json` from that clean snapshot plus current Review decisions after every accepted producer run and Event decision. For the same canonical detail URL, a confirmed Review candidate is authoritative for non-empty title, date, venue, and description fields; a rejected candidate suppresses the collector row; pending restores it.

Preview must use `/api/local-events/review/preview-events`, must not call the list-decision API, and must not publish to the kiosk. The server must create an isolated temporary Review store containing only the selected page, confirmed only inside that copy, with copied Events and feedback cleared. The real Review state remains untouched even when preview collection fails.

The direct Preview collector must complete listing recognition and detail reads in one Playwright manager using the source-specific same-context or ArtScience/MBS sequential-browser lifecycle. The final Preview handoff must invalidate the old manifest before collection, reject remaining listing-only evidence, retain expired official candidates, and issue the new manifest only after detail collection and redirect handling. The Preview panel must preserve original list-card identity separately from the final redirected/public detail URL. Saving the List Page review validates every candidate decision against that manifest. Formal collection must prefilter unselected list cards before detail navigation, retain only results matching the selected identity or original/final URL, exclude archive/past pages at the formal selection boundary, and never treat a confirmed page as unrestricted merely because it has no saved selection record.

List Page lifecycle owners must remove stale authority: RESET, REJECT, manual re-add, and discovery retirement clear committed selection state and invalidate the manifest. State-write failures restore the previous selection bytes before returning an error.

### Acceptance evidence

A fixture with stale collector fields and a confirmed candidate sharing the same canonical URL must produce exactly one kiosk row with the confirmed fields and preserved collector ordering metadata. `NOT RELATED` must remove the matching row, `RESET` must restore the clean collector row, and a later producer run must reapply the decision.

A separate pending-page fixture must prove that preview succeeds before confirmation, the temporary collector sees one confirmed page, and persisted list decisions, Event candidates, feedback, collection metadata, selection state, and kiosk output do not change. Frontend source must contain the isolated preview endpoint and no temporary list-decision writes or confirmation gate.

A selection fixture must prove that incomplete decisions cannot confirm a page, the submitted exact set must equal the latest server manifest, expired/restarted/revision-changed submissions require a new Preview, unselected list cards are rejected before detail navigation, selected rows are persisted as confirmed, and a redirected selected candidate remains linked to the original candidate identity while matching its final public URL after detail collection.

Direct Preview fixtures must prove the source-specific lifecycle metadata, listing-before-detail order, no post-collector browser fallback, retention of expired classification candidates, and manifest issuance only after the final-detail invariant passes.

A discovery lifecycle fixture must prove that retired non-manual pages cannot leave an old selection eligible for reuse when the same URL later appears again. A formal-collection fixture must also prove that legacy confirmed archive pages are not admitted before their persisted history is retired.

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