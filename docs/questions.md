# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread and the evidence needed to accept their implementation. It is organised by product requirement rather than by conversation history or implementation attempt.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display can be interpreted as requiring a dot-matrix wallpaper, pixel grid, noisy CRT texture, or other decorative terminal effect.

### Why it fails

Those effects compete with the information, reduce readability on an always-on display, and confuse visual decoration with the actual requirement for a stable information hierarchy.

### Correct requirement interpretation

The TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear panel boundaries, and a visually quiet background.

### Required implementation

Keep the dashboard background restrained. Use typography, hierarchy, alignment, borders, and state presentation to create the terminal style. Do not add a dot-matrix wallpaper or decorative CRT noise as a substitute for information design.

### Acceptance evidence

A browser acceptance check must show readable content at the target display size, stable panel boundaries, no decorative pattern obscuring text, and consistent TTY-inspired information style across the page.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can be treated as a second Calendar client, a normal `python3` executable can be assumed to support EventKit, and a successful file copy to any convenient path can be treated as a successful Calendar update.

### Why it fails

macOS Calendar already owns the accounts, permissions, timezone context, and authoritative event view. A Python runtime without `import EventKit` cannot export Calendar data. launchd does not inherit an interactive shell environment. The dashboard only reads `~/infoscreen/surface/.env/schedule.json`, so copying elsewhere does not update the page.

### Correct requirement interpretation

Calendar data is authoritative on the Mac and follows macOS Calendar/EventKit -> `mac/export.py` -> local `mac/schedule.json` -> `mac/sync_schedule.sh` -> SSH/SCP -> `~/infoscreen/surface/.env/schedule.json` -> `/schedule.json` -> `calendar_board.js`.

### Required implementation

The setup script must probe candidate Python executables with `import EventKit`, store the selected executable and Surface target in uncommitted `mac/local.env`, install a LaunchAgent with explicit paths, create the remote runtime directory, and copy to the canonical runtime destination. The Mac LaunchAgent normally runs every 120 seconds; the Sync ticker observes freshness every 60 seconds; the Calendar board rotates already-loaded groups every seven seconds.

### Acceptance evidence

Evidence must show that the configured Python imports EventKit, the LaunchAgent runs without an interactive shell, `schedule.json` changes at the canonical Surface path, `/schedule.json` serves the new modification time and payload, and a page reload displays the updated Calendar data.

## Market resilience and runtime symbol authority

### Easy-to-make interpretation

Market data can be implemented with one unauthenticated quote endpoint, provider failure can be treated as an empty Market panel, and browser local storage can be treated as the authoritative symbol list.

### Why it fails

Public quote sources can reject requests, rate-limit, return HTML, omit fields, or behave differently for stocks and ETFs. A single failure must not erase values that another provider or a previous usable runtime row can supply. Browser state is not a reliable shared runtime configuration source.

### Correct requirement interpretation

Each configured symbol uses an independent fallback chain: Nasdaq stock, Nasdaq ETF, CNBC, Stooq daily CSV, Yahoo chart data, then the previous usable row from `market.json`. Active symbols are authoritative in `surface/.env/market_config.json`, while committed defaults remain in `surface/conf/market_config.default.json`.

### Required implementation

Normalize, deduplicate, and limit active symbols to 12. Preserve a previous usable quote as `session: STALE` and `provider: stale-cache` when live providers fail. Emit `session: ERR`, `provider: none`, and `price: N/A` when no live or cached value exists. Keep percentage movement separate from provider and session labels.

### Acceptance evidence

Tests and runtime inspection must prove provider fallback order, per-symbol failure isolation, stale-cache marking, visible ERR output when no value exists, persistence of the runtime symbol list, and consistent values and movement direction in the Market card and tape.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

A single display-online indicator or one generic refresh interval can be treated as proof that all page data is current.

### Why it fails

The HTTP server can remain online while individual runtime files are old, missing, or unreachable. Producer refresh, browser data reload, and visual rotation are independent behaviours and can show different timing states.

### Correct requirement interpretation

The Sync ticker observes `/schedule.json`, `/weather.json`, `/market.json`, and `/event_stream.json` separately through HTTP `Last-Modified`. It reports `OK`, `STALE`, `MISS`, or `ERR` with `LATEST` and `AGE`. Producer jobs write files, browser code reloads them on its own cadence, and rotation changes only the already-loaded visible item.

### Required implementation

Keep per-file thresholds and HEAD checks. Do not treat visual rotation as data refresh. Document and preserve separate schedules for producer jobs, browser reloads, and display rotation. Keep clock-skew diagnosis distinct from provider failure diagnosis.

