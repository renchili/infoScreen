# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread and the evidence needed to accept their implementation. It is organised by product requirement rather than by conversation history or implementation attempt.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display can be interpreted as requiring a dot-matrix wallpaper, pixel grid, noisy CRT texture, or other decorative terminal effect.

### Why it fails

Those effects compete with the information, reduce readability on an always-on display, and confuse decoration with the requirement for a stable information hierarchy.

### Correct requirement interpretation

The TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear panel boundaries, and a visually quiet background.

### Required implementation

Keep the background restrained. Use typography, hierarchy, alignment, borders, and state presentation. Do not add decorative CRT noise as a substitute for information design.

### Acceptance evidence

A browser acceptance check must show readable content at the target display size, stable panel boundaries, no decorative pattern obscuring text, and consistent visual hierarchy.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can be treated as a second Calendar client, any `python3` can be assumed to support EventKit, and a successful copy to any path can be treated as a successful Calendar update.

### Why it fails

macOS Calendar owns the accounts, permissions, timezone context, and authoritative event view. A Python runtime without `import EventKit` cannot export Calendar data. launchd does not inherit an interactive shell. The dashboard only reads `~/infoscreen/surface/.env/schedule.json`.

### Correct requirement interpretation

Calendar data follows macOS Calendar/EventKit -> `mac/export.py` -> local `schedule.json` -> `mac/sync_schedule.sh` -> SSH/SCP -> Surface runtime file -> `/schedule.json` -> `calendar_board.js`.

### Required implementation

Probe Python executables with `import EventKit`, store machine-specific settings in uncommitted `mac/local.env`, install a LaunchAgent with explicit paths, create the remote runtime directory, and copy to the canonical destination.

### Acceptance evidence

Evidence must show the configured Python imports EventKit, the LaunchAgent runs unattended, the canonical Surface file changes, the endpoint serves the new payload and modification time, and a page reload displays it.

## Market resilience and runtime symbol authority

### Easy-to-make interpretation

Market data can use one public endpoint, a provider failure can empty the whole panel, and browser local storage can be the authoritative symbol list.

### Why it fails

Public providers can reject, rate-limit, return HTML, omit fields, or behave differently for stocks and ETFs. One failure must not erase values available from another provider or previous usable runtime data. Browser state is not reliable shared configuration.

### Correct requirement interpretation

Each symbol uses the fallback chain Nasdaq stock/ETF, CNBC, Stooq, Yahoo, then previous usable `market.json`. Active symbols are authoritative in `surface/.env/market_config.json`; committed defaults remain in `surface/conf/market_config.default.json`.

### Required implementation

Normalize, deduplicate, and limit symbols to 12. Mark retained values `session: STALE`, `provider: stale-cache`. Emit `session: ERR`, `provider: none`, `price: N/A` when no value exists.

### Acceptance evidence

Tests and runtime inspection must prove fallback order, per-symbol isolation, stale-cache marking, visible ERR output, persistence, and consistent movement direction.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator or one generic refresh interval proves all page data is current.

### Why it fails

The HTTP server can remain online while individual runtime files are old, missing, or unreachable. Producer refresh, browser reload, visual rotation, and operator-state refresh are independent.

### Correct requirement interpretation

The Sync ticker observes runtime files through `Last-Modified`. Producers write data, browser code reloads on its own cadence, and rotation changes only already-loaded content. The Local Event review page reloads after explicit actions, manual reload, and tab return rather than recurring full-DOM polling.

### Required implementation

Keep per-file thresholds and HEAD checks. Document separate producer, browser reload, and rotation schedules. Do not run a three-second review-page loop that clears and rebuilds all cards.

### Acceptance evidence

Acceptance must demonstrate each freshness state, correct age calculation, independent failure of one runtime file, and a review page that remains visually stable and preserves scroll while idle.

## Synchronized multilingual News

### Easy-to-make interpretation

Three unrelated feeds that scroll at the same speed can be presented as synchronized English, French, and Chinese content.

### Why it fails

The same screen position would refer to unrelated stories. Substituting another story when one language is unavailable breaks semantic alignment.

### Correct requirement interpretation

All three rows display corresponding versions of the same base content and maintain the same order and position. Translation fills a missing language rather than substituting an unrelated item.

### Required implementation

Select a real base item, produce a complete EN/FR/ZH triple, validate every language, and skip the entire triple if one language cannot be produced after retries.

### Acceptance evidence

Tests must verify equal row lengths, matching base identity at each index, valid text, whole-triple rejection, and synchronized movement.

## Local Photo processing

### Easy-to-make interpretation

The browser can enumerate personal files, HEIC can be linked directly, and every format can be flattened to one static type.

### Why it fails

Browsers do not reliably display HEIC/HEIF, direct enumeration exposes local paths, and flattening GIF destroys animation. Duplicate stems can create repeated photos.

### Correct requirement interpretation

Originals stay under `surface/.env/photos/`. The builder creates browser-safe files under `surface/.env/public_photos/` and writes `photos.json`. GIF remains animated; HEIC/HEIF is converted when supported; a native image with the same stem takes priority.

