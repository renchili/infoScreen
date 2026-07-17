# InfoScreen system architecture

This document explains what the system is, how components are separated, where every product data stream comes from, and why the implementation has source-specific behavior. It deliberately does not repeat deployment or recovery commands; those belong in `README.md`.

## 1. Product shape

InfoScreen is an always-on, local-first information screen. Its design priorities are:

- readable from a distance;
- compact but stable layout;
- predictable long-running behavior;
- local ownership of personal data;
- visible freshness and failure state;
- no cloud account requirement for local preferences;
- one renderer for each visible UI mount;
- explicit producer, runtime, API, and consumer ownership for every data stream.

The frontend is plain HTML, CSS, and JavaScript. The backend is a Python standard-library HTTP server plus short-lived producer jobs. Runtime persistence is local JSON rather than a database.

## 2. Deployment topology

```text
Mac
  macOS Calendar/EventKit
  LaunchAgent
  mac/export.py
  mac/sync_schedule.sh
  SSH/SCP
            |
            v
Surface or Ubuntu device
  systemd --user services and timers
  producer jobs
  surface/.env/*.json
  surface/serve_infoscreen.py
  HTTP on 127.0.0.1:8765
            |
            v
Browser kiosk
  surface/web/index.html
  surface/web/assets/css/*
  surface/web/assets/js/*
```

The Surface is the runtime host for HTTP, Market, Weather, News, Local Events, Photos, and the kiosk page. The Mac is the authoritative Calendar host because Calendar accounts and EventKit permissions exist there.

## 3. Runtime component boundaries

| Component | Lifecycle | Responsibility | Must not do |
| --- | --- | --- | --- |
| `surface/serve_infoscreen.py` | Long-running `infoscreen-http.service` | Serve the dashboard, runtime JSON, public photos, OpenAPI, and local mutation/refresh endpoints | Scrape external data, generate schedule data, or rewrite frontend files |
| `surface/fetch_live_data.py` | One-shot job | Fetch Weather and Market, apply provider fallback, write two runtime files | Render UI or own scheduling |
| `surface/fetch_event_stream.py` | One-shot job | Fetch RSS sources, build aligned EN/FR/ZH rows, write `event_stream.json` | Render ticker rows |
| `surface/search_local_events.py` | Compatibility wrapper | Preserve the command path used by systemd and HTTP | Contain the full collector implementation |
| `surface/jobs/local_event_search.py` | One-shot job | Configure crawl budgets, run the source-specific collector, normalize output, and protect verified results from partial replacement | Apply frontend truncation or preserve legacy rows without current candidate evidence |
| `surface/local_events_runtime/*` | Library | Render official activity lists, establish listing-card membership, enrich admitted cards, normalize fields, preserve source order, and record rejection/debug reasons | Write UI markup or admit arbitrary page-wide structured objects |
| `surface/build_photos_json.py` | One-shot manual job | Normalize/copy local photos and build the manifest | Scan photos from the browser |
| `mac/export.py` and `mac/sync_schedule.sh` | Mac LaunchAgent job | Export EventKit data and push `schedule.json` | Run on the Surface |
| Browser scripts | Long-running page session | Fetch runtime/API data, render owned mounts, handle local controls and visual rotation | Produce authoritative external data or repair backend data quality |

Runtime state belongs under `surface/.env/`. It is device state or personal data and is not source code.

## 4. Three refresh layers

The implementation has three independent timing layers. Documentation and troubleshooting must not collapse them into one generic “refresh” concept.

### 4.1 Producer refresh

A producer refresh fetches or generates data and writes runtime JSON.

| Data | Scheduler | Frequency | Runtime output |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes | `market.json`, `weather.json` |
| News | `infoscreen-event-stream.timer` | 5 minutes | `event_stream.json` |
| Local Events | `infoscreen-local-events.timer` | 6 hours | `local_event_search_results.json` |
| Calendar | Mac LaunchAgent | 120 seconds by default | `schedule.json` pushed to the Surface |
| Photos | Manual builder | No supported timer | `photos.json`, `public_photos/` |

### 4.2 Browser data reload

A browser reload re-reads existing runtime data. It does not invoke the producer unless the UI calls a POST refresh endpoint.