### Acceptance evidence

Acceptance must demonstrate each status state, correct age calculation from the served file, independent failure of one runtime file, and the expected difference between a newly written file and a browser panel that has not yet reloaded it.

## Synchronized multilingual News

### Easy-to-make interpretation

Three independent news feeds that happen to scroll at the same speed can be presented as synchronized English, French, and Chinese content.

### Why it fails

The same screen position would refer to unrelated stories, so the rows would be visually aligned but semantically wrong. Substituting a different story when one language is unavailable breaks the product requirement.

### Correct requirement interpretation

The English, French, and Chinese rows synchronously display corresponding versions of the same content, advance in the same direction and at the same speed, and keep the same position aligned across all three languages. English and Chinese prioritise Singapore news. Translation fills a missing language instead of substituting an unrelated story.

### Required implementation

Select one real base item, generate a complete EN/FR/ZH representation, validate each language, and skip the whole triple when any language cannot be produced after retries. Keep ticker animation separate from runtime freshness.

### Acceptance evidence

Tests must verify equal row lengths, matching base-item identity at each index, valid text for every language, whole-triple rejection on translation failure, and synchronized browser movement. Runtime evidence must separately show a fresh `event_stream.json`.

## Local Photo processing

### Easy-to-make interpretation

The browser can enumerate personal files directly, HEIC files can be linked as-is, and all formats can be flattened to one static image type.

### Why it fails

Browsers do not reliably display HEIC/HEIF, direct filesystem enumeration exposes local paths, and flattening GIF files destroys animation. Duplicate native and HEIC versions can also create repeated photos.

### Correct requirement interpretation

Original files remain under `surface/.env/photos/`. The builder creates browser-safe outputs under `surface/.env/public_photos/` and writes `photos.json`. JPEG, PNG, and WebP are normalized to web JPEG; GIF is copied without flattening; HEIC and HEIF are converted with `ffmpeg` when available; a native image with the same stem takes priority.

### Required implementation

Keep personal originals outside the served tree, generate cache-busted browser URLs, avoid exposing arbitrary filesystem paths, preserve GIF animation, and report or skip unsupported conversions without inventing output.

### Acceptance evidence

Fixture tests must cover native normalization, GIF copying, HEIC/HEIF conversion or explicit skip behaviour, duplicate-stem precedence, manifest generation, cache invalidation, and browser retrieval only through `/photos.json` and `/public_photos/*`.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, a recursive crawler, or a generic search-engine scraper, and a stored fixture can prove that live source coverage is currently correct.

### Why it fails

Official sites differ in JavaScript rendering, listing completeness, detail-page fields, date and venue layouts, pagination, anti-bot behaviour, and timing. Unrestricted crawling increases duplicates, unrelated content, runtime, and blocking risk. Offline fixtures do not prove current reachability or page structure.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official activity-list entrypoints, allowed domains, default venues, source order, and adapter choice. A rendered card on one of those configured lists is the authority for whether an activity exists. Structured XHR, embedded state, and detail pages may improve fields only after list membership is established.

### Required implementation

Render and fully expand each configured official list, isolate cards that contain one official detail URL plus a usable date and title, then optionally enrich those admitted cards. Do not recursively scan the site or turn arbitrary XHR and embedded JSON objects into independent candidates. Preserve official URLs and configured source order.

### Acceptance evidence

For an affected organisation, evidence must include the real collector run, `debug_by_source`, listing-card evidence when enabled, final runtime JSON, visible card output, and an offline regression case for the observed structure. A fixture or successful pytest run alone is not live-source verification.

## Local Events positive event intent

### Easy-to-make interpretation

A title plus `startDate` and `endDate`, an explicit `Event` type, an event-looking URL route, or the absence of a small blacklist of words can be treated as proof that a structured record is an activity.

### Why it fails

A real SAFRA result displayed `Carpark` with a 2024-2029 range and `Carpark Rates`. Facility, membership, operating-information, promotion, and navigation records can be event-shaped, typed, or placed under broad site routes without being activities shown in the correct official activity list. Adding one rejection for every observed bad row never becomes complete.

### Correct requirement interpretation

Positive event intent means membership in the correct official activity listing. The list card is the admission evidence. Structured JSON and detail pages are supplementary field sources and cannot independently create an output row, even when an object is explicitly typed as `Event`. A legitimate listed activity is not rejected merely because its title contains a word previously seen in a bad record.

### Required implementation

