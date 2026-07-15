# InfoScreen project discussion and decision record

This file distils the product and engineering decisions that emerged from the project discussions. Each record preserves the problem being discussed, the chosen direction, why that direction matters, and what the current implementation does as a result.

## Decision record 001 — Build a local-first, always-on information screen

**Discussion context**

The product was repeatedly described as a screen that should stay open for long periods and be understood at a glance rather than as a conventional application that requires constant navigation. The display needs to combine the current day, personal schedule, public information, market movement, nearby activities, photos, and data freshness without becoming a collection of unrelated widgets.

**Decision**

InfoScreen is a local-first kiosk dashboard for a Surface or Ubuntu display. It prioritises distance readability, compact information density, stable layout, and predictable long-running behaviour over decorative effects or a general-purpose desktop interface.

**Why this direction was chosen**

An always-on screen fails as a product when important information moves unpredictably, controls hide primary values, or the user must repeatedly interact with it. Local-first operation also keeps the screen useful when cloud accounts, remote dashboards, or third-party application sessions are unavailable.

**Resulting implementation**

The product uses a fixed multi-panel kiosk layout, plain HTML/CSS/JavaScript, a local Python HTTP server, local runtime JSON, and background jobs that operate independently from the browser session.

## Decision record 002 — Separate the Surface runtime from the Mac Calendar authority

**Discussion context**

The schedule is personal Calendar data, while the always-on display runs on a Surface or Ubuntu device. The Mac already owns the Calendar accounts, EventKit permissions, and the authoritative event view.

**Decision**

The Mac remains the schedule authority. It exports events through EventKit and pushes `schedule.json` to the Surface. The Surface stores, serves, monitors, and renders that file but does not create a second Calendar integration.

**Why this direction was chosen**

Duplicating Calendar account access on the Surface would introduce another authentication model, another source of truth, and more private-account configuration. The push model preserves the existing Mac permissions and keeps the Surface runtime account-free.

**Resulting implementation**

`mac/export.py` and `mac/sync_schedule.sh` run under `com.renchili.infoscreen.schedule-sync`. Machine-specific SSH and Python settings live in uncommitted `mac/local.env`. The runtime target is `surface/.env/schedule.json`.

## Decision record 003 — Keep source code and device state physically separate

**Discussion context**

The project produces frequently changing JSON, logs, debug pages, photo indexes, copied photos, and machine-specific configuration. Mixing those files with source made it difficult to know what should be committed, deployed, regenerated, or preserved.

**Decision**

All device runtime and personal data lives under `surface/.env/`. User photo inputs live under `surface/.env/photos/`. Generated runtime data is never treated as source code.

**Why this direction was chosen**

A clean boundary allows repository updates without overwriting personal state, prevents accidental commits of private content, and makes producer failures diagnosable by inspecting one runtime directory.

**Resulting implementation**

Weather, Market, News, Local Events, Schedule, photo manifests, copied public photos, partial Local Events results, debug evidence, and logs all use the `surface/.env/` boundary.

## Decision record 004 — Use short-lived producers and a simple local HTTP server

**Discussion context**

The screen needs periodic external data refresh, but the HTTP server should remain stable and should not block normal page requests while scraping or translating remote content.

**Decision**

External data collection is implemented as short-lived Python jobs that write runtime JSON and exit. `surface/serve_infoscreen.py` is a separate long-running server that serves the current state and exposes a small set of local interaction endpoints.

**Why this direction was chosen**

This separates serving from production, gives each job independent logs and retry behaviour, and allows systemd timers to schedule work without coupling every page request to external providers.

**Resulting implementation**

Weather/Market, News, Local Events, Photos, and Calendar each have a distinct producer path. The HTTP server reads the resulting files and only invokes producers for explicit POST refresh/search interactions.

## Decision record 005 — Treat producer refresh, browser reload, and visual rotation as separate behaviours

**Discussion context**

During development, the word “refresh” referred to several different operations: fetching new external data, reading an already-written runtime file, and rotating through items already loaded into the page. Conflating them made stale-data behaviour difficult to understand.

**Decision**

The design explicitly separates producer refresh frequency, browser data reload frequency, and visual rotation frequency.

**Why this direction was chosen**

A producer may be healthy while the browser still holds an older in-memory list. Conversely, a frequently animated panel may still be rotating stale data. Operators and future code changes need to know which layer is responsible.

**Resulting implementation**

Systemd and the Mac LaunchAgent own production. Browser scripts own periodic GET/HEAD behaviour. Local Events, Calendar, Photos, and ticker animations use independent rotation intervals.

## Decision record 006 — Monitor final runtime freshness inside the product

**Discussion context**

The screen needs to show whether the information it displays is current. The producers use different JSON schemas and run on different machines, including the Mac Calendar push.

