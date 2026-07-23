# InfoScreen system architecture

This document explains system boundaries, data ownership, refresh behavior, Local Event collection, operator review, and the current interaction limits. Deployment and recovery commands belong in `README.md`.

## 1. Product shape

InfoScreen is an always-on, local-first information screen. Its design priorities are readable distance viewing, compact information density, stable layout, predictable long-running behavior, local ownership of personal data, and visible freshness/failure state.

The frontend is plain HTML, CSS, and JavaScript. The backend is a Python standard-library HTTP server plus short-lived producer jobs. Runtime persistence is local JSON rather than a database.

## 2. Deployment topology

```text
Mac
  macOS Calendar/EventKit
  -> schedule.json over SSH/SCP

Surface or Ubuntu device
  systemd --user services and timers
  -> producer jobs
  -> surface/.env/*.json
  -> surface/serve_infoscreen.py on 0.0.0.0:8765
  -> kiosk page
  -> Local Event Studio on the Surface or another trusted LAN device
```

The Surface is the runtime host for HTTP, Market, Weather, News, Local Events, Photos, review state, and the kiosk page. The Mac is authoritative for Calendar.

## 3. Runtime component boundaries

| Component | Responsibility |
| --- | --- |
| `surface/serve_infoscreen.py` | Serve frontend, runtime JSON, photos, OpenAPI, and local mutation/refresh endpoints |
| `surface/fetch_live_data.py` | Fetch Weather and Market and write runtime files |
| `surface/fetch_event_stream.py` | Fetch RSS, build aligned EN/FR/ZH rows, write `event_stream.json` |
| `surface/search_local_events.py` | Supported Local Events command wrapper |
| `surface/jobs/local_event_search.py` | Configure crawl budgets, run collector, normalize output, protect verified results |
| `surface/local_events_runtime/` | Canonical Local Events collection, extraction, review, diagnostics, and persistence library |
| `surface/web/local-events/studio/` | Operator review, filtering, manual list-page entry, explicit collection, and diagnostics |
| `surface/build_photos_json.py` | Normalize/copy photos and build manifest |
| `mac/export.py`, `mac/sync_schedule.sh` | Export EventKit and push `schedule.json` |

Runtime state belongs under `surface/.env/`. It is device state or personal data and is not source code.

## 4. Refresh layers

Producer refresh, browser data reload, visual rotation, dashboard filtering, and review-state refresh are independent.

The kiosk Local Events card periodically performs `GET /api/local-events/search` to read the current runtime payload. Its institution and text controls filter that in-memory payload only. Applying a dashboard filter does not run Chromium, start a producer, or write runtime JSON. A later GET refresh re-applies the active browser filter to the new payload.

The Local Event Studio reloads review state on initial load, explicit operations, manual `RELOAD`, and tab return. It does not continuously clear and rebuild all cards every three seconds.

## 5. UI ownership

Each visible mount has one renderer owner. Producer jobs write authoritative runtime files. Browser scripts render those files and send explicit mutations. Asynchronous scripts must not overwrite another owner’s final DOM.

`surface/web/assets/js/local_event_card.js` owns both rendering the kiosk Local Events card and filtering its already-loaded rows. Collection remains owned by the producer job and explicit collection API, not by the dashboard filter dialog.

## 6. Source-specific Local Events architecture

### 6.1 Source inventory

The authoritative institution inventory is:

```text
surface/conf/event_sources.json
```

It defines source ID, display name, official home, allowed domains, configured list URLs, default venue, adapter, and order.

### 6.2 Collection pipeline

```text
source configuration or confirmed review-state list page
  -> launch Chromium with --disable-http2
  -> open official list URL
  -> deep-scroll and operate expansion/pagination controls
  -> identify rendered card boundaries
  -> require a usable title and one canonical official detail URL
  -> do not require a date on the list card
  -> mark the card with listing evidence
  -> optionally match XHR/embedded structured data to the admitted card
  -> discard unmatched structured records
  -> open the admitted official detail page
  -> extract/normalize title, date/time, venue, summary, public URL
  -> record admission, rejection, detail, and failure evidence
```

The official list proves activity membership. The detail page is authoritative for fields the list omits, especially date/time and specific venue.

### 6.3 HTTP protocol policy

The Surface observed `ERR_HTTP2_PROTOCOL_ERROR` while Chromium opened official Event sites. The supported collection entrypoints apply:

```text
surface/local_events_runtime/http1_browser.py
```

before importing collector code. The patched Chromium launch always includes:

```text
--disable-http2
```

