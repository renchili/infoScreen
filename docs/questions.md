# InfoScreen supplementary product explanations

This file collects project-specific clarifications that were established across the development discussions. It explains intended behaviour, visual constraints, data semantics, and implementation expectations that are easy to miss when reading only the source code or architecture tables.

## TTY visual language does not mean a dot-matrix background

The requested TTY style is primarily an information language: monospaced typography, compact spacing, clear panel boundaries, short labels, tabular values, restrained status colours, and a layout that resembles an operational terminal display.

It does not require a dot-matrix wallpaper, pixel grid, noisy CRT texture, or decorative background pattern. Those effects do not make the screen more terminal-like when they reduce contrast or compete with the data. The background should remain visually quiet. Any scanline or display effect must be subtle, optional, and subordinate to readability.

The visual identity should come from typography, alignment, hierarchy, borders, labels, and state presentation rather than from filling unused space with texture.

## Compact presentation must preserve the important information

InfoScreen is viewed as an always-on screen, often from a distance. Compact does not mean shrinking every element or filling every empty area. It means using the available space efficiently while keeping the most important values immediately readable.

Primary values such as time, Market movement, Weather, Local Event title/date/place, Schedule, and freshness state must not be hidden behind controls or decorative elements. Configuration controls should remain secondary and should not move or restyle the product data they configure.

A layout change in one panel must not cause unrelated panels to lose information, change established colour semantics, or become visually inconsistent.

## A component optimisation must stay inside that component

Requests to improve Local Events, Calendar, Photos, or another panel are scoped to that product area unless a shared contract genuinely has to change. Fixing the Local Event card must not redesign the Market card, remove News, hide Photos, alter Calendar behaviour, or replace the real Sync ticker.

Each visible mount therefore has one renderer owner:

- `dashboard.js` renders Market and Weather;
- `calendar_board.js` renders Calendar;
- `local_event_card.js` renders Local Events, Sync status, News, and Photos;
- `market_custom.js` owns Market controls and triggers the Market renderer instead of replacing it.

This boundary prevents one asynchronously loaded script from briefly showing correct data and then overwriting it with a second markup implementation.

## Visible content must be real product data, not invented filler

The dashboard must not fill empty areas with fake logs, invented development messages, `RESERVED` entries, fabricated incidents, or synthetic event/news content. A placeholder is acceptable only when it clearly represents a temporary product state such as loading, missing runtime data, or an explicit error.

When a producer has no valid data, the page should show the absence or failure and point to the responsible runtime file or job. It must not simulate normal content merely to keep the screen visually busy.

This requirement applies especially to News and Local Events, where invented text can be mistaken for externally sourced information.

## Sync status represents data freshness, not generic display health

`DISPLAY ONLINE` only says that the page is rendering. It does not answer whether Schedule, Weather, Market, or News is current.

The Sync ticker therefore reports each runtime artifact separately using:

- `OK`: the file exists and is within its freshness threshold;
- `STALE`: the file exists but is older than its threshold;
- `MISS`: the runtime path or `Last-Modified` header is absent;
- `ERR`: the browser could not complete the `HEAD` request;
- `LATEST`: the server file modification time visible to the browser;
- `AGE`: the difference between the browser clock and that modification time.

The ticker observes the final HTTP-served file. It does not replace the producer, and it does not prove which internal provider failed. A very large `AGE` may indicate a stopped producer, a failed Mac push, a wrong runtime path, or clock skew between the browser, Surface, and Mac.

## Refresh has three different meanings

The project separates three behaviours that were repeatedly confused during development.

**Producer refresh** fetches or generates new external data and writes runtime JSON. It is controlled by systemd timers, the Mac LaunchAgent, a manual command, or a POST refresh/search action.

**Browser reload** reads an existing runtime file again. A browser reload does not necessarily run the producer.

**Visual rotation** changes which already-loaded item is visible. Rotating every few seconds does not make the underlying data newer.

This distinction explains several otherwise confusing behaviours:

- Local Events may be regenerated by the six-hour timer while the page still holds the previous in-memory list until reload;
- Calendar may receive a new `schedule.json` from the Mac while the board continues rotating the old list until page reload;
- Market may reload every minute even though its background producer normally runs every five minutes;
- News ticker animation may continue smoothly while `event_stream.json` is stale.

## Market data and Market presentation are separate concerns

The Market panel has two responsibilities that should not be mixed.

The producer resolves configured symbols through a provider fallback chain and writes quote data. The UI renders symbol, price, movement, session metadata, source, and update time using stable visual semantics.

Positive and negative movement must remain visually distinct. Provider or session metadata must not overwrite the colour and class used for price movement. A configuration control may change symbols or request a refresh, but it must not introduce a second quote renderer.

When live providers fail, the project may retain the previous usable quote as `stale-cache`, but that state must remain visible. A missing value must remain `N/A`/error rather than being replaced with a plausible-looking number.

## Weather and Market share a producer but remain separate products

Weather and Market are both written by `surface/fetch_live_data.py`. The normal Surface timer and the Market refresh endpoint run that shared producer, so manually refreshing Market also refreshes Weather.

This shared execution path should not be confused with shared UI ownership. Market and Weather still have separate runtime files, separate display regions, and separate field mappings.

## The multilingual News rows must describe the same stories

The English, French, and Chinese rows are intended as three language views of the same selected stories. They are not three unrelated random feeds placed on aligned rows.

The producer therefore selects a base set of real RSS items and creates a complete EN/FR/ZH triple for each one. When one language cannot be produced or validated, that story is skipped rather than shifting the rows out of semantic alignment.