**Decision**

Freshness is measured from the final runtime artifact using HTTP `Last-Modified`. The page reports `OK`, `STALE`, `MISS`, or `ERR` for Schedule, Weather, Market, and News.

**Why this direction was chosen**

Monitoring the final file verifies that the complete producer-to-runtime-to-HTTP path succeeded. It also provides one freshness model for both Surface timers and the Mac push without requiring every payload to share an `updated_at` schema.

**Resulting implementation**

`local_event_card.js` performs `HEAD` requests every 60 seconds and computes `AGE` using the browser clock. The ticker is an observer only; it never generates or repairs data.

## Decision record 007 — Give every visible mount one renderer owner

**Discussion context**

The dashboard contains independently loaded scripts and asynchronous data. When multiple scripts write the same DOM mount, correct content can appear briefly and then be replaced by older markup, different classes, or incompatible field mapping.

**Decision**

Every visible DOM mount has exactly one data renderer. Other scripts may trigger that renderer or observe the same runtime file, but they do not rewrite the mount.

**Why this direction was chosen**

Single ownership makes final UI state deterministic and makes a visible problem traceable to one consumer. It also prevents refresh-order races from becoming styling or data bugs.

**Resulting implementation**

`dashboard.js` owns Market and Weather; `calendar_board.js` owns Calendar; `local_event_card.js` owns Local Events, Sync, News, and Photos; `market_custom.js` owns only Market controls and calls `window.loadMarket()` after refresh.

## Decision record 008 — Keep Market values configurable while preserving visible failures

**Discussion context**

The Market panel needs user-selected symbols, but public quote providers can fail, rate-limit, return incomplete data, or behave differently across sessions. Important price and movement values must remain visible rather than hidden behind configuration controls.

**Decision**

Market symbols are locally configurable, quotes use a provider fallback chain, and failures remain explicit in runtime metadata and the UI.

**Why this direction was chosen**

No single unauthenticated provider is sufficiently reliable for an always-on display. Retaining a previous usable item is preferable to replacing it with an empty row, but stale data must be labelled rather than presented as live.

**Resulting implementation**

The producer tries Nasdaq, CNBC, Stooq, Yahoo, then previous `market.json`. Active symbols are stored in `surface/.env/market_config.json`; the gear panel saves configuration and invokes a refresh. Stale-cache and hard-error states remain visible per symbol.

## Decision record 009 — Keep the three News rows aligned to the same base stories

**Discussion context**

The screen presents English, French, and Chinese news simultaneously. Independent per-language feeds would produce unrelated rows and make the three-line display visually aligned but semantically inconsistent.

**Decision**

Select a base set of stories and generate a complete EN/FR/ZH version of each selected story. Skip a story when a complete validated translation triple cannot be produced.

**Why this direction was chosen**

The three rows should be alternate language views of the same information, not three unrelated random feeds. Skipping an incomplete triple is more coherent than shifting the rows out of alignment.

**Resulting implementation**

`fetch_event_stream.py` gathers official/RSS sources, deduplicates titles, selects up to eight base items, translates missing languages, validates output, and writes aligned arrays under `items_by_lang`.

## Decision record 010 — Build Local Events from curated official sources, not generic web search

**Discussion context**

The Local Event panel needs trustworthy title, date, venue, description, source, and official link. Search engines and aggregators return reposts, stale pages, SEO pages, facilities, promotions, and content with unclear ownership.

**Decision**

Local Events uses a curated inventory of official organisation listing and detail pages stored in `surface/conf/event_sources.json`. Third-party aggregators, recursive crawling, and sitemap-first collection are not the primary flow.

**Why this direction was chosen**

The user must be able to open the publishing organisation’s page and verify the event. Curated sources also make it possible to identify exactly which official site changed when coverage or extraction quality drops.

**Resulting implementation**

The configured inventory currently covers 18 official museum, library, community, attraction, shopping-centre, venue, and institution sources, each with allowed domains, listing entrypoints, default venue, source order, and adapter choice.

## Decision record 011 — Develop Local Events with shared stages plus source-specific adapters

**Discussion context**

Real official sites do not expose events in one consistent shape. Some have structured JSON, some require JavaScript rendering, some omit dates from listing cards, some require detail pages, and some mix event and non-event records in the same page state.

**Decision**

Use a common collection and normalization pipeline, but allow source configuration, adapter choice, and targeted source handling where the official site requires it.

**Why this direction was chosen**

A universal CSS selector or a single “smart” regex cannot reliably cover all official sites. Source-specific behavior is not an exception to the product; it is the implementation strategy that makes official-source coverage maintainable and testable.

**Resulting implementation**

