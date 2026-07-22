# InfoScreen system architecture

This document explains system boundaries, data ownership, refresh behaviour, Local Event collection, operator review, and current interaction limits. Deployment and recovery commands belong in `README.md`.

## 1. Product shape

InfoScreen is an always-on, local-first information screen. Its priorities are readable distance viewing, compact information density, stable layout, predictable long-running behaviour, local ownership of personal data, and visible freshness or failure state.

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
| `surface/serve_infoscreen.py` | Serve frontend, runtime JSON, photos, OpenAPI, and local mutation or refresh endpoints |
| `surface/fetch_live_data.py` | Fetch Weather and Market and write runtime files |
| `surface/fetch_event_stream.py` | Fetch RSS, build aligned EN/FR/ZH rows, and write `event_stream.json` |
| `surface/search_local_events.py` | Supported Local Events compatibility command |
| `surface/jobs/local_event_search.py` | Run the complete official-source collector, normalize new producer rows, protect partial output, overlay Review decisions, and write runtime JSON |
| `surface/local_events_runtime/` | Canonical collection, extraction, browser, source authority, review, diagnostics, and persistence library |
| `surface/web/local-events/studio/` | Operator review, filtering, manual list-page entry, explicit collection, and diagnostics |
| `surface/build_photos_json.py` | Normalize or copy photos and build the photo manifest |
| `mac/export.py`, `mac/sync_schedule.sh` | Export EventKit and push `schedule.json` |

Runtime state belongs under `surface/.env/`. It is device state or personal data and is not source code.

## 4. Refresh layers

Producer refresh, browser data reload, visual rotation, and review-state refresh are independent.

The Local Event Studio reloads review state on initial load, explicit operations, manual `RELOAD`, and tab return. It does not continuously clear and rebuild all cards.

The kiosk Local Events card reads the current primary runtime and periodically reloads it without redrawing unchanged content.

## 5. UI ownership

Each visible mount has one renderer owner. Producer jobs write runtime files. Browser scripts render those files and send explicit mutations. Asynchronous scripts must not overwrite another owner’s final DOM.

## 6. Local Events source inventory

The authoritative institution inventory is:

```text
surface/conf/event_sources.json
```

It defines source ID, display name, official home, allowed domains, configured list URLs, default venue, adapter, and source order.

## 7. Complete Local Events collection

### 7.1 Pipeline

```text
configured official source and list URLs
  -> apply complete collection coverage floors
  -> launch Chromium with --disable-http2
  -> open every configured official list URL
  -> deep-scroll and operate expansion or pagination controls
  -> identify rendered card boundaries
  -> admit official activity cards
  -> preserve official listing evidence
  -> enrich from matched structured data only
  -> open an official detail page when the card has one
  -> retain complete listing-only cards when no detail page exists
  -> normalize new producer rows
  -> record per-source and per-listing evidence
```

The official list proves activity membership. A detail page is authoritative for fields omitted by the list, but absence or failure of a detail page does not erase valid list membership.

### 7.2 Coverage authority

Local Events modules read many limits at import time. The HTTP server and compatibility command can import those modules before the job module, so job-level environment defaults alone are not authoritative.

`surface/local_events_runtime/complete_collection_authority.py` updates the live runtime globals used by the collector. The coverage floors allow all configured sources to receive execution time across all concurrency batches and align list-card and detail limits with the supported Event budget.

Runtime configuration may raise these values. It must not silently lower supported source coverage.

### 7.3 HTTP protocol policy

The supported browser bootstrap is:

```text
surface/local_events_runtime/http1_browser.py
```

It applies complete collection authority and source-specific parser authorities, and every patched Chromium launch includes:

```text
--disable-http2
```

There is no HTTP/2-first navigation or protocol retry loop.

### 7.4 Positive Event intent

Positive Event intent means membership in the correct official activity list. A title, date range, explicit Event type, or Event-looking route is insufficient by itself. Structured XHR, embedded JSON, and detail-page JSON can enrich an admitted list card only after matching it.

### 7.5 Cards without detail pages

Some official activity lists contain all required fields directly and provide no independent detail page. These listing-only cards remain separate Events even when several cards share one official list URL. Card identity and semantic identity prevent URL-only deduplication from collapsing them.

## 8. Operator review state

Review state is stored separately at:

```text
surface/.env/local_event_review/state.json
```

It contains candidate list pages and decisions, Event candidates and decisions, collection metadata, recognition diagnostics, and submitted DOM positions.

### 8.1 Review flow

```text
discover or manually add candidate list page
  -> preview Events
  -> confirm, reject, or reset list page
  -> collect from confirmed pages
  -> inspect listing evidence and detail status
  -> mark Event as RELATED ACTIVITY, NOT RELATED, or RESET
```

### 8.2 Review publication

Review state is separate storage, but confirmed decisions contribute to the kiosk output.

```text
current producer rows
  + current Review Events with decision=confirmed
  -> local_event_search_results.json
```

`review_publish_authority.py` applies the same overlay in two places:

- immediately after an Event decision;
- after the producer has normalized and protected a new collector payload.

Review publication removes and rebuilds only rows carrying `review_publish_origin: review_state`. It copies unrelated producer rows unchanged. A confirmed Event is not subjected to a second crawler-admission pass; unavailable fields can remain blank, and listing-only Events use their official list URL.

A producer Event and confirmed Event are not duplicated when they identify the same detail URL or semantic listing card.

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

New producer rows are normalized before publication. Previously verified rows retained during partial protection are copied without another normalization or admission pass. This prevents a later incomplete run or unrelated Review decision from deleting correct rows.

The final primary runtime contains protected producer rows plus the current confirmed Review overlay.

## 10. Service duration boundary

The complete collection budget is longer than the previous default HTTP and systemd oneshot limits. Deployment units therefore allow the full producer duration:

- `infoscreen-local-events.service` has a start timeout longer than the complete collection budget;
- `infoscreen-http.service` gives `POST /api/local-events/search` a matching subprocess timeout.

The timer remains a producer trigger; it is not a diagnostics-only task.

## 11. Calendar pipeline

```text
macOS Calendar/EventKit
  -> LaunchAgent
  -> mac/export.py
  -> mac/sync_schedule.sh
  -> SSH/SCP
  -> surface/.env/schedule.json
  -> browser
```

## 12. Photo pipeline

```text
surface/.env/photos/
  -> surface/build_photos_json.py
  -> surface/.env/public_photos/
  -> surface/.env/photos.json
  -> browser photo wall
```

## 13. Freshness observation

The Sync ticker is an observer, not a scheduler. It performs `HEAD` requests and calculates age from the browser clock and `Last-Modified`.

## 14. Failure isolation

- HTTP service failure affects every panel.
- One producer failure affects only its outputs.
- One Local Event source failure is recorded under that source.
- Queue waiting must not classify a configured source as skipped before it starts.
- A partial Local Event run cannot delete protected producer rows or current confirmed Review rows.
- A zero-result review page records the first failed recognition stage.
- A manually supplied list page outside the configured institution allow-list is rejected before persistence.
- HTTP/2 is disabled before Chromium collection begins.

## 15. Documentation boundaries

- `README.md`: overview, operation, interaction, deployment, and troubleshooting.
- `docs/design.md`: architecture, ownership, data flow, and implementation boundaries.
- `docs/api-spec.md`: HTTP interaction contract and side effects.
- `docs/questions.md`: clarified requirements and acceptance evidence.
