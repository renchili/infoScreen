# InfoScreen supplementary context

This document records project-specific background that is difficult to infer from code alone. It focuses on requirements and real deployment observations that changed the current implementation. It does not repeat the complete architecture, deployment procedure, or source-code inventory.

## TTY visual language without a dot-matrix background

The requested TTY style comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, and clear panel boundaries.

A dot-matrix wallpaper, pixel grid, noisy CRT texture, or decorative pattern was explicitly not required. Those effects compete with the information and reduce readability on an always-on display. The background should remain quiet; the terminal character should come from typography and information layout.

## Schedule export through macOS EventKit

Schedule data is exported on the Mac because macOS Calendar already owns the Calendar accounts, permissions, timezone context, and authoritative event view. The Surface does not maintain a second Calendar account or attempt to recreate EventKit access.

The active path is:

```text
macOS Calendar/EventKit
  -> mac/export.py
  -> mac/schedule.json
  -> mac/sync_schedule.sh
  -> SSH/SCP
  -> surface/.env/schedule.json
  -> /schedule.json
  -> calendar_board.js
```

This design keeps private Calendar configuration on the device that already owns it while allowing the Surface to remain a simple runtime and display host.

## EventKit-capable Python and LaunchAgent execution

A normal `python3` executable is not automatically suitable for the Mac exporter. The actual requirement is a Python runtime that can import the macOS `EventKit` bridge.

The setup script therefore verifies candidate Python executables with `import EventKit` and writes the selected executable to the uncommitted `mac/local.env` file. The LaunchAgent uses that explicit path instead of relying on the interactive shell environment.

The sync script also defines an explicit PATH, resolves its own directory, and writes logs under `~/Library/Logs/infoscreen-sync/`. These details exist because launchd does not run with the same environment as an interactive terminal.

## Canonical Schedule runtime destination

The Schedule push and the dashboard must use the same file. The canonical Surface destination is:

```text
~/infoscreen/surface/.env/schedule.json
```

The Mac setup script, sync script, HTTP server, Calendar board, Sync ticker, documentation, and tests all use this path. The sync script creates the remote runtime directory before copying the file.

A successful `scp` to another path does not update the page, even though the transfer itself succeeded.

## Schedule production, freshness, and board rotation

Schedule has three independent timing behaviours:

- the Mac LaunchAgent normally exports and pushes a new file every 120 seconds;
- the Sync ticker checks the served file age every 60 seconds;
- the Calendar board rotates already-loaded event groups every seven seconds.

The board reads `schedule.json` at page startup. A newly pushed file can therefore appear fresh in the Sync ticker while the board continues rotating the previous in-memory list until the page reloads.

The split-flap board animation is presentation only. It does not refresh Calendar data.

## Market redundancy after public data-source instability

The Market implementation does not rely on one unauthenticated public quote endpoint. Real use showed that public sources can reject requests, rate-limit, return HTML, omit expected fields, or behave differently for stocks and ETFs.

The current per-symbol fallback order is:

1. Nasdaq stock endpoint;
2. Nasdaq ETF endpoint;
3. CNBC quote service;
4. Stooq daily CSV;
5. Yahoo chart data;
6. the previous usable item from `market.json`.

Every symbol runs through the fallback chain independently. One provider failure or unsupported symbol therefore does not erase quotes that succeeded through another path.

The runtime payload records the aggregate source as `nasdaq+cnbc+stooq+yahoo`, while every row records the provider that actually supplied that value.

## Explicit stale and failed Market rows

When every live provider fails for a symbol, the previous usable quote may be retained. The retained value is explicitly marked:

```text
session: STALE
provider: stale-cache
```

The provider errors remain attached to the row. When no live value and no previous value exist, the row is written as `N/A` with `session: ERR` and `provider: none`.

This preserves useful last-known information during temporary outages without presenting it as current or inventing a plausible price.

## Market movement and provider-state presentation

Market movement, provider state, and runtime metadata have different meanings:

- percentage movement controls the up/down/flat arrow and colour;
- session/provider labels describe where or in what state the quote was obtained;
- the file-level source and timestamp describe the generated runtime payload.

A negative percentage must remain visually negative even when a session label is present. Session labels such as `NSDQ`, `CNBC`, `DLY`, `STALE`, or a Yahoo market state are supplementary metadata and must not replace the movement semantics.

The Market card and the global Market tape use the same `market.json` rows so they present the same price and direction.

## Runtime Market symbol configuration

The symbol list is runtime configuration rather than source-code configuration.

```text
Committed defaults: surface/conf/market_config.default.json
Active symbols:     surface/.env/market_config.json
```

The UI uppercases symbols, removes duplicates, and keeps at most 12. `SAVE` writes the active configuration and then runs a refresh. `REFRESH` runs the producer without changing the list.

Browser local storage only helps repopulate the control when the API cannot be read. The producer reads the runtime JSON file as the authoritative configuration.

## Shared Market and Weather producer

Market and Weather are produced by the same one-shot job, `surface/fetch_live_data.py`, and the same five-minute systemd timer. A manual Market refresh therefore also refreshes Weather.

They remain separate products with different runtime files, schemas, panels, and freshness thresholds. A Weather failure preserves available previous fields but changes the status to `ERR` and records the current error instead of silently presenting the old reading as a successful refresh.

## Per-file Sync freshness

A real display remained online while runtime data had not been updated for a long period. A generic display-online message was therefore insufficient.

The Sync ticker observes the final served artifacts separately:

- `SCHEDULE` → `/schedule.json`;
- `WEATHER` → `/weather.json`;
- `MARKET` → `/market.json`;
- `NEWS` → `/event_stream.json`.

It reports `OK`, `STALE`, `MISS`, or `ERR` together with `LATEST` and `AGE`, calculated from the HTTP `Last-Modified` header.

This verifies the final producer-to-runtime-to-HTTP path. It does not identify the failing internal provider, and a large `AGE` can also expose clock skew between the browser, Surface, and Mac.

## Synchronized multilingual News display

The product requirement is that the English, French, and Chinese rows synchronously display corresponding versions of the same content. The three rows must advance together, in the same direction and at the same speed, so the same position across EN, FR, and 中文 always refers to the same story.

English and Chinese should prioritise Singapore news. When one language does not provide the corresponding item, translation fills that language instead of substituting an unrelated story.

The current producer implements this requirement by selecting one real news item and creating an EN/FR/ZH representation for the same item. That shared item is an implementation mechanism, not the requirement itself. When any language cannot be produced after retries, the complete three-language item is skipped so the rows do not become misaligned.

Ticker motion is visual movement only. It does not prove that `event_stream.json` is fresh.

## Local Photo inputs and browser-safe outputs

The Photo wall was designed around local personal files, including iPhone HEIC images.

Original files remain under:

```text
surface/.env/photos/
```

The builder creates browser-facing outputs under `surface/.env/public_photos/` and writes `photos.json`:

- JPEG, PNG, and WebP inputs are normalized to web JPEG files;
- GIF files are copied without flattening their animation;
- HEIC/HEIF inputs are converted to JPEG with `ffmpeg` when available;
- a native image with the same stem takes priority over a HEIC duplicate;
- generated URLs include the output modification time for cache invalidation.

The browser reads only `photos.json` and `/public_photos/*`; it does not enumerate arbitrary local filesystem paths.

## Local Events validation in the real deployment environment

Local Events depends on live official pages, JavaScript rendering, the deployment network, region, cookies, timing, anti-bot controls, and source-site changes. Repository tests cannot prove that a source is reachable today or that it still produces the stored DOM or structured payload.

The effective validation loop includes the project owner on the real Surface or an equivalent real browser/network environment:

1. run the collector against the real sources;
2. inspect the displayed card and runtime JSON;
3. identify the affected organisation and exact page;
4. inspect `debug_by_source`, structured payloads, rendered cards, detail-page evidence, and rejection reasons;
5. change the smallest appropriate source configuration, adapter, extraction rule, or output policy;
6. add an offline regression test that preserves the observed case;
7. rerun the real collector and inspect the final UI.