| UI data | Browser read behavior |
| --- | --- |
| Market | Page load and every 60 seconds; also after Market POST refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | `HEAD` on page load and every 60 seconds |
| Local Events | Page load and immediately after POST location search; no periodic GET |
| Calendar | Page load only; no periodic GET |
| Photos | Page load and every 5 minutes |

### 4.3 Visual rotation

Visual rotation changes which already-loaded item is shown.

| UI | Rotation behavior |
| --- | --- |
| Local Event card | 15 seconds, with previous/next controls |
| Calendar board | 7 seconds per visible group |
| Photo wall | 9 seconds per image |
| News and Market tapes | Continuous animation over already-rendered DOM |

This separation explains why a producer can update a file while a Local Event or Calendar panel still displays the previously loaded in-memory list until the page reloads.

## 5. UI ownership, interaction, and data source map

Every visible mount has one renderer owner.

| Product area | Browser owner | User interaction | Runtime/API | Producer and data source |
| --- | --- | --- | --- | --- |
| Clock, date, refresh time, page uptime | `dashboard.js` | None | No runtime file | Browser clock; uptime is page-session duration |
| Market card and global tape | `dashboard.js` | Read-only quotes | `/market.json` | `fetch_live_data.py`; Nasdaq → CNBC → Stooq → Yahoo → previous cache |
| Market configuration panel | `market_custom.js` | Gear, symbol input, `SAVE`, `REFRESH` | `GET/POST /api/market-config`, `POST /api/market-refresh` | User symbols in `market_config.json`; refresh invokes `fetch_live_data.py` |
| Weather | `dashboard.js` | None | `/weather.json` | `fetch_live_data.py`; Open-Meteo, Singapore coordinates |
| Local Event card | `local_event_card.js` | Previous, next, location search, official link | `GET/POST /api/local-events/search` | Source-specific official collector configured by `event_sources.json` |
| Sync ticker | `local_event_card.js` | None | `HEAD` on four runtime paths | Observes file `Last-Modified`; does not produce data |
| EN/FR/ZH News | `local_event_card.js` | Continuous ticker only | `/event_stream.json` | `fetch_event_stream.py`; RSS sources plus translation |
| Photo wall | `local_event_card.js` | None | `/photos.json`, `/public_photos/*` | User files processed by `build_photos_json.py` |
| Calendar board | `calendar_board.js` | None | `/schedule.json` | Mac EventKit export and SCP push |
| CPU/MEM/DSK/NET bars | `dashboard.js` | None | No runtime file | Browser `Math.random()` demo values |
| POWER/DISPLAY/NETWORK labels | Static HTML | None | No runtime file | Static text |

`market_custom.js` does not render quotes. `local_event_card.js` does not render Market. `dashboard.js` does not render News or Sync status. This prevents asynchronous scripts from overwriting each other’s final DOM.

## 6. Market and Weather pipeline

### 6.1 Shared producer

`infoscreen-live-data.timer` starts one producer that writes both Weather and Market. A manual Market UI refresh therefore also refreshes Weather.

```text
infoscreen-live-data.timer
  -> infoscreen-live-data.service
  -> surface/fetch_live_data.py
     -> surface/.env/weather.json
     -> surface/.env/market.json
```

### 6.2 Market providers and fallback

For each configured symbol, the producer tries:

1. Nasdaq stock and ETF endpoints;
2. CNBC quote service;
3. Stooq daily CSV;
4. Yahoo chart data;
5. the previous usable item from `market.json`.

A retained previous item is marked `provider: stale-cache` and `session: STALE`. A symbol with no live provider and no previous value is emitted with `price: N/A`, `provider: none`, and `session: ERR` so the failure remains visible.

Market symbols are runtime configuration. The default file is `surface/conf/market_config.default.json`; the active file is `surface/.env/market_config.json`; the API accepts up to 12 unique normalized symbols.

### 6.3 Weather source

Weather uses Open-Meteo with Singapore coordinates, timezone `Asia/Singapore`, and current temperature, apparent temperature, humidity, and weather code. The current location is code configuration in `fetch_live_data.py`, not a browser preference.

## 7. Multilingual News pipeline

`surface/fetch_event_stream.py` reads a fixed source list:

- Google News Singapore English search;
- CNA;
- Google News Singapore French search;
- France24;
- RFI;
- Google News Singapore Chinese searches;
- BBC Chinese.

The producer deduplicates exact titles, randomly selects up to eight base items, and builds a complete EN/FR/ZH triple for each selected item. Google Translate is used when the base item is not already in the target language. A triple is skipped when any target translation fails validation, preserving row alignment across all three tickers.

The runtime contract is:

```text
event_stream.json
  items_by_lang.en
  items_by_lang.fr
  items_by_lang.zh
  base_items
  errors
  selection
```

The UI row labels remain `EN`, `FR`, and `中文`; internal `TR-*` source labels are metadata, not row ownership labels.

## 8. Source-specific Local Events architecture

### 8.1 Product requirement

Local Events was developed to show verifiable nearby activity options with source, title, date/time, venue, description, and an official link. It was not designed as a general web search or a recursive site crawler.

The source set is intentionally curated because the official sites differ materially:

- some render cards only after JavaScript;
- some lists require deep scrolling or explicit load-more controls;
- some expose structured JSON that can improve a listed card;
- some require detail-page reads for better fields;
- some place unrelated dated objects in page-wide JSON or adjacent navigation;
- some need source-specific date or venue repair.

A single generic selector cannot produce reliable results across these sites, so the collector uses a shared listing-authority pipeline plus per-source configuration and targeted field repair.

### 8.2 Source inventory and adapter choices

The authoritative inventory is `surface/conf/event_sources.json`. Version 6 currently contains 18 organisations.

| Source | Adapter | Official listing coverage |
| --- | --- | --- |
| Children's Museum Singapore | `nhb` | Heritage/Children’s Museum activity and season listing pages |
| National Gallery Singapore | `rendered_dom_card` | What’s On listing and exhibition-filtered listing |
| National Museum Singapore | `nhb` | Today/upcoming overview, exhibitions, view-all |
| Asian Civilisations Museum | `nhb` | Exhibitions, lectures, programmes, guided tours |
| Peranakan Museum | `nhb` | Programmes listing |
| ArtScience Museum | `rendered_dom_card` | Museum What’s On pages |
| Science Centre Singapore | `rendered_dom_card` | Workshops, exhibitions, shows, and What’s On listings |
| National Library Board | `nhb` | NLB What’s On and LibCal calendar |
| onePA / People’s Association | `nhb` | onePA events |
| SAFRA | `rendered_dom_card` | SAFRA What’s On |
| One Punggol | `rendered_dom_card` | Events and happenings |
| Waterway Point | `nhb` | Happenings and promotions |
| Mandai Wildlife Group | `nhb` | Mandai events and attraction pages |
| Sentosa | `nhb` | Sentosa events |
| Resorts World Sentosa | `nhb` | RWS events |
| Gardens by the Bay | `nhb` | Calendar of events |
| Esplanade | `rendered_dom_card` | What’s On |
| The Kallang | `rendered_dom_card` | Things to do / events |

The adapter names are historical extraction hints. They may change how the official list is rendered or how card fields are discovered, but neither adapter may admit a row without a rendered official listing card.

### 8.3 Collection pipeline

```text
source configuration
  -> open each configured official activity-list URL with Playwright
  -> deep-scroll and operate list expansion controls until stable
  -> evaluate rendered DOM card boundaries
  -> require one canonical official detail URL, a usable date, and a usable title
  -> mark the card with official listing evidence
  -> capture XHR/embedded structured data only as supplementary candidates
  -> match supplementary data to an admitted list card by canonical URL or activity identity
  -> discard every unmatched structured record
  -> optionally enrich admitted cards from their own detail pages
  -> normalize title, date, venue, summary, and official URL
  -> validate current/future dates
  -> record listing admission and rejection evidence by source
  -> preserve configured source order
  -> normalize text
  -> write runtime JSON
```

The policy forbids recursive site crawling, sitemap-first collection, third-party aggregators as the primary source, and page-wide structured objects as independent output candidates.

### 8.4 Positive event intent

Positive event intent is established by membership in the correct configured official activity list. A title, date range, explicit `Event` type, or event-looking route is not enough on its own.