### Required implementation

Keep originals outside the served tree, generate cache-busted URLs, preserve GIF, handle unsupported conversion explicitly, and avoid duplicate stems.

### Acceptance evidence

Fixtures must cover normalization, GIF copy, HEIC/HEIF conversion or skip, duplicate precedence, manifest generation, cache invalidation, and access only through public runtime paths.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, recursive crawler, or generic search scraper, and a stored fixture proves current live coverage.

### Why it fails

Official sites differ in rendering, list completeness, APIs, detail fields, pagination, anti-bot behavior, and timing. Unrestricted crawling increases unrelated content and blocking risk. Offline fixtures do not prove current page structure.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official list entrypoints, domains, venues, order, and adapter. A rendered card on one of those lists proves membership. Structured XHR, embedded state, and detail pages may improve fields only after membership is established.

### Required implementation

Render and fully expand each configured list, isolate activity cards with one official detail URL and usable title, then enrich those admitted cards. Do not recursively scan the site or admit unmatched structured objects.

### Acceptance evidence

For an affected organisation, evidence must include a real collector run, debug data, list-card evidence, final runtime JSON, visible output, and an offline regression for the observed structure.

## Local Events listing-date authority

### Easy-to-make interpretation

A list card can be rejected unless it already contains a usable date.

### Why it fails

Correct official Event lists may show only an image, title, category, and detail link. The date can exist only on the official detail page. Rejecting before following that link produces zero Events from valid lists such as museum What’s On pages.

### Correct requirement interpretation

The configured official list proves membership through an isolated rendered card with a usable title and exactly one canonical official detail link. Date and venue are required for final Event output, but they may be obtained from the detail page after admission.

### Required implementation

Remove listing-date checks from card admission. Preserve list evidence, follow the admitted detail URL, extract date/time and venue there, and keep an `incomplete` or `failed` candidate with exact detail error when enrichment cannot complete.

### Acceptance evidence

A regression must show that a date-less list card with one official detail link is admitted, its detail page supplies the date, and a card without a valid detail link is rejected. A live run must show Events from a real list whose cards omit dates.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves that a structured record is an activity.

### Why it fails

Facilities, membership access, operating information, promotions, and navigation records can be event-shaped or typed as Events. A blacklist never becomes complete.

### Correct requirement interpretation

Positive Event intent means membership in the correct official activity list. Structured JSON and detail pages cannot independently create output rows. A legitimate listed activity is not rejected because its title contains a word seen in a previous bad record.

### Required implementation

Require rendered official list evidence with one canonical detail URL and usable title. Match structured data to that card, discard unmatched records, and keep rejection in the backend collector rather than frontend hiding.

### Acceptance evidence

Regression tests must reject unmatched typed Event objects without new title blacklists, accept matched enrichment, retain legitimate listed activities, and reject cards without official list evidence.

## Local Events detail-field authority

### Easy-to-make interpretation

The organisation name can always be the final venue, or an internal CMS/list URL can be exposed as the Event URL even when the detail page contains a specific location and public route.

### Why it fails

The organisation is often only the host. Internal paths prevent the user from opening the canonical public activity page. Falling back before reading labeled detail fields discards correct data.

### Correct requirement interpretation

After list admission, the official detail page is authoritative for specific venue and public detail URL. Labeled `Where`, `Location`, or `Venue` values override the configured default. Configured prefix rewrites may map internal CMS paths to equivalent public paths.

### Required implementation

Parse labeled detail fields, prefer them over defaults, normalize approved path prefixes, remove fragments, and retain the listing URL separately as evidence.

### Acceptance evidence

A regression must prove the observed National Gallery public-path and specific-venue behavior without enumerating Event slugs. Live inspection remains required.

## Local Events zero-result diagnostics

### Easy-to-make interpretation

A zero count can be displayed as “no Events returned” or “no diagnostic record” without explaining the failed extraction stage.

### Why it fails

The operator cannot distinguish an incorrect URL from page load failure, unrecognized detail routes, card-boundary failure, missing selector evidence, detail timeout, or missing detail fields. A generic message sends the user to fix the wrong thing.

### Correct requirement interpretation

Every attempted list page produces one diagnostic record tied to the exact canonical list URL. It reports the first failed recognition stage and the supporting counts.

### Required implementation

Persist and display HTTP status, visible-link count, allowed-domain links, possible detail links, extracted cards, admitted cards, DOM evidence, selectors, candidates, and detail result counts. Distinguish backend-not-restarted and wrong-scope diagnostics from actual extraction failure.

### Acceptance evidence

A zero-result collection must show a stable `reason_code`, reason text, stage counts, and sample detail links when present. The page must not claim the URL is wrong unless the evidence supports that conclusion.

## Local Events review-page stability

### Easy-to-make interpretation

Polling review state every few seconds and rebuilding every card is a simple way to keep the page current.

### Why it fails

Full rebuilds cause flicker, scroll jumps, disappearing transient results, repeated MutationObserver work, and status overlays that appear to start repeatedly. They are unnecessary for a single-operator local tool.

