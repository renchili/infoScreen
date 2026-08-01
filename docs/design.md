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
| `surface/fetch_live_data.py` | Fetch Weather and Market and atomically replace their runtime files |
| `surface/fetch_event_stream.py` | Fetch RSS, prioritise Singapore sources, build aligned EN/FR/ZH rows, and atomically replace `event_stream.json` |
| `surface/search_local_events.py` | Supported Local Events command wrapper |
| `surface/jobs/local_event_search.py` | Configure crawl budgets, run collector, normalize output, protect verified results, persist the collector snapshot, and publish the kiosk projection |
| `surface/local_events_runtime/` | Canonical Local Events collection, extraction, review, diagnostics, projection, and persistence library |
| `surface/web/local-events/studio/` | Operator review, filtering, manual list-page entry, explicit collection, and diagnostics |
| `surface/build_photos_json.py` | Normalize/copy photos and atomically build a public-path-only manifest |
| `mac/export.py`, `mac/sync_schedule.sh` | Export EventKit, upload a temporary schedule file, and atomically publish it on the Surface |

Runtime state belongs under `surface/.env/`. It is device state or personal data and is not source code.

## 4. Refresh layers

Producer refresh, browser data reload, visual rotation, dashboard filtering, and review-state refresh are independent.

The kiosk Local Events card periodically performs `GET /api/local-events/search` to read the current runtime payload. Its institution and text controls filter that in-memory payload only. Applying a dashboard filter does not run Chromium, start a producer, or write runtime JSON. A later GET refresh re-applies the active browser filter to the new payload.

The Local Event Studio loads review state on initial load, explicit operations, manual `RELOAD`, and return to the browser tab. It does not register an idle polling interval. A completed render emits one lifecycle event, after which the scroll guard restores a stable candidate anchor or the previous scroll position.

Calendar visual rotation remains separate from data reload. The board rotates loaded rows every seven seconds and checks `schedule.json` every 60 seconds without reloading the whole page.

## 5. UI ownership

Each visible mount has one renderer owner. Producer jobs write authoritative runtime files. Browser scripts render those files and send explicit mutations. Asynchronous scripts must not overwrite another owner’s final DOM.

`surface/web/assets/js/dashboard.js` owns the clock, Market, Weather, and browser-generated CPU/MEM/DSK/NET demo meters. Those meters are not host telemetry. The POWER/DISPLAY/NETWORK values in `surface/web/index.html` are static kiosk labels.

`surface/web/assets/js/local_event_card.js` owns both rendering the kiosk Local Events card and filtering its already-loaded rows. Collection remains owned by the producer job and explicit collection API, not by the dashboard filter dialog.

The left dashboard column has three explicit rows for Market, Local Events, and the Sync ticker. The Local Event panel is not placed in the fixed ticker row.

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

The Surface observed `ERR_HTTP2_PROTOCOL_ERROR` while Chromium opened official Event sites. The supported formal collection entrypoints apply:

```text
surface/local_events_runtime/http1_browser.py
```

before importing collector code. Chromium launched by scoped discovery, confirmed-page formal collection, scheduled collection, and direct search starts with:

```text
--disable-http2
```

There is no HTTP/2-first attempt and no protocol retry loop on those paths.

Isolated Preview is a deliberate exception. `preview_direct_detail_collector_authority.py` owns one Playwright manager, one Chromium process, and one browser context for the selected listing plus all admitted detail pages. `preview_transport_authority.py` may run Marina Bay Sands Preview in headed mode and records NetLog diagnostics, but it does not force HTTP/1 or otherwise alter Chromium protocol negotiation.

### 6.4 Positive Event intent

Positive Event intent means membership in the correct official activity list. A title, date range, explicit `Event` type, or event-looking route is insufficient by itself. Structured XHR, embedded JSON, and detail-page JSON can improve an admitted item only after matching the rendered list card.

### 6.5 Detail-page authority

A correct listing card may omit date and venue. After admission, the collector follows only that card’s official detail URL. Detail failure does not erase the list evidence; review candidates remain visible with exact detail status/error.

## 7. Operator review state and kiosk projection

Operator review persistence is separate from the collector snapshot and kiosk output:

```text
surface/.env/local_event_review/state.json
surface/.env/local_event_review/preview_event_selections.json
```

`state.json` contains candidate list pages and decisions, Event candidates and decisions, collection metadata, per-listing recognition diagnostics, and previously submitted DOM positions. `preview_event_selections.json` contains the validated REAL EVENT / NOT EVENT decisions committed for each reviewed list page.

