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

The English, French, and Chinese rows synchronously display corresponding versions of the same content, advance in the same direction and at the same speed, and keep the same position aligned across EN, FR, and 中文. English and Chinese prioritise Singapore news. Translation fills a missing language instead of substituting an unrelated story.

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

Official sites differ in structured JSON, JavaScript rendering, listing completeness, detail-page requirements, non-event records, date and venue layouts, pagination, anti-bot behaviour, and timing. Unrestricted crawling increases duplicates, unrelated content, runtime, and blocking risk. Offline fixtures do not prove current reachability or page structure.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official entrypoints, allowed domains, default venues, source order, and adapter choice. The shared collector handles common stages while targeted source behaviour remains where real page evidence requires it. Live-source verification and offline regression have different roles.

### Required implementation

Use structured XHR or embedded state before rendered DOM fallback, selectively enrich eligible detail pages, avoid recursive site crawling, preserve official URLs and configured source order, and retain source-specific rules only when supported by current page evidence and regression cases.

### Acceptance evidence

For an affected organisation, evidence must include the real collector run, `debug_by_source`, captured page or card evidence when enabled, final runtime JSON, visible card output, and an offline regression case for the observed structure. A fixture or successful pytest run alone is not live-source verification.

## Local Events positive event intent

### Easy-to-make interpretation

A title plus `startDate` and `endDate`, or the absence of a small blacklist of words, can be treated as proof that a structured record is an event.

### Why it fails

A real SAFRA result displayed `Carpark` with a 2024-2029 range and `Carpark Rates`. Facility, membership, operating-information, and promotion records can be event-shaped without being activities a user can attend.

### Correct requirement interpretation

A structured record requires positive event intent through an explicit event, programme, or activity type, or a verified relationship to an official event-oriented listing or detail route. A blacklist is only supplementary and cannot be the primary semantic rule.

### Required implementation

Keep positive-intent validation in the collector before output. Preserve distinctions between explicitly typed events, untyped records inside event routes, and dated non-event records. Data-quality rejection belongs in the backend rather than frontend title hiding.

### Acceptance evidence

Regression tests must preserve the SAFRA facility record, another dated membership record, an untyped event-route record, and an explicitly typed Event outside that route. Live validation must confirm the rule against the current official source before claiming current coverage.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total result count is enough to diagnose coverage, and every completed crawl should replace the current primary file even when several sources failed.

### Why it fails

Failure can occur during page access, structured extraction, rendered-card discovery, pagination, detail enrichment, date parsing, event-intent validation, normalization, or the total crawl budget. Replacing a larger complete result with a smaller partial run causes transient source failures to remove valid events from the display.

### Correct requirement interpretation

The runtime includes `debug_by_source` and optional evidence under `surface/.env/local_event_debug_cards/`. When a new run is partial and contains fewer results than the previous complete run, the primary file remains the previous complete result and the incomplete run is written to `surface/.env/local_event_search_results.partial.json` with `write_policy: kept_previous_complete_result`.

### Required implementation

Record per-source stage and rejection evidence, calculate whether source coverage is partial, preserve the previous complete primary file when the protection condition applies, and keep the partial payload for diagnosis.

### Acceptance evidence

Tests must cover complete-to-partial state transitions, result-count comparison, preservation of the primary file, creation of the partial file, `write_policy: kept_previous_complete_result`, and retained `debug_by_source`. A real failed-source run must show the same behaviour before deployment acceptance.

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

InfoScreen has two different outputs: operational service messages captured by systemd and deliberate command results such as Local Events JSON written for callers. Treating machine-readable result output as logging breaks the CLI/API contract, while leaving a long-running service with uncontrolled diagnostic output makes operations difficult.

### Correct requirement interpretation

The long-running HTTP server uses Python logging with level and destination controlled by the runtime environment. Short-lived producer jobs may emit concise completion or failure lines to stdout/stderr because systemd captures those streams. Deliberate machine-readable stdout remains a command result, not the primary logging system.

### Required implementation

Keep service messages concise and free of credentials, full request bodies, file contents, and personal data. Use stable component and operation names. Document the project-specific stdout/stderr boundary in `AGENT.md`. Do not replace command JSON with log records.

### Acceptance evidence

Static checks must distinguish service logging from command-result output, verify configurable HTTP log level and destination, reject accidental sensitive payload logging, and preserve Local Events command JSON. Operational acceptance must show useful startup, request, job completion, and failure records in the configured systemd journal or selected stream.

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