The rendered list card is the admission record. Structured XHR, embedded JSON, and detail-page JSON can improve the title, dates, venue, summary, or canonical URL only after they match that listed activity. Unmatched structured objects are discarded even when they are explicitly typed as events.

This prevents classes of false positives such as facilities, membership access, operating information, promotions with validity periods, and navigation state without maintaining an endless blacklist of titles or routes. It also avoids rejecting a legitimate listed activity merely because its title contains a word that appeared in a previous bad record.

### 8.5 Targeted source behavior

The current shared pipeline includes targeted behavior developed from observed official-site structure:

- National Gallery and other dynamic lists: deep-scroll and operate load-more controls until the set of visible links stabilizes;
- all sources: admit only isolated rendered list cards with one canonical official detail URL plus usable date and title evidence;
- structured sources: use structured data only when it matches an already admitted list card;
- detail-enriched sources: read only the admitted card’s own canonical detail page, and retain the list card when detail enrichment fails;
- Gardens by the Bay: preserve its targeted date-range and concise-venue field repair after listing admission;
- all sources: preserve configured default venues when extracted venue text is missing, narrative, or implausibly long.

These are collector rules rather than frontend exceptions because the API, debug evidence, runtime JSON, and page must all see the same accepted dataset.

### 8.6 Crawl budgets and configuration

`surface/jobs/local_event_search.py` sets deployment defaults through environment variables before importing the collector:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_EVENTS_MAX_SECONDS` | 520 | Total job budget |
| `LOCAL_EVENTS_SOURCE_CONCURRENCY` | 3 | Parallel source workers |
| `LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS` | 160 | Per-source budget |
| `LOCAL_EVENTS_MAX_LISTING_PAGES` | 2 | Listing pagination limit |
| `LOCAL_EVENTS_LOAD_MORE_ROUNDS` | 24 | Listing expansion attempts before stability stops the loop |
| `LOCAL_EVENTS_MAX_TOTAL_EVENTS` | 180 | Final collection cap |
| `LOCAL_EVENTS_NAV_TIMEOUT_MS` | 25000 | Navigation timeout |
| `LOCAL_EVENTS_DOM_TIMEOUT_MS` | 25000 | DOM timeout |
| `LOCAL_EVENTS_DETAIL_LIMIT` | 24 | Maximum supplementary detail-page reads per list run |
| `LOCAL_EVENTS_DETAIL_TIMEOUT_MS` | 16000 | Supplementary detail-page timeout |
| `LOCAL_EVENTS_NHB_DETAIL_LIMIT` | 18 | Legacy adapter detail limit retained for compatibility |
| `LOCAL_EVENTS_NHB_DETAIL_TIMEOUT_MS` | 16000 | Legacy adapter detail timeout retained for compatibility |
| `LOCAL_EVENTS_PAGE_SCREENSHOTS` | 0 | Optional page screenshot evidence |
| `LOCAL_EVENTS_CARD_SCREENSHOTS` | 0 | Optional card screenshot evidence |

The source inventory and adapter choice are configuration. List-card admission and field extraction are code and tests. Changing either requires evidence from the affected official page and a regression test or fixture representing the observed structure.

### 8.7 Output, partial-run protection, and evidence

The primary runtime file is:

```text
surface/.env/local_event_search_results.json
```

The payload includes accepted `results`, configured `sources`, and `debug_by_source`. Accepted rows carry `candidate_policy: official-listing-authority-v1`; debug data records listing admission, enrichment, source failures, and rejection reasons.

Before partial-result comparison, a previous payload is reduced to rows carrying the current verified candidate policy. When a run covers fewer sources than configured and would replace a larger verified result with fewer events, the job keeps the previous verified rows and writes the new incomplete evidence to:

```text
surface/.env/local_event_search_results.partial.json
```

The partial payload records `write_policy: kept_previous_verified_result`. Legacy rows without current listing evidence are not retained merely because they were present in an older complete file.

Debug card/page evidence is written under:

```text
surface/.env/local_event_debug_cards/
```

### 8.8 UI contract

The Local Event panel displays one accepted result at a time with:

- organisation/source at the top;
- title;
- `WHEN`;
- `WHERE`;
- description fitted to the available card height;
- official-link action;
- previous, next, search, and position controls.

The backend returns full accepted fields. The frontend owns visual fitting and ellipsis; it must not drop backend records based on title-specific rules.

The configured source order is preserved in runtime metadata and used by the browser, so events remain grouped by organisation rather than being mixed by unstable browser sort order.

## 9. Calendar pipeline

The schedule path is deliberately external-push rather than Surface-side account access:

```text
macOS Calendar/EventKit
  -> com.renchili.infoscreen.schedule-sync
  -> mac/export.py
  -> local schedule.json
  -> mac/sync_schedule.sh
  -> SSH/SCP
  -> surface/.env/schedule.json
  -> /schedule.json
  -> calendar_board.js
