# InfoScreen system architecture

This document explains system boundaries, data ownership, refresh behavior, Local Event collection, operator review, and client-device browser feedback. Deployment and recovery commands belong in `README.md`.

## 1. Product shape

InfoScreen is an always-on, local-first information screen. Its design priorities are:

- readable from a distance;
- compact but stable layout;
- predictable long-running behavior;
- local ownership of personal data;
- visible freshness and failure state;
- no cloud account requirement for local preferences;
- one renderer for each visible UI mount;
- explicit producer, runtime, API, and consumer ownership.

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
  HTTP on 0.0.0.0:8765
        |                    |
        v                    v
Surface kiosk browser   Operator browser on another trusted LAN device
surface/web/index.html  /local-events/studio/
                        optional unpacked Chrome helper
                        official listing pages in that client browser
```

The Surface is the runtime host for HTTP, Market, Weather, News, Local Events, Photos, review state, and the kiosk page. The Mac is authoritative for Calendar. Interactive Event-position feedback is performed in the browser on the device currently used by the operator, not necessarily on the Surface.

## 3. Runtime component boundaries

| Component | Lifecycle | Responsibility | Must not do |
| --- | --- | --- | --- |
| `surface/serve_infoscreen.py` | Long-running `infoscreen-http.service` | Serve frontend, runtime JSON, photos, OpenAPI, and local mutation/refresh endpoints | Scrape external data, generate Calendar data, or rewrite frontend files |
| `surface/fetch_live_data.py` | One-shot job | Fetch Weather and Market, apply fallback, write runtime files | Render UI or own scheduling |
| `surface/fetch_event_stream.py` | One-shot job | Fetch RSS, build aligned EN/FR/ZH rows, write `event_stream.json` | Render ticker rows |
| `surface/search_local_events.py` | Compatibility wrapper | Preserve command path used by systemd and HTTP | Contain the full collector |
| `surface/jobs/local_event_search.py` | One-shot job | Configure crawl budgets, run collector, normalize output, protect verified results | Apply frontend filtering or preserve unverified legacy rows |
| `surface/local_events_runtime/*` | Library | Render official lists, establish membership, enrich details, review candidates, record diagnostics, persist feedback | Render browser UI or admit arbitrary page-wide structured objects |
| `surface/web/local-events/studio/` | Long-running browser page | Operator review, filtering, explicit collection, diagnostics, feedback status | Run external extraction itself |
| `surface/web/local-events/feedback-extension/` | Client-browser helper | Open an official page in the operator's Chrome, inject selection toolbar, submit DOM evidence | Depend on a visible Surface desktop or bypass server validation |
| `surface/build_photos_json.py` | One-shot manual job | Normalize/copy photos and build manifest | Scan photos from the browser |
| `mac/export.py`, `mac/sync_schedule.sh` | Mac LaunchAgent job | Export EventKit and push `schedule.json` | Run on the Surface |
| Browser scripts | Long-running page session | Fetch API/runtime data, render owned mounts, handle controls and rotation | Produce authoritative external data |

Runtime state belongs under `surface/.env/`. It is device state or personal data and is not source code.

## 4. Refresh layers

The implementation has independent timing layers. Documentation and troubleshooting must not collapse them into one generic refresh concept.

### 4.1 Producer refresh

| Data | Scheduler | Frequency | Runtime output |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes | `market.json`, `weather.json` |
| News | `infoscreen-event-stream.timer` | 5 minutes | `event_stream.json` |
| Local Events | `infoscreen-local-events.timer` | 6 hours | `local_event_search_results.json` |
| Calendar | Mac LaunchAgent | 120 seconds | `schedule.json` pushed to Surface |
| Photos | Manual builder | None | `photos.json`, `public_photos/` |

### 4.2 Browser data reload

A browser reload re-reads existing runtime or review state. It does not invoke a producer unless the UI calls a POST action.

| UI data | Browser read behavior |
| --- | --- |
| Market | Page load and every 60 seconds; after Market POST refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | `HEAD` on page load and every 60 seconds |
| Local Events | Page load and immediately after POST location search |
| Local Event review | Initial load, explicit action, manual reload, and tab return |
| Calendar | Page load only |
| Photos | Page load and every 5 minutes |

The Local Event review page does not poll and rebuild its entire DOM every three seconds. Such polling causes card flicker, scroll loss, duplicate helper work, and stale diagnostic overlays. The review page refreshes only at meaningful boundaries.

### 4.3 Visual rotation

| UI | Rotation behavior |
| --- | --- |
| Local Event card | 15 seconds, with previous/next controls |
| Calendar board | 7 seconds per visible group |
| Photo wall | 9 seconds per image |
| News and Market tapes | Continuous animation over already-loaded DOM |

## 5. UI ownership and data-source map

| Product area | Browser owner | User interaction | Runtime/API | Producer/data source |
| --- | --- | --- | --- | --- |
| Clock, date, refresh time, uptime | `dashboard.js` | None | No runtime file | Browser clock |
| Market card and tape | `dashboard.js` | Read-only quotes | `/market.json` | `fetch_live_data.py` |
| Market configuration | `market_custom.js` | Gear, symbols, save, refresh | `/api/market-config`, `/api/market-refresh` | Runtime config and shared producer |
| Weather | `dashboard.js` | None | `/weather.json` | Open-Meteo |
| Local Event card | `local_event_card.js` | Previous, next, location, official link | `/api/local-events/search` | Official collector |
| Local Event review | Studio scripts | Discover, preview, confirm/reject, collect, review | `/api/local-events/review/*` | Review store and Playwright collector |
| Browser feedback | Chrome helper content script | Browse, point, resize selection, submit | `/api/local-events/review/open-feedback` | Current client browser plus review store |
| Sync ticker | `local_event_card.js` | None | `HEAD` on runtime paths | Observes `Last-Modified` |
| EN/FR/ZH News | `local_event_card.js` | Continuous ticker | `/event_stream.json` | RSS plus translation |
| Photo wall | `local_event_card.js` | None | `/photos.json`, `/public_photos/*` | Photo builder |
| Calendar board | `calendar_board.js` | None | `/schedule.json` | Mac EventKit export |
| CPU/MEM/DSK/NET | `dashboard.js` | None | None | Simulated |
| POWER/DISPLAY/NETWORK | Static HTML | None | None | Static text |

Each visible mount has one renderer owner. Asynchronous scripts must not overwrite another owner's final DOM.

## 6. Market and Weather pipeline

`infoscreen-live-data.timer` starts one producer that writes both Weather and Market:

```text
infoscreen-live-data.timer
  -> infoscreen-live-data.service
  -> surface/fetch_live_data.py
     -> surface/.env/weather.json
     -> surface/.env/market.json
```

For each Market symbol, the fallback chain is Nasdaq stock/ETF, CNBC, Stooq, Yahoo, then the previous usable row. A retained previous row is `provider: stale-cache`, `session: STALE`; no live or cached value is `provider: none`, `session: ERR`, `price: N/A`.

Weather uses Open-Meteo with Singapore coordinates and timezone `Asia/Singapore`.

## 7. Multilingual News pipeline

`surface/fetch_event_stream.py` reads fixed Singapore and international sources, deduplicates exact titles, selects base items, and builds complete EN/FR/ZH triples. A triple is skipped when any target language cannot be produced after retries, preserving semantic alignment across rows.

Runtime contract:

```text
event_stream.json
  items_by_lang.en
  items_by_lang.fr
  items_by_lang.zh
  base_items
  errors
  selection
```

## 8. Source-specific Local Events architecture

### 8.1 Product requirement

Local Events must show verifiable activity options with source, title, date/time, venue, description, and an official link. It is not a general web search or recursive crawler.

Official sites differ in JavaScript rendering, list expansion, pagination, structured data, detail-page fields, anti-bot behavior, and timing. A single selector cannot reliably handle all sources.

### 8.2 Source inventory

The authoritative inventory is:

```text
surface/conf/event_sources.json
```

It defines source ID, display name, official home, allowed domains, configured list URLs, default venue, adapter, and order.

Adapter names are extraction hints. Neither `rendered_dom_card` nor `nhb` may admit an output row without a rendered card from a configured official list.

### 8.3 Collection pipeline

```text
source configuration
  -> open configured official list URL with Playwright
  -> deep-scroll and operate expansion/pagination controls
  -> identify rendered card boundaries
  -> require a usable title and exactly one canonical official detail URL
  -> do not require a date on the list card
  -> mark the card with official listing evidence
  -> optionally match XHR/embedded structured data to that admitted card
  -> discard unmatched structured records
  -> open the admitted card's official detail page
  -> extract/normalize title, date/time, venue, summary, public URL
  -> reject output if required current/future date cannot be established after detail enrichment
  -> record admission, rejection, detail, and failure evidence
  -> preserve configured source order
  -> write runtime JSON
```

The list proves activity membership. The detail page is authoritative for fields that the list omits, particularly date/time and specific venue.

The policy forbids recursive site crawling, sitemap-first collection, third-party aggregators as the primary source, and page-wide structured objects as independent output candidates.

### 8.4 Positive Event intent

Positive Event intent is membership in the correct configured official activity list. A title, date range, explicit `Event` type, or event-looking route is insufficient by itself.

Structured XHR, embedded JSON, and detail-page JSON can improve an admitted item only after matching the rendered list card by canonical URL or activity identity. Unmatched records are discarded even when typed as Events.

This prevents false positives such as facilities, membership access, operating information, promotions, and navigation state without relying on an endless title/path blacklist.

### 8.5 Detail-page authority

A correct listing card may omit date and venue. After admission, the collector follows only that card's official detail URL.

Detail enrichment can provide:

- canonical public URL;
- title;
- required current/future date or range;
- specific venue;
- summary;
- detail status and exact error.

Detail failure does not erase the evidence that a card existed on the list. Review candidates remain visible with `collected`, `incomplete`, or `failed` detail status so the operator can see where extraction failed.

### 8.6 Targeted source behavior

Shared and targeted behavior includes:

- deep scrolling and load-more operation until link/card state stabilizes;
- isolated card admission by one official detail URL and usable title;
- structured data enrichment only after list-card matching;
- configured URL-prefix rewrites for equivalent public detail routes;
- Gardens by the Bay date-range and concise-venue repair;
- configured default venue only when detail/structured venue is absent or implausible;
- source-specific API adapters where an official shared entry page returns Event JSON.

Targeted rules belong in the collector rather than frontend hiding because API, state, diagnostics, and visible cards must agree.

### 8.7 Crawl budgets

`surface/jobs/local_event_search.py` defines deployment defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_EVENTS_MAX_SECONDS` | 520 | Total job budget |
| `LOCAL_EVENTS_SOURCE_CONCURRENCY` | 3 | Parallel source workers |
| `LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS` | 160 | Per-source budget |
| `LOCAL_EVENTS_MAX_LISTING_PAGES` | 2 | Pagination limit |
| `LOCAL_EVENTS_LOAD_MORE_ROUNDS` | 24 | Expansion attempts |
| `LOCAL_EVENTS_MAX_TOTAL_EVENTS` | 180 | Final cap |
| `LOCAL_EVENTS_NAV_TIMEOUT_MS` | 25000 | Navigation timeout |
| `LOCAL_EVENTS_DOM_TIMEOUT_MS` | 25000 | DOM timeout |
| `LOCAL_EVENTS_DETAIL_LIMIT` | 24 | Detail reads |
| `LOCAL_EVENTS_DETAIL_TIMEOUT_MS` | 16000 | Detail timeout |
| `LOCAL_EVENTS_PAGE_SCREENSHOTS` | 0 | Optional page evidence |
| `LOCAL_EVENTS_CARD_SCREENSHOTS` | 0 | Optional card evidence |

Changing source configuration or extraction logic requires evidence from the affected official page and an offline regression representing the observed structure.

### 8.8 Output and partial-run protection

Primary runtime:

```text
surface/.env/local_event_search_results.json
```

Incomplete run evidence:

```text
surface/.env/local_event_search_results.partial.json
```

Debug evidence:

```text
surface/.env/local_event_debug_cards/
```

Accepted rows carry `candidate_policy: official-listing-authority-v1`. Before comparing a partial run with previous output, legacy rows without that policy are removed. A smaller partial run does not replace a larger verified result; the partial payload records `write_policy: kept_previous_verified_result`.

### 8.9 Operator review state

Operator review is separate from kiosk output:

```text
surface/.env/local_event_review/state.json
```

It contains:

- candidate list pages and decisions;
- Event candidates and decisions;
- collection metadata;
- per-listing recognition diagnostics;
- independent submitted DOM positions.

The workflow is:

```text
discover candidate list pages
  -> preview Events for a page
  -> confirm/reject/reset list page
  -> collect from confirmed pages
  -> inspect detail data and DOM evidence
  -> confirm/reject/reset Event candidate
```

A zero-result preview is not represented by a generic empty message. Each attempted listing records stage counts:

- HTTP/page load;
- visible links;
- allowed-domain links;
- possible detail links;
- extracted DOM cards;
- admitted list cards;
- DOM evidence;
- selectors;
- Event candidates;
- detail collected/incomplete/failed.

The first failed stage produces a stable `reason_code`. The browser renders the backend diagnostic rather than guessing why zero Events were returned.

### 8.10 Client-device browser feedback

The independent feedback flow is designed for an operator using another computer on the LAN:

```text
operator Studio page on client computer
  -> Chrome helper receives source and listing URL
  -> opens official page in same client Chrome profile
  -> user browses normally with cookies/filters/pagination
  -> POINT TO EVENT enables one selection click
  -> helper records selector/index/position/text/href/page URL
  -> extension service worker POSTs to Surface
  -> server validates source and original configured listing
  -> feedback is appended to review state
```

The helper is an unpacked Manifest V3 extension served from:

```text
surface/web/local-events/feedback-extension/
```

The Studio page can build a ZIP for installation. The helper uses the current device's browser session. It does not depend on the Surface display, mouse, graphical environment, or Surface-local browser profile.

A legacy server-side Playwright feedback mode remains callable with a normal listing URL, but the Studio page uses the client-device helper.

### 8.11 UI contract

The kiosk Local Event panel displays one accepted result at a time with source, title, `WHEN`, `WHERE`, summary, official link, and navigation controls.

The operator page displays review evidence and diagnostics. It reloads only after explicit actions, manual reload, and tab return; it must not continuously clear and rebuild the card lists.

## 9. Calendar pipeline

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

Machine-specific SSH and Python configuration belongs in uncommitted `mac/local.env`.

## 10. Photo pipeline

```text
user files in surface/.env/photos/
  -> surface/build_photos_json.py
  -> normalized files in surface/.env/public_photos/
  -> surface/.env/photos.json
  -> /photos.json and /public_photos/*
  -> browser photo wall
```

The browser does not enumerate local files.

## 11. Freshness observation

The Sync ticker is an observer, not a scheduler.

| Stat | Endpoint | Dependency | Stale threshold |
| --- | --- | --- | --- |
| `SCHEDULE` | `/schedule.json` | Calendar | 600 seconds |
| `WEATHER` | `/weather.json` | Weather | 900 seconds |
| `MARKET` | `/market.json` | Market | 600 seconds |
| `NEWS` | `/event_stream.json` | News | 600 seconds |

It performs `HEAD` and calculates age from the browser clock and `Last-Modified`.

## 12. HTTP and runtime boundary

The server exposes committed frontend assets and local runtime state. It does not synthesize producer results during ordinary GET requests.

- GET runtime endpoints return current local files or missing-runtime payloads.
- HEAD runtime endpoints return size and `Last-Modified`.
- Market config POST mutates runtime symbols.
- Market refresh POST invokes the shared live-data producer.
- Local Event search POST invokes the source-specific collector.
- Local Event review APIs mutate only review state or run explicit review collection.
- Client-browser feedback is validated and appended through the review API.

Method, payload, side-effect, and caller details are defined in `docs/api-spec.md`.

## 13. Failure isolation

- HTTP failure affects every panel even when runtime files are healthy.
- One producer failure affects only its outputs.
- Browser renderer failure affects only its owned mounts.
- Mac schedule failure affects Calendar but not Surface producers.
- One Local Event source failure is recorded under that source.
- A partial Local Event run does not replace a larger verified result.
- Legacy Local Event rows without listing evidence are not preserved.
- A zero-result review page records the first failed recognition stage.
- Client helper failure does not require or affect the Surface kiosk browser.
- Market provider failure is isolated per symbol.

Diagnosis follows UI -> endpoint -> runtime/review state -> producer/collector -> external source.

## 14. Simulated and static page content

CPU/MEM/DSK/NET bars use browser-generated demo values. POWER, DISPLAY, NETWORK, `AC_ONLY`, `ONLINE`, and `LAN_OK` are static labels. They are not Surface OS monitoring.

## 15. Documentation boundaries

- `README.md`: overview, operation, interaction, deployment, troubleshooting.
- `docs/design.md`: architecture, ownership, data flow, implementation boundaries.
- `docs/api-spec.md`: HTTP interaction contract and side effects.
- `docs/questions.md`: clarified requirements and acceptance evidence.