Require a rendered, isolated card from a configured official listing with one canonical official detail URL, a usable date, and a usable title. Match structured data to that card by canonical URL or the same activity identity, discard every unmatched structured record, and keep rejection in the backend collector. Do not maintain per-record title, route, facility, membership, or navigation blacklists as the primary decision mechanism.

### Acceptance evidence

Regression tests must show that the SAFRA `Carpark Rates` object and another unmatched typed `Event` are rejected without naming new blacklist terms, that matched structured data enriches only its listed card, that a listed activity such as `Membership Workshop` remains accepted, and that a card without official listing evidence is rejected. Live validation against current sources is still required before claiming current coverage.

## Local Events detail-field authority

### Easy-to-make interpretation

Once a correct listing card is admitted, the source organisation name can be used as the final venue and an internal CMS path or listing URL can be exposed as the event URL even when the official detail page contains a more specific place and a stable public detail route.

### Why it fails

The organisation is often only the host, not the room, wing, level, branch, auditorium, or outdoor location. Some official sites expose both public and internal content paths. Falling back before reading an explicit detail-page `Where:`, `Location:`, or `Venue:` field discards correct information, while publishing the CMS or listing route prevents the card from opening the canonical public activity page.

### Correct requirement interpretation

The configured official listing proves membership. After admission, the official detail page is authoritative for the activity's specific venue and public detail URL. An explicit labeled detail-page venue overrides the configured default venue. Source-configured URL-prefix rewrites may map an internal CMS route to the equivalent public route, but must not enumerate individual activity slugs.

### Required implementation

Parse exact `Where:`, `Location:`, and `Venue:` label/value pairs from the admitted activity's detail page, prefer that value over structured/default venue data, normalize configured CMS path prefixes to public paths, remove fragments, and retain the listing URL separately as evidence rather than using it as the event URL.

### Acceptance evidence

A regression must model the observed National Gallery structure, proving that a CMS URL under `/content/nationalgallerysg/` becomes the corresponding `/sg/en/` detail URL and that `City Hall Wing, Level 4, Wu Guanzhong Gallery` replaces the generic `National Gallery Singapore` default. The config and implementation must contain no event-title or event-slug enumeration. Live collection and visible-card inspection remain required before runtime acceptance.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total result count is enough to diagnose coverage, and every incomplete crawl should replace the current primary file even when the previous file contains rows accepted by the active output contract.

### Why it fails

Failure can occur during page access, listing-card discovery, pagination, detail enrichment, date parsing, normalization, Studio evaluation, or the total crawl budget. Replacing a larger usable result with a smaller partial run removes valid events. Conversely, preserving rows carrying a known obsolete non-empty candidate policy keeps rejected behavior alive.

### Correct requirement interpretation

The runtime includes `debug_by_source`, `studio_activations`, and optional evidence under `surface/.env/local_event_debug_cards/`. Previous-cache eligibility mirrors the active output contract:

- `candidate_policy: official-listing-authority-v1` is eligible;
- a missing policy is eligible only when the previous payload identifies the current `structured-first` extractor family;
- a different non-empty policy is not eligible.

When a new run is partial and contains fewer results than that eligible previous set, the primary file remains the previous set and the incomplete run is written to `surface/.env/local_event_search_results.partial.json` with `write_policy: kept_previous_verified_result`.

### Required implementation

Record per-source admission and rejection evidence, aggregate completion by source rather than by listing debug row, preserve an existing `partial: true` signal, apply output-compatible cache filtering, retain the larger eligible primary result when protection applies, and keep the partial payload for diagnosis.

### Acceptance evidence

Tests must cover multi-listing completion aggregation, a failed listing making only its source incomplete, structured-first missing-policy cache compatibility, rejection of obsolete non-empty policies, result-count comparison, preservation of the primary file, creation of the partial file, and retained diagnostic evidence. A real failed-source run must show the same behaviour before deployment acceptance.

## Local Event Studio process boundary

### Easy-to-make interpretation

A rule editor can be implemented as a second web app, a second port, a cloud service, or a development-only page that stores selectors in repository files.

### Why it fails

A second server duplicates authentication and deployment concerns, breaks the existing single-process Surface model, and creates another availability dependency. Committing machine-specific selectors, screenshots, or captured HTML mixes runtime state with source code and can leak local evidence.

### Correct requirement interpretation

Local Event Studio is an operator page served by the existing `surface/serve_infoscreen.py` process on port `8765`. It operates only on source/listing pairs already committed in `surface/conf/event_sources.json`. All captures, drafts, published versions, history, and test runs are machine-local under `surface/.env/local_event_studio/`.

### Required implementation