```

The Mac setup writes machine-specific SSH and Python configuration to `mac/local.env`. That file and the generated LaunchAgent are not committed.

The Calendar board loads the runtime file at page startup and rotates already-loaded items. The Sync ticker independently observes the Surface file age every 60 seconds.

## 10. Photo pipeline

```text
user files in surface/.env/photos/
  -> surface/build_photos_json.py
  -> normalized files in surface/.env/public_photos/
  -> surface/.env/photos.json
  -> /photos.json and /public_photos/*
  -> browser photo wall
```

The browser does not enumerate local files. The builder is manual in the supported deployment so private photo changes remain explicit.

## 11. Freshness observation

The left Sync ticker is an observer, not a scheduler or producer.

| Stat | Observed endpoint | Product dependency | Stale threshold |
| --- | --- | --- | --- |
| `SCHEDULE` | `/schedule.json` | Calendar | 600 seconds |
| `WEATHER` | `/weather.json` | Weather | 900 seconds |
| `MARKET` | `/market.json` | Market card/tape | 600 seconds |
| `NEWS` | `/event_stream.json` | Three-language ticker | 600 seconds |

The browser performs `HEAD` and calculates `AGE` from its current clock and the server’s `Last-Modified` header.

```text
OK     file exists and age is within threshold
STALE  file exists but age exceeds threshold
MISS   path or Last-Modified is absent
ERR    browser HEAD request failed
```

This contract monitors the final runtime artifact, allowing Mac push and Surface timers to share one freshness model without requiring identical JSON schemas.

## 12. HTTP and runtime boundary

The server exposes committed frontend assets and local runtime state. It does not synthesize producer results during ordinary GET requests.

- GET runtime endpoints return the current local file or a missing-runtime error payload.
- HEAD runtime endpoints return size and `Last-Modified` for freshness checks.
- Market config POST mutates the runtime symbol file.
- Market refresh POST invokes the shared live-data producer.
- Local Events POST invokes the source-specific collector with a location input.

Method, payload, side-effect, and caller details are defined in `docs/api-spec.md`.

## 13. Failure isolation

The architecture separates failures by owner:

- HTTP failure affects every panel even when runtime files are healthy;
- one producer failure affects only its runtime outputs;
- browser renderer failure affects only its owned mounts;
- Mac schedule failure affects Calendar but not Surface producers;
- a single Local Events source failure is recorded under that source and should not erase evidence from other sources;
- a partial Local Events run should not replace a larger verified runtime result;
- legacy Local Events rows without current listing evidence are not eligible for preservation;
- Market provider failure is isolated per symbol through the fallback chain.

This is why operator diagnosis starts from the visible product area, then follows UI → endpoint → runtime file → producer → external source.

## 14. Simulated and static page content

Current CPU/MEM/DSK/NET bars are generated with `Math.random()` in the browser. POWER, DISPLAY, NETWORK, `AC_ONLY`, `ONLINE`, and `LAN_OK` are static labels. Page uptime measures the current browser session.

These are not Surface OS monitoring. Replacing them with real monitoring requires a producer, runtime schema, endpoint, frontend renderer, freshness behavior, tests, and documentation as one coherent change.

## 15. Documentation boundaries

- `README.md`: the main project entrypoint covering overview, capabilities, data sources, interaction, refresh behaviour, project structure, deployment, operation, troubleshooting, and validation.
- `docs/design.md`: this architecture, source ownership, refresh layers, and implementation boundaries.
- `docs/api-spec.md`: HTTP interaction contract and side effects.
- `docs/questions.md`: project-specific clarifications, constraints, and supplementary explanations established during development.
