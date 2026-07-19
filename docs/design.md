# InfoScreen system architecture

This document explains what the system is, how components are separated, where each product data stream comes from, and why Local Events uses source-specific behavior. Deployment and recovery commands belong in `README.md`; HTTP methods and payloads belong in `docs/api-spec.md`.

## 1. Product shape

InfoScreen is an always-on, local-first information screen. Its design priorities are:

- readable from a distance;
- compact but stable layout;
- predictable long-running behavior;
- local ownership of personal data and operator configuration;
- visible freshness and failure state;
- no cloud account requirement for local preferences;
- one renderer for each visible UI mount;
- explicit producer, runtime, API, and consumer ownership for every data stream.

The frontend is plain HTML, CSS, and JavaScript. The backend is a Python standard-library HTTP server plus short-lived producer jobs. Runtime persistence is local JSON and local files rather than a database.

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
  short-lived producer jobs
  surface/.env/*
  surface/serve_infoscreen.py
  HTTP on port 8765
            |
            +-> kiosk page /
            +-> Local Event Studio /local-events/studio/
            +-> runtime JSON and local APIs
```

The Surface is the runtime host for HTTP, Market, Weather, News, Local Events, Photos, the kiosk page, and Local Event Studio. The Mac remains the authoritative Calendar host because Calendar accounts and EventKit permissions exist there.

Local Event Studio does not add another server, port, daemon, database, or systemd service. It is static frontend content and bounded local APIs owned by the existing HTTP process.

## 3. Runtime component boundaries

| Component | Lifecycle | Responsibility | Must not do |
| --- | --- | --- | --- |
| `surface/serve_infoscreen.py` | Long-running `infoscreen-http.service` | Serve the kiosk, Studio page, runtime JSON, public photos, OpenAPI, and bounded local mutation/refresh APIs | Perform ordinary external collection during GET requests, generate Calendar data, or create arbitrary crawler targets |
| `surface/fetch_live_data.py` | One-shot job | Fetch Weather and Market, apply provider fallback, write two runtime files | Render UI or own scheduling |
| `surface/fetch_event_stream.py` | One-shot job | Fetch News sources, build aligned EN/FR/ZH rows, write `event_stream.json` | Render ticker rows |
| `surface/search_local_events.py` | Compatibility wrapper | Preserve the command path used by systemd and HTTP | Contain the full collector implementation |
| `surface/jobs/local_event_search.py` | One-shot job | Configure crawl budgets, run the existing collector, apply published Studio rules per source/listing, normalize output, aggregate source completion, and protect the primary result from smaller partial runs | Apply frontend hiding, globally activate draft rules, or preserve rows rejected by the active output contract |
| `surface/jobs/local_event_studio_capture.py` | One-shot job | Capture one configured official listing for Studio | Run as a new service or accept arbitrary source URLs |
| `surface/local_events_runtime/*` | Library | Render official lists, establish list-card membership, enrich admitted cards, evaluate Studio rules, preserve evidence, and normalize fields | Render UI markup or admit arbitrary page-wide structured objects |
| `surface/build_photos_json.py` | One-shot manual job | Normalize/copy local photos and build the manifest | Scan photos from the browser |
| `mac/export.py`, `mac/sync_schedule.sh` | Mac LaunchAgent job | Export EventKit data and push `schedule.json` | Run on the Surface |
| Browser scripts | Long-running page session | Fetch local data, render owned mounts, handle local controls and visual rotation | Produce authoritative external data or repair backend data quality |

Runtime state belongs under `${INFOSCREEN_ENV_DIR:-surface/.env}`. It is device state or personal data and is not repository source code.

## 4. Refresh layers

The implementation has three independent timing layers.

### 4.1 Producer refresh

| Data | Scheduler | Frequency | Runtime output |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes | `market.json`, `weather.json` |
| News | `infoscreen-event-stream.timer` | 5 minutes | `event_stream.json` |
| Local Events | `infoscreen-local-events.timer` | 6 hours | `local_event_search_results.json` |
| Calendar | Mac LaunchAgent | 120 seconds by default | `schedule.json` pushed to the Surface |
| Photos | Manual builder | No supported timer | `photos.json`, `public_photos/` |

A Studio snapshot capture is an explicit operator action. Publishing a rule changes which source/listing implementation the next Local Events producer run uses; publishing does not itself run the producer.

### 4.2 Browser data reload

| UI data | Browser read behavior |
| --- | --- |
| Market | Page load and every 60 seconds; also after Market POST refresh |
| Weather | Page load and every 5 minutes |
| News | Page load and every 5 minutes |
| Sync status | `HEAD` on page load and every 60 seconds |
| Local Events | Page load and immediately after POST location search; no periodic GET |
| Calendar | Page load only |
| Photos | Page load and every 5 minutes |
| Studio state | Page load, source/listing changes, capture completion, and explicit reload/test/publish actions |

### 4.3 Visual rotation

| UI | Rotation behavior |
| --- | --- |
| Local Event card | 15 seconds, with previous/next controls |
| Calendar board | 7 seconds per visible group |
| Photo wall | 9 seconds per image |
| News and Market tapes | Continuous animation over already-rendered DOM |

Visual rotation does not fetch or produce new data.

## 5. UI ownership and data source map

Every visible mount has one renderer owner.

| Product area | Browser owner | Interaction | Runtime/API | Producer or source |
| --- | --- | --- | --- | --- |
| Clock, date, refresh time, page uptime | `dashboard.js` | None | No runtime file | Browser clock |
| Market card and tape | `dashboard.js` | Read-only quotes | `/market.json` | `fetch_live_data.py` |
| Market configuration | `market_custom.js` | Gear, `SAVE`, `REFRESH` | `/api/market-config`, `/api/market-refresh` | Runtime symbol config and live-data producer |
| Weather | `dashboard.js` | None | `/weather.json` | Open-Meteo through `fetch_live_data.py` |
| Local Event card | `local_event_card.js` | Previous, next, location search, official link | `/api/local-events/search` | Existing collector plus published Studio routing |
| Local Event Studio | `local_event_studio.js`, `local_event_studio_test.js` | Capture, annotate, draft, test, publish, export/import, rollback | `/api/local-events/studio/*` | Configured official listings and machine-local Studio state |
| Sync ticker | `local_event_card.js` | None | `HEAD` on four runtime paths | Observes file metadata only |
| EN/FR/ZH News | `local_event_card.js` | Continuous ticker | `/event_stream.json` | `fetch_event_stream.py` |
| Photo wall | `local_event_card.js` | None | `/photos.json`, `/public_photos/*` | Photo builder |
| Calendar board | `calendar_board.js` | None | `/schedule.json` | Mac EventKit export and push |
| CPU/MEM/DSK/NET bars | `dashboard.js` | None | No runtime file | Browser demo values |
| POWER/DISPLAY/NETWORK labels | Static HTML | None | No runtime file | Static text |

Scripts do not repair or filter another script's owned data.

## 6. Market and Weather pipeline

`infoscreen-live-data.timer` starts one producer that writes both Weather and Market.

```text
infoscreen-live-data.timer
  -> infoscreen-live-data.service
  -> surface/fetch_live_data.py
     -> surface/.env/weather.json
     -> surface/.env/market.json
```

For each symbol the producer attempts Nasdaq stock/ETF data, CNBC, Stooq, Yahoo, then a previous usable runtime row. A retained row is marked `provider: stale-cache` and `session: STALE`. No live or cached value emits `price: N/A`, `provider: none`, and `session: ERR`.

Market symbols are authoritative in `surface/.env/market_config.json`; committed defaults remain in `surface/conf/market_config.default.json`. Weather uses Open-Meteo with Singapore coordinates and timezone `Asia/Singapore`.

## 7. Multilingual News pipeline

`surface/fetch_event_stream.py` reads a fixed set of Singapore-oriented and international RSS sources, selects base stories, and builds complete English, French, and Chinese representations. A row is skipped when any required language cannot be validated, preserving semantic alignment among the three visible ticker rows.

The runtime contract includes:

```text
event_stream.json
  items_by_lang.en
  items_by_lang.fr
  items_by_lang.zh
  base_items
  errors
  selection
```

Ticker movement is separate from producer freshness.

## 8. Source-specific Local Events architecture

### 8.1 Product requirement

Local Events shows verifiable activity options with source, title, date/time, venue, description, and an official link. It is not a general web-search scraper or recursive site crawler.

Official sites differ in JavaScript rendering, list expansion, pagination, detail fields, structured data, and source-specific date/venue layouts. One generic selector or one global blacklist cannot reliably cover them.

### 8.2 Source inventory

The authoritative inventory is:

```text
surface/conf/event_sources.json
```

It defines each source ID, display name, official home, allowed domains, configured activity-list URLs, default venue, adapter hint, and display order. Studio may operate only on these committed source/listing pairs.

The adapter names `rendered_dom_card` and `nhb` are historical extraction hints. Neither is allowed to produce an activity without a rendered card from a configured official activity list.

### 8.3 Existing collector pipeline

```text
source configuration
  -> render each configured official activity list with Playwright
  -> expand and paginate within configured budgets
  -> isolate rendered card boundaries
  -> require one official detail URL, usable date, and usable title
  -> use XHR/embedded structured data only as supplementary candidates
  -> match supplementary data to an admitted card
  -> discard unmatched structured records
  -> optionally enrich the admitted card from its own detail page
  -> normalize and validate fields
  -> preserve configured source order
  -> record per-source admission, rejection, and failure evidence
```

Positive event intent is membership in the correct configured activity list. A title, date range, explicit `Event` type, or event-looking route is not an independent admission path.

### 8.4 Targeted source behavior

Targeted behavior remains in backend collection and tests rather than frontend exceptions. Examples include deep-scroll/list expansion, source-specific public URL prefix rewrites, exact detail venue labels, and Gardens by the Bay date/venue repair after list admission.

A source default venue is a controlled fallback, not proof of the actual room or location.

### 8.5 Crawl budgets

`surface/jobs/local_event_search.py` sets defaults before importing the collector:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_EVENTS_MAX_SECONDS` | 520 | Total job budget |
| `LOCAL_EVENTS_SOURCE_CONCURRENCY` | 3 | Parallel source workers |
| `LOCAL_EVENTS_SOURCE_TIMEOUT_SECONDS` | 160 | Per-source budget |
| `LOCAL_EVENTS_MAX_LISTING_PAGES` | 2 | Listing pagination limit |
| `LOCAL_EVENTS_LOAD_MORE_ROUNDS` | 24 | Expansion attempts |
| `LOCAL_EVENTS_MAX_TOTAL_EVENTS` | 180 | Final collection cap |
| `LOCAL_EVENTS_NAV_TIMEOUT_MS` | 25000 | Navigation timeout |
| `LOCAL_EVENTS_DOM_TIMEOUT_MS` | 25000 | DOM timeout |
| `LOCAL_EVENTS_DETAIL_LIMIT` | 24 | Supplementary detail reads |
| `LOCAL_EVENTS_DETAIL_TIMEOUT_MS` | 16000 | Detail timeout |
| `LOCAL_EVENTS_NHB_DETAIL_LIMIT` | 18 | Legacy adapter detail limit |
| `LOCAL_EVENTS_NHB_DETAIL_TIMEOUT_MS` | 16000 | Legacy adapter detail timeout |
| `LOCAL_EVENTS_PAGE_SCREENSHOTS` | 0 | Optional page evidence |
| `LOCAL_EVENTS_CARD_SCREENSHOTS` | 0 | Optional card evidence |

### 8.6 Local Event Studio operator plane

Studio provides a local workflow for one configured listing at a time:

```text
capture rendered official list
-> inspect full-page screenshot with DOM overlay
-> confirm repeated activity cards
-> map title / when / where / URL / summary / image
-> define exclusions and optional detail mappings
-> save inert draft
-> test against stored DOM evidence
-> inspect accepted and rejected rows
-> publish the exact tested fingerprint
```

The screenshot is a visual aid. Published extraction authority consists of bounded CSS selectors, field attributes, exclusion selectors, and explicit fallback choices. Coordinates are not stored in rules.

### 8.7 Studio local storage

All Studio state is under the active runtime root:

```text
surface/.env/local_event_studio/
├── snapshots/<source-id>/<snapshot-id>/
│   ├── page.png
│   ├── page.html
│   ├── dom.json
│   └── metadata.json
├── rules/<source-id>/<listing-hash>/
│   ├── draft.json
│   ├── published.json
│   └── history/vNNNNNN.json
├── test-runs/<source-id>/<run-id>.json
└── crawl-runs/
```

Writes are atomic. Path components are derived from validated configured bindings. Asset reads are name-whitelisted and reject path traversal and symlink escape. Captures and rules are machine-local and must not be committed.

### 8.8 Draft, test, publication, and rollback

Drafts never affect production collection. Deterministic snapshot testing validates selector mechanics, mandatory fields, public official detail URLs, current/future dates, duplicates, accepted rows, rejected rows, and field evidence.

A semantic rule fingerprint excludes lifecycle timestamps and version metadata. Publication requires the latest applicable test to be publishable and to match the current draft fingerprint exactly.

Publication creates:

- the next monotonically increasing version;
- an immutable history file;
- an atomically replaced `published.json`;
- removal of the mutable draft.

Rollback republishes one historical rule as a new version and records `based_on_version`; history is never rewritten in place.

### 8.9 Production routing

Runtime order is:

```text
existing structured-first collector
  -> apply published Studio rules per configured source/listing
  -> synchronize Studio detail dates
  -> enforce Studio source health
  -> normalize the existing output contract
  -> aggregate completion by source
  -> apply existing partial-write protection
```

Activation is bounded:

```text
no published rule
  -> existing collector result remains

all configured listings for one source published
  -> that source becomes Studio-only

some listings published
  -> replace only legacy rows carrying matching listing evidence

Studio failure, fatal evaluation, or zero accepted rows
  -> mark that source incomplete
  -> keep unrelated sources intact
  -> mark the payload partial
```

Accepted Studio rows use the same final candidate policy as other verified rows and additionally carry rule version, listing URL, field evidence, and detail-page evidence.

### 8.10 Source completion and partial-result protection

Studio can produce one debug row per listing while `source_count` counts organisations. The writer therefore groups debug rows by source name/ID before calculating completed and incomplete source counts. One failed listing makes that source incomplete without double-counting its successful listings.

Previous-cache eligibility mirrors the output contract:

- `official-listing-authority-v1` rows are eligible;
- missing policy is eligible only for a previous payload in the current `structured-first` extractor family;
- a different non-empty policy is ineligible.

When a partial run has fewer rows than the eligible previous result, the writer keeps the previous primary file and writes the incomplete run to `local_event_search_results.partial.json` with `write_policy: kept_previous_verified_result`.

### 8.11 Evidence and semantic acceptance

Deterministic tests prove storage, selector evaluation, publication gating, HTTP behavior, production routing, and failure isolation for supplied inputs. They do not prove that a current external page contains the intended real-world activities.

The first live migration therefore requires a real Studio capture, human confirmation of activity cards and fields, a publishable test, an identified published version, a live producer run, runtime JSON inspection, visible-card inspection, and confirmation that unrelated sources remain intact.

### 8.12 Local Event UI contract

The kiosk displays one accepted result at a time with organisation, title, `WHEN`, `WHERE`, description, and an official-link action. Backend rows remain authoritative; the frontend may fit or ellipsize text but must not hide records with title-specific rules.

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

The Mac setup stores machine-specific configuration in uncommitted `mac/local.env`. The Calendar board loads the runtime file at page startup and rotates already-loaded groups. The Sync ticker independently observes Surface file age.

## 10. Photo pipeline

```text
user files in surface/.env/photos/
  -> surface/build_photos_json.py
  -> normalized files in surface/.env/public_photos/
  -> surface/.env/photos.json
  -> /photos.json and /public_photos/*
  -> browser photo wall
```

The browser does not enumerate local files. The builder preserves GIF animation, converts supported HEIC/HEIF input, and avoids exposing original filesystem paths.

## 11. Freshness observation

The Sync ticker is an observer, not a scheduler or producer.

| Stat | Endpoint | Dependency | Stale threshold |
| --- | --- | --- | --- |
| `SCHEDULE` | `/schedule.json` | Calendar | 600 seconds |
| `WEATHER` | `/weather.json` | Weather | 900 seconds |
| `MARKET` | `/market.json` | Market | 600 seconds |
| `NEWS` | `/event_stream.json` | News | 600 seconds |

The browser performs `HEAD` and calculates `AGE` from `Last-Modified`.

## 12. HTTP and runtime boundary

Ordinary GET requests serve committed frontend assets or current local runtime state. They do not synthesize external producer data.

- runtime GET returns the current local file or a missing-runtime payload;
- runtime HEAD returns size and `Last-Modified`;
- Market config POST writes the runtime symbol file;
- Market refresh POST invokes the live-data producer;
- Local Events search POST invokes the existing command wrapper;
- Studio mutations are restricted to configured source/listing bindings and machine-local state;
- Studio capture invokes one short-lived capture job;
- Studio test is offline against stored snapshot evidence;
- Studio publish activates only an exact tested draft.

Detailed methods, payloads, and status codes are defined in `docs/api-spec.md`.

## 13. Failure isolation

Failures remain separated by owner:

- HTTP failure affects every browser area even when runtime files are healthy;
- one producer failure affects only its outputs;
- one renderer failure affects only its owned mounts;
- Mac schedule failure affects Calendar but not Surface producers;
- one Local Events source failure is recorded under that source;
- one Studio listing failure makes its source incomplete without erasing unrelated sources;
- a smaller partial Local Events run does not replace a larger eligible previous result;
- Market provider failure is isolated per symbol through fallback.

Diagnosis follows visible area -> endpoint -> runtime file -> producer -> external source.

## 14. Simulated and static page content

CPU/MEM/DSK/NET bars are generated with `Math.random()` in the browser. POWER, DISPLAY, NETWORK, `AC_ONLY`, `ONLINE`, and `LAN_OK` are static labels. Page uptime measures the current browser session. These are not Surface OS monitoring.

## 15. Documentation boundaries

- `README.md`: onboarding, capabilities, interaction, deployment, operation, troubleshooting, and validation.
- `docs/design.md`: architecture, ownership, data flow, runtime storage, and source-specific behavior.
- `docs/api-spec.md`: HTTP methods, payloads, responses, side effects, and callers.
- `docs/questions.md`: requirement interpretations and acceptance evidence.
- `AGENT.md`, `AGENTS.md`: repository contribution rules and required read order.