Serve `/local-events/studio/` as ordinary static content from `surface/web/`. Reuse the existing HTTP process and existing Local Events systemd service/timer. Do not add another daemon, database, service, port, arbitrary source URL input, or cloud dependency.

### Acceptance evidence

Static and HTTP checks must show one server and port, no additional systemd unit, source/listing validation before browser launch or file writes, runtime storage under the active `INFOSCREEN_ENV_DIR`, and no committed snapshots or local rules.

## Local Event Studio rule authority and publication

### Easy-to-make interpretation

Saving a selector can immediately change production collection, a successful JSON schema validation can be treated as a tested rule, or rollback can overwrite history in place.

### Why it fails

An unfinished selector can suppress valid events or admit unrelated cards. Schema validation proves shape, not that the selector matches actual activity cards and extracts usable fields. Mutable history prevents proving which version produced a runtime result.

### Correct requirement interpretation

Drafts are inert. A draft must be evaluated against a stored snapshot, produce at least one accepted activity with no fatal errors, and retain the exact semantic fingerprint tested. Publication creates a monotonically increasing immutable version and activates only that configured source/listing pair. Rollback republishes a historical rule as a new version.

### Required implementation

Keep separate draft, published, and immutable history files. Persist accepted/rejected test rows and field evidence. Reject publication when the latest applicable test is missing, non-publishable, belongs to another listing, or no longer matches the draft fingerprint.

### Acceptance evidence

Tests must prove draft inactivity, atomic replacement, publish gating, stale-test rejection after a selector change, immutable history, monotonic versions, import as draft, export, and rollback as a new version. Live acceptance must identify the published version that produced the inspected runtime rows.

## Local Event Studio screenshot and selector semantics

### Easy-to-make interpretation

A rectangle drawn on a screenshot can be saved as the extraction rule, or pixel coordinates can be treated as stable evidence across page sizes and future renders.

### Why it fails

Coordinates change with viewport, responsive layout, fonts, consent banners, and dynamic content. A screenshot alone cannot identify the DOM relationship that provides a title, date, venue, or official URL.

### Correct requirement interpretation

The screenshot is a visual annotation surface. Each selectable rectangle is backed by captured DOM evidence. Published rules store CSS selectors, attributes, field mappings, exclusion selectors, and explicit fallback choices; they never store screenshot coordinates as extraction authority.

### Required implementation

Capture bounded DOM metadata with stable evidence IDs, overlay those elements on the screenshot, infer a repeated card selector from confirmed examples, and save only selector-based rules. Unsupported selector syntax must fail explicitly rather than being approximated.

### Acceptance evidence

Frontend and backend tests must show that coordinates remain UI-only, selector evaluation is deterministic against stored DOM, field evidence identifies the matched element and attribute, and a viewport change does not alter the persisted rule contract.

## Local Event Studio per-source activation and failure isolation

### Easy-to-make interpretation

Publishing one rule can globally replace the collector, a Studio failure can clear every source, or one selector can be copied to all organisations.

### Why it fails

The official sites have different structures. Global activation recreates the same cross-source failure that source-specific collection is designed to prevent. A source with several configured listings also needs listing-specific replacement rather than an all-or-nothing global filter.

### Correct requirement interpretation

The existing collector remains the default. Published Studio rules are applied after legacy collection and before final normalization. No published rule means no behavior change. Full source coverage replaces that source. Partial listing coverage replaces only legacy rows carrying matching listing evidence. Studio failure marks that source incomplete and leaves unrelated sources intact.

### Required implementation

Discover published rules per configured binding, use one reusable browser per Studio source, preserve unrelated results and debug rows, aggregate completion by source, synchronize detail-derived dates, carry rule version and field evidence, and retain existing partial-write protection.

### Acceptance evidence

Offline tests must cover no activation, full-source activation, partial-listing activation, unrelated-source preservation, zero acceptance, fatal selector errors, multi-listing source counts, detail precedence, and output metadata. Live migration must proceed one source at a time and inspect both the migrated source and at least one unaffected source.

## Local Event Studio semantic acceptance boundary

### Easy-to-make interpretation

A passing pytest suite, mocked Playwright result, stored screenshot, or generated report can prove that the current official page contains the right real-world activities.

### Why it fails

Code can verify selector mechanics and policy constraints, but it cannot decide without current page evidence whether a visible card is semantically an activity rather than a promotion, facility, navigation item, or stale page artifact. External structure and content can also change after fixtures are recorded.

### Correct requirement interpretation

Deterministic code and repository tests must be completed without pausing for operator input. Human participation begins only at the first real-source semantic migration. The operator confirms actual activity cards and fields in the local Studio preview; the resulting live output then provides runtime evidence.