The current adapters are `rendered_dom_card` and the historically named `nhb` detail-enriched mode. The collector reads network/embedded JSON, rendered cards, and eligible detail pages. Gardens by the Bay and Mandai have targeted handling based on observed source behaviour. Per-source debug evidence records coverage and rejection reasons.

## Decision record 012 — Require positive evidence that a record is an event

**Discussion context**

Official JSON and page state contain objects with titles and dates that represent facilities, memberships, operating information, promotions, or long validity periods. Rejecting only known bad words would require an endless list and would still miss new categories.

**Decision**

A structured record must establish why it is an event: explicit event/programme/activity type, relationship to the official event listing route, or an event-oriented detail route. Title and date fields alone are insufficient.

**Why this direction was chosen**

Positive intent blocks whole categories of false positives at the structured-data boundary. It is more general and safer than adding a new negative keyword after each bad record appears.

**Resulting implementation**

Structured extraction now validates event intent before a candidate enters the normal event conversion path. Generic title/date/venue quality rules still apply afterward, but no dedicated facility-name blacklist is the primary classifier.

## Decision record 013 — Make the collector, not the frontend, own Local Event quality

**Discussion context**

A bad Local Event record is visible in the page, the API, runtime JSON, and debugging tools. Hiding it only in the browser would leave every other consumer with inconsistent data and would conceal the real extraction problem.

**Decision**

Invalid links, bad titles, wrong dates, wrong venues, non-event structured objects, and duplicates are rejected or repaired before runtime JSON is written. The frontend only fits and renders accepted fields.

**Why this direction was chosen**

One accepted dataset must be shared by every consumer. Collector-level rejection also preserves a reason in `debug_by_source`, making source regressions diagnosable instead of silently hidden.

**Resulting implementation**

Local Event tests target extraction and acceptance behaviour. The browser does not contain title-specific hiding rules. Description truncation is a visual fitting concern only and does not mutate backend content.

## Decision record 014 — Preserve the previous complete Local Event result during partial crawls

**Discussion context**

Official sites can time out or fail independently. A run that reaches only some configured sources may return fewer events than the previous successful run even though the previous data is still more useful for the always-on screen.

**Decision**

When a new run is partial and would replace a larger previous complete result, retain the previous primary runtime file and write the incomplete run separately for diagnosis.

**Why this direction was chosen**

Transient source failure should not empty or sharply reduce the kiosk display. At the same time, the failed run must not be discarded because it contains the evidence needed to repair coverage.

**Resulting implementation**

The job writes incomplete evidence to `local_event_search_results.partial.json`, marks `partial` and `write_policy`, and keeps the previous complete `local_event_search_results.json` when the protection condition applies.

## Decision record 015 — Present Local Events as one source-verifiable card at a time

**Discussion context**

The Local Event panel has limited physical space but each result needs enough context to be useful: organisation, title, time, place, description, and official link. A dense multi-card list made each event too small and reduced source visibility.

**Decision**

Show one event card at a time, group results by configured organisation order, auto-advance, and provide previous, next, location search, position count, and official-link controls.

**Why this direction was chosen**

One-card presentation preserves readable type and makes the source and official action clear. Source grouping provides a stable browsing context and prevents unstable cross-source date sorting from making the sequence unpredictable.

**Resulting implementation**

The panel advances every 15 seconds, retains manual navigation, stores the last location in browser local storage, and requests a new source-specific collection through the local API when the user searches another location.

## Decision record 016 — Keep the Photo wall entirely local

**Discussion context**

The Photo wall is personal content and should not depend on a cloud gallery, remote account, or browser filesystem access.

**Decision**

User photos remain under `surface/.env/photos/`. A local builder creates a safe manifest and copied public files. The browser only reads the generated manifest and served copies.

**Why this direction was chosen**

This preserves privacy, avoids cloud authentication, and creates a stable HTTP contract without exposing arbitrary local filesystem paths to the browser.

**Resulting implementation**

`build_photos_json.py` writes `photos.json` and `public_photos/`. The supported deployment keeps this refresh manual so changes to private photos are explicit.

## Decision record 017 — Do not describe decorative status values as system monitoring

**Discussion context**

The page includes CPU/MEM/DSK/NET bars and POWER/DISPLAY/NETWORK labels, but the current implementation has no OS metrics producer or health API behind those elements.

**Decision**

Treat the bars as simulated display values and the labels as static text. Do not use them to claim Surface health or monitoring coverage.

**Why this direction was chosen**

A monitoring label without a producer, schema, endpoint, freshness model, and failure state creates false confidence. The product already has real runtime freshness monitoring and must keep that distinction clear.

**Resulting implementation**

The demo bars are named accordingly in code and documentation. A future real-monitoring implementation must replace the complete producer-to-renderer chain rather than relabel the existing random values.