The exact candidate set returned by the latest successful Preview is a separate process-local manifest owned by `preview_event_selection_authority.py`. It is not written to either Review JSON file. The manifest records candidate identity, original listing link, final redirected/public URL, the List Page revision, and an expiry. Its default lifetime is 21,600 seconds and can be changed with `INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS`, with a minimum of 60 seconds. A service restart, expiry, newer Preview, List Page state change, reset, rejection, manual re-add, or discovery retirement invalidates the manifest and requires a fresh Preview before saving candidate decisions.

The persistence files are separate, but confirmed and rejected Event decisions are authoritative inputs to the kiosk projection. The homepage must not independently choose stale collector fields when the same canonical detail URL has a reviewed decision.

### 7.1 System-discovered flow

```text
discover candidate list pages
  -> retire no-longer-discovered non-manual pages and their committed Preview selections
  -> inspect candidate URL
  -> preview that saved page in any decision state
  -> classify every Preview candidate as REAL EVENT or NOT EVENT
  -> save the List Page decision and candidate selections together
  -> collect selected REAL EVENT rows from confirmed pages
  -> inspect persisted detail data and DOM evidence
  -> confirm/reject/reset persisted Event candidate
  -> rebuild local_event_search_results.json from collector snapshot + Review state
```

When scoped discovery removes a non-manual List Page, it removes that URL’s committed Preview selection before saving the new Review state. If the state write fails, the previous selection file is restored. After a successful state write, the process-local Preview manifest is invalidated. A later discovery of the same URL therefore starts without an eligible old selection and must be Previewed again.

Preview collection is decision-independent. `POST /api/local-events/review/preview-events` copies the current Review state to a temporary store, keeps only the selected list page, marks only that temporary copy confirmed, clears copied Event candidates and feedback, and runs the direct Preview collector/detail owner. The Preview request itself does not change the saved list-page decision, persisted Event candidates, feedback, collection metadata, `state.json`, or kiosk output.

One Preview request owns one real Chromium process and one browser context. The direct collector opens the selected listing page, extracts rendered candidate cards, then opens every admitted official detail page through the same context before closing the browser once. The returned metadata records `preview_browser_process_count: 1`, `preview_browser_reuse: listing_and_details`, `preview_detail_context_count: 1`, and `preview_detail_transport: same_browser_context`. If listing-only evidence still reaches the final HTTP handoff, the request fails instead of opening a second browser or issuing a manifest from incomplete detail results.

Preview is classification evidence, so its final handoff bypasses the executing expired-event filter only for the isolated Preview result. Expired official candidates remain visible for operator classification, and the response records `preview_expiry_policy: retain_for_operator_review`. The original expiry filter is restored before the request returns; formal persisted collection and kiosk publication keep the normal expiry policy.

The browser keeps the active Preview panel and uncommitted candidate choices in `sessionStorage`. The final Preview handoff first invalidates any older manifest, completes detail enrichment and redirect handling, then issues the exact candidate manifest returned to the browser. When the operator saves the List Page review, `POST /api/local-events/review/listing-decision` receives a `preview-review-v1:` payload containing every Preview candidate and its REAL EVENT / NOT EVENT decision. The backend validates the List Page identity, official-domain detail URLs, candidate identities, and exact equality with the latest unexpired server manifest. Browser drafts may remain visible after the manifest becomes invalid, but submission then fails with guidance to run Preview again. The backend atomically replaces `preview_event_selections.json`, then writes the List Page decision; if that state write fails, the prior selection file is restored and the still-valid manifest remains available for retry.

Normal collection remains separate. `POST /api/local-events/review/collect-events` reads confirmed pages that have committed REAL EVENT selections, filters unselected list cards before detail navigation, persists only the selected Event candidates and diagnostics, marks those candidates confirmed, and leaves list-page decisions unchanged. A confirmed page without a committed REAL EVENT selection is not silently collected as an unrestricted page.

Decision projection rules are:

```text
confirmed + matching collector URL
  -> keep one row
  -> Review title/date/venue/summary override non-empty matching fields
  -> collector order and evidence metadata remain

confirmed + no collector match
  -> append one Review-owned row

rejected + matching collector URL
  -> suppress that collector row from the kiosk projection

pending/reset
  -> leave or restore the collector row
```

The projection is deterministic and is rebuilt from the private collector snapshot on every Event decision and after each producer run. The public event row must not embed a second copy of the original collector row.

### 7.2 Manual correct-list-page flow

Some institutions do not expose a discoverable dedicated list URL, or the automated discovery result is wrong. The Studio therefore provides an explicit manual input tied to the global institution selection.