An offline test protects a known parsing or policy case. It does not replace the initial or final live-source verification.

## Source-specific Local Events collection

The collector is source-specific because the official sites do not expose one stable event contract.

Observed patterns include:

- structured JSON returned through XHR or embedded page state;
- cards that appear only after JavaScript rendering;
- listing cards with incomplete or ambiguous dates;
- useful fields available only on detail pages;
- facilities, memberships, promotions, navigation objects, and operating information mixed with event data;
- source-specific date and venue layouts;
- pages that time out, block automation, or return partial coverage.

`surface/conf/event_sources.json` therefore stores official entrypoints, allowed domains, default venues, source order, and adapter choice. The shared collector provides common stages, while targeted handling remains where real pages require it.

A targeted rule that appears unnecessary in an isolated test may still be required by the live rendered page. A rule may also become obsolete after a site redesign. Live-page evidence is required before removing or generalising it.

## Positive event intent from the SAFRA Carpark result

A real Local Events result displayed a SAFRA record titled `Carpark`, with a 2024–2029 range and the description `Carpark Rates`. The source exposed enough structured fields for the record to look event-shaped even though it was facility information.

The result established that a title and date range do not prove event meaning. It did not establish that the word `carpark` should be added to a growing blacklist.

The current structured-data rule requires positive event intent through an explicit event/programme/activity type or a relationship to an official event-oriented listing/detail route. An untyped dated object outside that context is not automatically accepted.

`tests/test_official_feeds.py` preserves the known distinction between:

- the SAFRA facility record outside the event route;
- another dated membership record;
- an untyped record inside an event route;
- an explicitly typed Event outside that route.

These tests preserve the logic derived from the observed false positive. They do not prove SAFRA's current live page structure or accessibility.

## Listing extraction and selective detail enrichment

Some official listing cards contain enough information to produce an event directly. Others omit a complete date, venue, or description and require a detail-page read.

The collector therefore supports rendered listing extraction and a selectively detail-enriched adapter path. It does not recursively crawl an entire site, because unrestricted crawling increases runtime, duplicates, unrelated content, and blocking risk.

A stored fixture can prove that a known detail response is parsed correctly. It cannot prove that the live detail page is still reachable or still exposes that response.

## Per-source debug evidence

A total result count cannot explain why coverage changed. Failure can occur during page access, structured extraction, rendered-card discovery, pagination, detail enrichment, date parsing, event-intent validation, normalization, or the total crawl budget.

The runtime therefore includes `debug_by_source`, with optional evidence under `surface/.env/local_event_debug_cards/`. This evidence connects a bad displayed card or missing organisation to a specific source and collection stage.

The evidence is also required to decide whether an existing targeted rule still matches the real page.

## Partial Local Events result protection

External sources fail independently. A crawl can finish with fewer organisations and fewer events because pages timed out, blocked automation, changed structure, or exceeded the job budget.

When a new run is partial and contains fewer results than the previous complete run, the primary file remains the previous complete result. The incomplete run is written to:

```text
surface/.env/local_event_search_results.partial.json
```

with:

```text
write_policy: kept_previous_complete_result
```

This protects the always-on display from an immediate transient loss of coverage while retaining the incomplete run and its debug evidence for repair.

## Automated and live validation boundaries

Repository tests can prove deterministic behaviour for supplied local inputs, including date parsing, structured-versus-DOM preference, known event-intent cases, text normalization, partial-result retention, payload contracts, and captured regressions.

Repository tests cannot prove current source reachability, current DOM or JSON structure, anti-bot behaviour, pagination, complete organisation coverage, semantic correctness on the live page, real Surface timing limits, or acceptance of the final visible card.

A mocked browser, stored fixture, or successful `pytest` run must not be reported as live-source verification. When real-source or Surface validation has not happened, the implementation remains partially verified.