There is no initial HTTP/2 navigation and no retry that switches browser instances or protocols. This applies to:

- Local Event Studio discovery and Event collection through `surface/serve_infoscreen.py`;
- scheduled and HTTP-triggered Local Events through `surface/search_local_events.py`.

### 6.4 Positive Event intent

Positive Event intent means membership in the correct official activity list. A title, date range, explicit `Event` type, or event-looking route is insufficient by itself. Structured XHR, embedded JSON, and detail-page JSON can improve an admitted item only after matching the rendered list card.

### 6.5 Detail-page authority

A correct listing card may omit date and venue. After admission, the collector follows only that card’s official detail URL. Detail failure does not erase the list evidence; review candidates remain visible with exact detail status/error.

## 7. Operator review state

Operator review is separate from kiosk output:

```text
surface/.env/local_event_review/state.json
```

It contains candidate list pages and decisions, Event candidates and decisions, collection metadata, per-listing recognition diagnostics, and previously submitted DOM positions.

### 7.1 System-discovered flow

```text
discover candidate list pages
  -> preview Events for a page
  -> confirm/reject/reset list page
  -> collect from confirmed pages
  -> inspect detail data and DOM evidence
  -> confirm/reject/reset Event candidate
```

### 7.2 Manual correct-list-page flow

Some institutions do not expose a discoverable dedicated list URL, or the automated discovery result is wrong. The Studio therefore provides an explicit manual input tied to the global institution selection.

```text
select one global institution
  -> enter official Event list URL
  -> POST /api/local-events/review/listing-page
  -> validate configured institution
  -> validate hostname against that institution's allowed_domains
  -> save or reset the page as pending review state
  -> display it immediately in the left-side list-page cards
  -> preview
  -> confirm/reject/reset
```

Manual addition does not edit committed `event_sources.json` and does not automatically collect Events. It creates a review candidate only. The user must preview and confirm it before normal confirmed-page collection.

When the same institution/URL already exists, manual addition resets it to `pending`, allowing the operator to reconsider a previously rejected or stale decision.

### 7.3 Zero-result diagnostics

Each attempted list page records stage counts for page access, visible links, allowed-domain links, possible detail links, extracted cards, admitted cards, DOM evidence, selectors, candidates, and detail result counts. The first failed stage produces a stable `reason_code`. The browser renders the backend diagnostic rather than guessing.

## 8. Interactive browser feedback status

The previously introduced downloadable Chrome Helper, generated ZIP, unpacked extension files, and remote `feedback:` transport were removed because they were not part of the requested product/deployment boundary.

The current branch does not expose a replacement interactive browser-feedback action. Ability 2 remains visibly marked `NOT IMPLEMENTED`; it must not pretend a browser opened or ask the operator to download/install generated artifacts.

Existing submitted positions remain readable from review state.

## 9. Local Events output protection

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

Accepted rows carry `candidate_policy: official-listing-authority-v1`. A smaller partial run does not replace a larger verified result.

## 10. Calendar pipeline

```text
macOS Calendar/EventKit
  -> LaunchAgent
  -> mac/export.py
  -> mac/sync_schedule.sh
  -> SSH/SCP
  -> surface/.env/schedule.json
  -> /schedule.json
  -> calendar_board.js
```

## 11. Photo pipeline

```text
surface/.env/photos/
  -> surface/build_photos_json.py
  -> surface/.env/public_photos/
  -> surface/.env/photos.json
  -> browser photo wall
```

## 12. Freshness observation

The Sync ticker is an observer, not a scheduler. It performs `HEAD` requests and calculates age from the browser clock and `Last-Modified`.

## 13. Failure isolation

- HTTP service failure affects every panel.
- One producer failure affects only its outputs.
- One Local Event source failure is recorded under that source.
- A partial Local Event run does not replace a larger verified result.
- A zero-result review page records the first failed recognition stage.
- A manually supplied list page outside the configured institution allow-list is rejected before persistence.
- HTTP/2 is disabled before Chromium collection begins, so `ERR_HTTP2_PROTOCOL_ERROR` is not handled by a second retry flow.
- A dashboard filter with no matches displays an empty filtered state without changing or deleting the underlying runtime events.

## 14. Documentation boundaries

- `README.md`: overview, operation, interaction, deployment, troubleshooting.
- `docs/design.md`: architecture, ownership, data flow, implementation boundaries.
- `docs/api-spec.md`: HTTP interaction contract and side effects.
- `docs/questions.md`: clarified requirements and acceptance evidence.