### Required implementation

Separate evidence levels explicitly:

```text
static source review
-> deterministic unit/integration tests
-> real Studio capture
-> human card and field confirmation
-> publishable snapshot test
-> published version
-> live producer run
-> runtime JSON and visible-card inspection
```

### Acceptance evidence

For the first Esplanade migration, evidence must show at least two confirmed activity cards, correct title/when/where/public detail URL mappings, rejected non-activity rows, the exact published version, a live run, no non-activity rows in the inspected sample, and unaffected-source preservation. No earlier evidence level may be described as full live acceptance.

## Local Events package boundary

### Easy-to-make interpretation

The repository rule can describe `surface/jobs/local_events/` as the required package while the actual collector remains under `surface/local_events_runtime/`, leaving future changes unsure which path is canonical.

### Why it fails

A documented target that does not match imports, tests, wrappers, and deployment entrypoints creates a permanent architecture contradiction and encourages duplicate implementations or unsafe moves.

### Correct requirement interpretation

`surface/jobs/local_event_search.py` is the one-shot orchestration entrypoint. `surface/local_events_runtime/` is the canonical source-specific collection and extraction library. `surface/search_local_events.py` remains a compatibility command wrapper while systemd and HTTP callers use that path.

### Required implementation

Keep new collector modules and source-specific extraction logic under `surface/local_events_runtime/`, keep job orchestration under `surface/jobs/local_event_search.py`, and update repository rules, README, design, imports, and tests together if a future explicit migration changes this boundary.

### Acceptance evidence

Static checks must show one canonical collector package, no duplicate `surface/jobs/local_events/` implementation, imports resolving through the documented paths, systemd and HTTP callers retaining their command contract, and tests passing after any boundary change.

## Logging and command output

### Easy-to-make interpretation

Every line written to stdout by a short-lived producer can be classified as ad-hoc service logging, or the generic structured-logging contract can be applied without considering InfoScreen's systemd user-service deployment and command-output interfaces.

### Why it fails

InfoScreen has two different outputs: operational status captured by systemd and deliberate command results such as Local Events JSON written for callers. Treating machine-readable result output as logging breaks the CLI/API contract. Introducing a second logging stack without an operational requirement would add configuration and maintenance that the local kiosk does not use.

### Correct requirement interpretation

For this repository, systemd-captured stdout and stderr are the accepted operational output for the standard-library HTTP service and short-lived producer jobs. Concise startup, request, completion, skip, and failure messages are allowed. Deliberate machine-readable stdout remains a command result, not a log record. Structured JSON logs, request IDs, trace IDs, and an additional logging framework are not current product requirements.

### Required implementation

Keep operational output concise and free of credentials, tokens, full request bodies, private file contents, and unnecessary personal-data values. Preserve `SimpleHTTPRequestHandler` request diagnostics, the HTTP startup line, producer status lines, and Local Events command JSON as distinct output contracts. Document this project-specific boundary in `AGENT.md` and update implementation, tests, and design together if the logging model changes.

### Acceptance evidence

Static checks must distinguish operational status from command-result output, preserve Local Events command JSON, and confirm that repository rules explicitly narrow the generic logging contract. Operational acceptance must show useful startup, request, producer completion, skip, and failure records in the systemd journal without sensitive payloads.

## Validation boundaries

### Easy-to-make interpretation

A mocked browser, stored fixture, successful `pytest`, static source review, or reviewer-written report can be presented as proof that current external sources, systemd services, LaunchAgent execution, and the final Surface UI all work.

### Why it fails

Repository tests only prove deterministic behaviour for supplied local inputs. They cannot prove current external reachability, DOM or JSON structure, anti-bot behaviour, provider availability, timing budgets, device clocks, deployment state, or semantic correctness of the final visible result.

### Correct requirement interpretation

Static inspection, offline tests, HTTP/browser fixture checks, CI, live producer runs, service execution, and real-device UI acceptance are separate evidence levels. Missing levels remain explicitly pending. The implementation is only partially verified when the relevant real source or Surface UI has not been checked.

### Required implementation

Tie each claim to the exact branch or commit and to the actual command, test, CI run, log, runtime file, screenshot, or real interaction that supports it. Do not reuse stale evidence or upgrade static evidence to runtime PASS.

### Acceptance evidence

A final acceptance record must state the exact revision, checks run, checks not run, current runtime and browser evidence, source reachability evidence, service and scheduler evidence, remaining gaps, and a verdict that does not exceed the strongest available proof.