The News area must not fall back to fake logs, development status text, or unrelated filler. Errors belong in the runtime `errors` evidence and in a clear unavailable state.

## A Local Event must answer the useful event questions

A Local Event card is useful only when it provides enough information to decide whether to open the official page. The accepted data model should provide, when the source exposes it:

- **What**: event title;
- **When**: current or future date/time;
- **Where**: concise venue or location;
- **Who**: publishing organisation or host;
- a short description or reason to attend;
- an official link that can be opened for verification.

A title and a long validity range are not sufficient. A card that cannot establish a real event date or event identity should not be promoted merely because it occupies an event-shaped object on the source page.

## Local Events uses a single readable card with navigation

The panel uses one event card at a time because the available physical area cannot show several complete What/When/Where/Who records at a readable size.

The current interaction model therefore includes:

- automatic advance every 15 seconds;
- previous and next controls;
- a position counter;
- location search;
- a direct official-link action.

The carousel rotates accepted records already loaded in the browser. It does not perform a new source crawl on every transition.

## Local Events is deliberately source-specific

Local Events is not a general search-engine scraper and not a single universal selector. It is a maintained set of official organisation sources with explicit listing URLs, allowed domains, default venues, source order, and adapter choices.

The official sites expose materially different structures. Some publish structured JSON, some render cards only after JavaScript, some omit dates from listing cards, and some require detail-page reads. The collector therefore combines shared stages with targeted source behaviour.

Examples of targeted handling currently include:

- structured XHR/embedded-state extraction before DOM fallback;
- detail-page date enrichment for sources whose listing cards are incomplete;
- Gardens by the Bay date-range and venue repair;
- rejection of synthetic Mandai location cards;
- configured source ordering and per-source debug evidence;
- preserving the previous complete result when a new crawl is partial.

Source-specific development is part of the feature, not an accidental exception around a generic crawler.

## Event classification uses positive evidence, not an endless blacklist

Official structured data contains facilities, memberships, operating information, promotions, navigation objects, and other dated records beside real events. It is not possible to enumerate every non-event title such as `carpark`, `gym`, `membership`, or future variants.

The collector therefore requires positive event evidence. A structured record must establish event/programme/activity semantics through its type or its relationship to an official event-oriented listing/detail route. Title and `startDate`/`endDate` fields alone are not enough.

Negative quality checks remain useful as secondary safeguards, but they must not become the primary classifier. A real event is accepted because there is evidence that it is an event, not because its title avoided a growing list of banned words.

## Local Event quality belongs in the collector

A bad record should not be hidden only in the browser. The same accepted dataset is consumed by the UI, API, runtime inspection, and debug tools.

Title, date, venue, URL, duplication, structured event intent, and source-specific repairs therefore belong in the collector/extractor before runtime JSON is written. The frontend owns layout fitting and ellipsis only.

Rejections should leave evidence in `debug_by_source`, so an affected organisation can be traced to page access, pagination, structured extraction, rendered-card extraction, detail enrichment, date parsing, event-intent validation, or crawl budget.

## Partial Local Event crawls must not erase a better complete result

Official sources can fail independently or exceed their time budget. A new run may cover fewer sources and return fewer events than the previous complete run.

When that happens, the screen should keep the previous complete primary result instead of replacing it with an obviously degraded partial set. The incomplete run is retained separately in `local_event_search_results.partial.json` with its debug evidence.

This is availability protection, not permission to hide permanent failures. The partial output remains available so the source coverage problem can be repaired.

## Calendar authority remains on the Mac

The Surface displays Calendar information but does not own Calendar accounts or permissions. macOS Calendar/EventKit is the authoritative source.

The Mac exports and pushes `schedule.json`; the Surface stores, serves, monitors, and renders it. This avoids maintaining a second Calendar authentication system on the Surface and keeps private account configuration on the device that already owns it.

Calendar rotation and Calendar freshness are separate. The board rotates its loaded events, while the Sync ticker independently observes the served file age.

## Photos remain local and explicit

The Photo wall is personal content. User files remain under `surface/.env/photos/`, and the builder creates `photos.json` plus safe served copies under `public_photos/`.

The browser does not scan arbitrary filesystem paths and the project does not require a cloud photo account. Photo changes are explicit: update the local files, run the builder, and let the page reload the generated manifest.

## Decorative metrics are not system monitoring

The current CPU/MEM/DSK/NET bars are simulated browser values. POWER/DISPLAY/NETWORK labels are static text, and page uptime measures the current browser session.

These elements must not be described as Surface OS monitoring. Real monitoring would require an actual producer, runtime schema, endpoint, freshness model, failure state, renderer, and tests. A status-like appearance alone is not evidence of a monitored system.

## Failure states should explain the responsible boundary

The screen should fail visibly and specifically rather than silently substituting plausible content.

A useful failure state points toward the responsible boundary:

- page or asset failure → HTTP service/frontend;
- stale Market or Weather → shared live-data producer and runtime files;
- stale News → News producer and `event_stream.json`;
- bad or partial Local Events → source-specific collector and `debug_by_source`;
- stale Schedule → Mac LaunchAgent, SSH/SCP path, and `schedule.json`;
- missing Photos → local photo input, builder, and manifest;
- large Sync `AGE` → producer/push path, runtime mtime, HTTP header, or device clocks.

The product should preserve enough status and debug evidence to follow the visible panel back to its producer and source without inventing a successful-looking state.