### Correct requirement interpretation

Review state changes at explicit user actions. The browser reloads after those actions, on manual `RELOAD`, and once when the operator returns to the tab.

### Required implementation

Remove recurring three-second state polling. Preserve scroll across intentional renders. Do not independently refetch diagnostics after every DOM mutation; reuse the state returned by the collection request.

### Acceptance evidence

Leave the page idle and during a long collection: cards must not flash or rebuild repeatedly, scroll must remain stable, and only one long-task blocking indicator may remain visible.

## Local Events browser-feedback execution location

### Easy-to-make interpretation

Because the HTTP server runs on the Surface, `OPEN REAL LISTING PAGE` should launch a headed Chromium process on the Surface desktop.

### Why it fails

The operator may access the Studio from another LAN computer because the Surface screen is small and may have no mouse. A server-launched browser appears on the wrong device and cannot use the operator computer's browser session, cookies, or comfortable input devices.

### Correct requirement interpretation

Interactive browsing and DOM selection run in Chrome on the device currently displaying the Studio. The Surface only serves configuration and persists submitted feedback.

### Required implementation

Provide a client-device Chrome helper. It opens the official listing in the same Chrome profile, injects the feedback toolbar, preserves normal browsing behavior, and submits selector/index/position/text/href/page URL to the Surface API. Keep any Surface-local Playwright browser as a legacy/manual path, not the Studio default.

### Acceptance evidence

From another LAN computer, the operator must open the Studio, launch the listing on that same computer, use cookies/filters/pagination, submit a selected Event, and see it appear in Surface review state without any browser window opening on the Surface.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every completed crawl should replace the primary file even when sources failed or previous rows use an obsolete policy.

### Why it fails

Failure can occur at page access, expansion, card discovery, detail enrichment, date parsing, normalization, or budget. A smaller partial run can erase valid results; preserving unverified legacy rows can keep known bad data.

### Correct requirement interpretation

The runtime includes `debug_by_source` and optional evidence. Previous cache comparison considers only rows with `candidate_policy: official-listing-authority-v1`. A smaller partial run is written separately with `write_policy: kept_previous_verified_result`.

### Required implementation

Record per-source evidence, calculate partial coverage, remove unverified legacy rows from cache comparison, preserve verified primary rows when required, and retain the partial payload.

### Acceptance evidence

Tests must cover verified-to-partial transitions, legacy removal, result comparison, primary preservation, partial file creation, write policy, and retained debug data. A real failed-source run must show the same behavior.

## Local Events package boundary

### Easy-to-make interpretation

Repository rules can name `surface/jobs/local_events/` while implementation remains in `surface/local_events_runtime/`.

### Why it fails

Contradictory paths encourage duplicate implementations and unsafe moves.

### Correct requirement interpretation

`surface/jobs/local_event_search.py` is orchestration. `surface/local_events_runtime/` is the canonical collector, review, diagnostics, and feedback library. `surface/search_local_events.py` remains a compatibility wrapper.

### Required implementation

Keep new runtime logic in the canonical package. Update rules, README, design, imports, callers, and tests together if an explicit migration changes the boundary.

### Acceptance evidence

Static checks must show one canonical package, no duplicate implementation, documented imports, and preserved systemd/HTTP command contracts.

## Logging and command output

### Easy-to-make interpretation

Every stdout line is ad-hoc logging, or generic structured-logging requirements must be applied without considering the local systemd deployment and machine-readable command output.

### Why it fails

Operational status and deliberate JSON command results are different interfaces. Reformatting command output breaks callers; adding an unused logging stack adds maintenance.

### Correct requirement interpretation

Systemd-captured stdout/stderr is accepted operational output. Concise status lines are allowed. Deliberate Local Events JSON stdout remains command output. Structured logs, request IDs, and tracing are not current requirements.

### Required implementation

Keep output concise and free of credentials, tokens, full request bodies, private file contents, and unnecessary personal data. Preserve the standard HTTP diagnostics and command JSON contract.

### Acceptance evidence

Static and operational checks must distinguish logs from command results and show useful, non-sensitive service and producer output.

## Validation boundaries

### Easy-to-make interpretation

A mocked browser, fixture, successful `pytest`, static review, or written report proves current sources, services, client extension, and final UI all work.

### Why it fails

Offline checks cannot prove current reachability, DOM/API structure, anti-bot behavior, browser extension permissions, LAN access, timing, clocks, deployment state, or visible interaction.

### Correct requirement interpretation

Static inspection, offline tests, CI, live producer runs, service execution, real client-browser feedback, and real Surface UI acceptance are separate evidence levels. Missing levels remain pending.

### Required implementation

Tie each claim to the exact revision and actual command, test, CI run, log, runtime file, screenshot, or interaction. Do not upgrade static evidence to runtime PASS.

### Acceptance evidence

A final acceptance record must state the exact revision, checks run, checks not run, current source/browser/service evidence, remaining gaps, and a verdict no stronger than the evidence.