```text
select one global institution
  -> enter official Event list URL
  -> POST /api/local-events/review/listing-page
  -> validate configured institution
  -> validate hostname against that institution's allowed_domains
  -> save or reset the page as pending review state
  -> discard its previous committed Preview selection and process-local manifest
  -> display it immediately in the left-side list-page cards
  -> preview before deciding
  -> classify every candidate as REAL EVENT or NOT EVENT
  -> confirm the page with at least one REAL EVENT, or reject it with none
  -> include only committed REAL EVENT selections in normal collection
```

Manual addition does not edit committed `event_sources.json` and does not automatically collect Events. It creates a review candidate only. The operator may run the isolated preview while the page is pending, rejected, or confirmed. Preview itself does not mutate the real List Page decision; saving the reviewed candidate set and List Page decision is a separate explicit operation.

When the same institution/URL already exists, manual addition resets it to `pending`, discards any old Preview selection and manifest, and requires a new Preview before confirmation.

### 7.3 Zero-result diagnostics

Each attempted list page records stage counts for page access, visible links, allowed-domain links, possible detail links, extracted cards, admitted cards, DOM evidence, selectors, candidates, and detail result counts. The first failed stage produces a stable `reason_code`. The browser renders the backend diagnostic rather than guessing.

## 8. Interactive browser feedback status

The previously introduced downloadable Chrome Helper, generated ZIP, unpacked extension files, and remote `feedback:` transport were removed because they were not part of the requested product/deployment boundary.

The current branch does not expose a replacement interactive browser-feedback action. Ability 2 remains visibly marked `NOT IMPLEMENTED`; it must not pretend a browser opened or ask the operator to download/install generated artifacts.

Existing submitted positions remain readable from review state.

## 9. Local Events output protection

Producer-owned collector snapshot:

```text
surface/.env/local_event_collector_results.json
```

Kiosk primary projection:

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

Accepted collector rows carry `candidate_policy: official-listing-authority-v1`. Source completion states, not debug-row counts, determine whether a run is partial. A smaller partial run does not replace a larger verified collector snapshot. The kiosk primary is rebuilt from the retained or newly accepted collector snapshot plus current Review decisions, so scheduled collection cannot silently discard confirmed corrections.

On first startup after migration, the current primary is cleaned into a collector snapshot. Legacy Review-only rows are re-created from review state, and legacy rows containing `review_overlay_base` restore that embedded collector base once; new primary rows never contain `review_overlay_base`.

## 10. Calendar pipeline

```text
macOS Calendar/EventKit
  -> LaunchAgent
  -> mac/export.py
  -> mac/sync_schedule.sh
  -> SCP to a remote temporary file
  -> remote atomic rename
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

The public manifest contains browser URLs, captions, and output types only. It does not include original absolute paths. JPEG inputs can be copied without conversion. PNG and WebP require ImageMagick; they are skipped rather than copied into files with false `.jpg` extensions when no converter exists. HEIC and HEIF require `ffmpeg`.

## 12. Freshness observation

The Sync ticker is an observer, not a scheduler. It performs `HEAD` requests and calculates age from the browser clock and `Last-Modified`.

## 13. Failure isolation

- HTTP service failure affects every panel.
- One producer failure affects only its outputs.
- Weather retains previous values only with a visible `ERR`/retained-data presentation.
- One Local Event source failure is recorded under that source.
- A partial Local Event run does not replace a larger verified collector snapshot.
- A zero-result review page records the first failed recognition stage.
- A manually supplied list page outside the configured institution allow-list is rejected before persistence.
- A retired discovery page cannot retain a committed Preview selection; failed Review-state persistence restores the previous selection bytes.
- An expired, missing, superseded, or revision-mismatched Preview manifest rejects submission and tells the operator to run Preview again.
- Isolated Preview listing and detail reads share one Chromium process and one context; incomplete final detail results fail instead of opening a second process.
- Preview retains expired official candidates only for classification; formal collection and kiosk publication retain normal expiry filtering.
- Formal discovery and collection disable HTTP/2 before Chromium starts; isolated Preview keeps normal protocol negotiation and may use headed Chromium for Marina Bay Sands.
- A dashboard filter with no matches displays an empty filtered state without changing or deleting the underlying runtime events.
- A Review projection failure must leave the previous kiosk primary intact because both collector and display writes are atomic.
- Market, Weather, News, and photo manifest producers use temporary files and atomic replacement.

## 14. Documentation boundaries

- `README.md`: overview, operation, interaction, deployment, troubleshooting.
- `docs/design.md`: architecture, ownership, data flow, implementation boundaries.
- `docs/api-spec.md`: HTTP interaction contract and side effects.
- `docs/questions.md`: clarified requirements and acceptance evidence.
