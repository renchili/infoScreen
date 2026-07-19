# InfoScreen HTTP interaction contract

This document defines the HTTP boundary between the kiosk frontend, Local Event Studio, local operator tools, runtime JSON, and producer jobs. Deployment and troubleshooting commands belong in `README.md`; architecture belongs in `docs/design.md`.

## 1. Server boundary

The HTTP owner is:

```text
surface/serve_infoscreen.py
```

The process binds `0.0.0.0:8765`. Local kiosk access normally uses `http://127.0.0.1:8765/`. The server has no authentication layer and is intended for a trusted local device/network; exposure beyond that boundary must be controlled outside the application.

Runtime files are read from:

```text
${INFOSCREEN_ENV_DIR:-surface/.env}
```

All responses add:

```text
Cache-Control: no-store
```

## 2. Static pages and generated API documentation

| Method | Path | Owner | Response |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/` | `serve_infoscreen.py` | `surface/web/index.html` |
| `GET`, `HEAD` | `/index.html` | `serve_infoscreen.py` | `surface/web/index.html` |
| `GET`, `HEAD` | `/local-events/studio/` | `SimpleHTTPRequestHandler` | `surface/web/local-events/studio/index.html` |
| `GET`, `HEAD` | `/docs` | `serve_infoscreen.py` | Swagger UI wrapper |
| `GET`, `HEAD` | `/openapi.json` | `serve_infoscreen.py`, `openapi_spec.py`, `api_models.py` | Generated OpenAPI JSON |

Static frontend assets are served from `surface/web/` through the existing `SimpleHTTPRequestHandler`. Local Event Studio does not introduce another HTTP process or port.

## 3. Runtime JSON reads

| Method | Path | Runtime file | Primary caller | Producer |
| --- | --- | --- | --- | --- |
| `GET`, `HEAD` | `/schedule.json` | `schedule.json` | `calendar_board.js`, Sync ticker | Mac EventKit export and SCP push |
| `GET`, `HEAD` | `/weather.json` | `weather.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market.json` | `market.json` | `dashboard.js`, Sync ticker | `fetch_live_data.py` |
| `GET`, `HEAD` | `/market_config.json` | `market_config.json` | Direct operator/debug read | Market config API |
| `GET`, `HEAD` | `/event_stream.json` | `event_stream.json` | `local_event_card.js`, Sync ticker | `fetch_event_stream.py` |
| `GET`, `HEAD` | `/local_event_search_results.json` | `local_event_search_results.json` | Direct operator/debug read | Local-event job |
| `GET`, `HEAD` | `/photos.json` | `photos.json` | `local_event_card.js` | Photo builder |
| `GET`, `HEAD` | `/sync_status.json` | `sync_status.json` | Reserved/direct read | No active producer documented |

### Missing runtime behaviour

For `GET`, when the runtime file does not exist, the server returns the endpoint’s default JSON shape plus:

```json
{
  "ok": false,
  "error": "missing_runtime_json",
  "expected_path": "/absolute/path/to/the/runtime/file"
}
```

For `HEAD`, a missing runtime file returns HTTP `404`.

### HEAD freshness contract

For an existing runtime file, `HEAD` returns:

```text
Content-Type: application/json; charset=utf-8
Content-Length: <file size>
Last-Modified: <file mtime as HTTP date>
```

The Sync ticker uses `Last-Modified`; it does not parse JSON `updated_at` fields.

## 4. Public photo reads

| Method | Path | Filesystem mapping | Caller |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/public_photos/<relative-path>` | `surface/.env/public_photos/<relative-path>` | Photo wall |

The photo builder controls which files are copied into the public runtime directory. The browser does not receive arbitrary filesystem access.

## 5. Market configuration interaction

### Read active symbols

```http
GET /api/market-config
```

Caller:

```text
surface/web/assets/js/market_custom.js
```

Resolution order:

1. `surface/.env/market_config.json` when present;
2. `surface/conf/market_config.default.json`;
3. built-in default symbols.

Example response:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

### Save active symbols

```http
POST /api/market-config
Content-Type: application/json
```

Canonical request body:

```json
{
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"]
}
```

Server behaviour:

- input must be a JSON list;
- values are trimmed and uppercased;
- duplicates are removed while preserving order;
- at most 12 symbols are stored;
- an empty final list is rejected;
- success writes `surface/.env/market_config.json` with `updated_at`.

Success response:

```json
{
  "ok": true,
  "symbols": ["AAPL", "NVDA", "MSFT", "TSLA"],
  "updated_at": "<UTC ISO timestamp>"
}
```

Invalid input returns HTTP `400` with:

```json
{
  "ok": false,
  "error": "<validation message>"
}
```

Saving configuration does not by itself render quotes. `market_custom.js` follows a successful save by calling the Market refresh endpoint and then `window.loadMarket()`.

## 6. Market and Weather manual refresh

```http
POST /api/market-refresh
```

Request body: none.

Caller:

```text
market_custom.js REFRESH action
market_custom.js SAVE action after config is written
```

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/fetch_live_data.py
  -> surface/.env/weather.json
  -> surface/.env/market.json
```

The subprocess timeout is 60 seconds.

Success/failure response includes:

```json
{
  "ok": true,
  "returncode": 0,
  "stdout": "<last output>",
  "stderr": "<last error output>",
  "market": {},
  "weather": {}
}
```

HTTP status is `200` when the subprocess exits successfully and `500` otherwise. Because Weather and Market share one producer, a manual Market refresh refreshes both runtime files.

## 7. Local Events read interaction

```http
GET /api/local-events/search
```

This endpoint does not run a crawl. It returns the current normalized `local_event_search_results.json` payload.

Primary caller:

```text
local_event_card.js on page load
```

The server normalizes text fields before returning the payload so API and page consumers receive the same plain-text representation.

## 8. Local Events search interaction

```http
POST /api/local-events/search
Content-Type: application/json
```

Canonical request body:

```json
{
  "location": "Punggol Singapore"
}
```

Primary caller:

```text
local_event_card.js location-search modal
```

The current server reads `location`; absent or empty input defaults to `Punggol Singapore`.

Side effect:

```text
serve_infoscreen.py
  -> subprocess: python surface/search_local_events.py <location>
  -> surface/jobs/local_event_search.py
  -> existing source-specific official collector
  -> published Studio source/listing replacement
  -> surface/.env/local_event_search_results.json
  -> optional surface/.env/local_event_search_results.partial.json
  -> debug evidence under surface/.env/local_event_debug_cards/
```

The HTTP subprocess timeout is 330 seconds. The job itself has a larger default total budget; therefore the HTTP on-demand path may terminate earlier than a direct systemd/manual producer run when sources are slow.

The response is the normalized runtime payload plus:

```json
{
  "ok": true,
  "stdout": "<last producer output>",
  "stderr": "<last producer error output>"
}
```

HTTP status is `200` for a successful subprocess and `500` otherwise.

Important response fields include:

```text
results
sources
debug_by_source
studio_activations
studio_source_count
partial
write_policy
previous_count
extractor
version
text_normalizer
```

The frontend displays only accepted `results`. `debug_by_source` and `studio_activations` are operator/developer evidence and are not rendered as event cards.

## 9. Local Event Studio source and rule reads

### List configured sources and rule state

```http
GET /api/local-events/studio/sources
```

Response shape:

```json
{
  "ok": true,
  "sources": [
    {
      "source_id": "esplanade",
      "name": "Esplanade",
      "listing_urls": [
        {
          "listing_url": "https://www.esplanade.com/whats-on",
          "has_draft": false,
          "published_version": null,
          "history_versions": []
        }
      ]
    }
  ]
}
```

The endpoint reads committed `surface/conf/event_sources.json` and machine-local Studio rule state. It does not crawl external pages.

### Read one listing’s rule state

```http
GET /api/local-events/studio/rules?source_id=<id>&listing_url=<url>
```

Response includes `draft`, `published`, and ascending immutable `history`. The source/listing pair must exist in committed configuration.

### Export one rule

```http
GET /api/local-events/studio/export?source_id=<id>&listing_url=<url>&status=published
GET /api/local-events/studio/export?source_id=<id>&listing_url=<url>&status=draft
GET /api/local-events/studio/export?source_id=<id>&listing_url=<url>&version=<n>
```

The response wraps a validated rule object. Export does not expose arbitrary filesystem paths.

## 10. Local Event Studio draft mutations

### Save draft

```http
PUT /api/local-events/studio/draft
Content-Type: application/json
```

The request body is the complete `LocalEventStudioRule` object. The server:

- validates source and listing against committed configuration;
- forces lifecycle state to `draft`, version `0`;
- preserves the original `created_at` when replacing an existing draft;
- writes atomically under `surface/.env/local_event_studio/rules/`;
- does not alter production collection.

### Delete draft

```http
DELETE /api/local-events/studio/draft
Content-Type: application/json
```

Request:

```json
{
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on"
}
```

Only the mutable draft is deleted. Published and historical versions remain.

### Import draft

```http
POST /api/local-events/studio/import
Content-Type: application/json
```

Request:

```json
{
  "rule": {}
}
```

The imported object is validated and saved as a new mutable draft. Imported publication metadata and history are not activated.

## 11. Local Event Studio snapshot capture and reads

### Capture configured listing

```http
POST /api/local-events/studio/capture
Content-Type: application/json
```

Request:

```json
{
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on"
}
```

Side effect:

```text
serve_infoscreen.py
  -> one-shot surface/jobs/local_event_studio_capture.py
  -> validate configured source/listing before browser launch
  -> Playwright render and bounded list expansion
  -> surface/.env/local_event_studio/snapshots/<source>/<snapshot>/page.png
  -> page.html
  -> dom.json
  -> metadata.json
```

The one-shot job inherits the active `INFOSCREEN_ENV_DIR`. It records rendered DOM evidence but does not collect page-wide XHR response bodies.

### List snapshots

```http
GET /api/local-events/studio/snapshots?source_id=<id>&listing_url=<url>
```

Both filters are optional. Results contain validated metadata only.

### Read snapshot asset

```http
GET /api/local-events/studio/snapshot-asset?source_id=<id>&snapshot_id=<id>&asset=page.png
HEAD /api/local-events/studio/snapshot-asset?source_id=<id>&snapshot_id=<id>&asset=page.png
```

Allowed asset names are:

```text
page.png
page.html
dom.json
metadata.json
```

Path traversal, unlisted asset names, and symlink escape are rejected.

## 12. Local Event Studio deterministic draft test

### Run test

```http
POST /api/local-events/studio/test
Content-Type: application/json
```

Request:

```json
{
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on",
  "snapshot_id": "<stored snapshot id>"
}
```

The test runs without external network access. It evaluates the current draft against stored `dom.json`, then atomically stores a test run under:

```text
surface/.env/local_event_studio/test-runs/<source-id>/
```

The result includes:

```text
rule_fingerprint
matched_card_count
accepted_count
rejected_count
publishable
fatal_errors
warnings
accepted[].event
accepted[].evidence
rejected[].reason
rejected[].reasons
rejected[].evidence
```

`publishable` requires no fatal rule error and at least one accepted activity. The test does not activate the draft.

### Read latest test

```http
GET /api/local-events/studio/test-latest?source_id=<id>&listing_url=<url>
```

The response contains the latest matching test result when available, otherwise `result: null`. Frontend presentation treats a loaded historical result as stale until the current draft is retested.

## 13. Local Event Studio publish and rollback

### Publish tested draft

```http
POST /api/local-events/studio/publish
Content-Type: application/json
```

Request:

```json
{
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on"
}
```

The server rejects publication unless:

- a current draft exists;
- a completed snapshot test exists for the same source/listing;
- the test’s semantic rule fingerprint exactly matches the current draft;
- the test result is `publishable: true`.

Successful publication:

- assigns the next monotonically increasing version;
- writes an immutable history file;
- atomically replaces `published.json`;
- removes the mutable draft;
- activates only that configured source/listing on subsequent Local Events jobs.

A draft-test mismatch returns HTTP `422` with `error: studio_test_required`.

### Roll back as a new version

```http
POST /api/local-events/studio/rollback
Content-Type: application/json
```

Request:

```json
{
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on",
  "version": 1
}
```

Rollback does not overwrite history. The selected historical rule is republished as a new active version with `based_on_version` pointing to the source version.

## 14. Production activation contract

Drafts and test runs never affect production output. `surface/jobs/local_event_search.py` applies Studio after the existing collector and before final normalization/write protection.

Activation rules:

```text
no published rule
  -> existing collector output remains

all configured listings for one source published
  -> legacy rows/debug for that source are replaced by Studio output

only some listings published
  -> only legacy rows carrying matching listing evidence are replaced

Studio source failure, fatal evaluation, or zero accepted result
  -> that Studio source is incomplete
  -> payload is partial
  -> unrelated sources remain
```

Accepted Studio rows carry:

```text
candidate_policy: official-listing-authority-v1
source_type: studio_published_rule
studio_rule_version
studio_listing_url
studio_evidence
studio_detail_page
```

The existing partial-write protection remains the final writer policy.

## 15. Browser interaction summary

| UI action | HTTP interaction | Server side effect | Final browser action |
| --- | --- | --- | --- |
| Open kiosk page | `GET /`, then runtime GETs | None | Render current runtime state |
| Market gear opens | `GET /api/market-config` | None | Populate symbol input |
| Market `SAVE` | `POST /api/market-config`, then `POST /api/market-refresh` | Write config; run live-data producer | Call `window.loadMarket()` |
| Market `REFRESH` | `POST /api/market-refresh` | Run live-data producer | Call `window.loadMarket()` |
| Local Event page load | `GET /api/local-events/search` | None | Render current accepted results |
| Local Event location search | `POST /api/local-events/search` | Run collector and published Studio routing | Store location and render returned results |
| Open Studio | `GET /local-events/studio/` | None | Load local source/rule/snapshot state |
| Studio `CAPTURE NOW` | `POST /api/local-events/studio/capture` | Run one-shot capture and store snapshot | Load screenshot and DOM overlay |
| Studio `SAVE DRAFT` | `PUT /api/local-events/studio/draft` | Atomically replace draft | Mark draft state |
| Studio `TEST DRAFT` | draft `PUT`, then test `POST` | Store deterministic test evidence | Render accepted/rejected preview |
| Studio `PUBLISH TESTED DRAFT` | draft `PUT`, test `POST`, publish `POST` | Publish only exact tested fingerprint | Show active version |
| Studio rollback | `POST /api/local-events/studio/rollback` | Republish history as new version | Reload versions |
| Sync observation | `HEAD` four runtime paths | None | Compute `AGE` and status |
| News reload | `GET /event_stream.json` | None | Rebuild three ticker rows |
| Photo reload | `GET /photos.json`, then image GETs | None | Rebuild and rotate photo wall |
| Calendar load | `GET /schedule.json` | None | Build and rotate Calendar board |

## 16. Endpoints that are intentionally not mutation APIs

There is no HTTP endpoint to:

- edit Calendar accounts or schedule events;
- add arbitrary Local Events source domains or listing URLs;
- change systemd timer frequency;
- upload or delete private photos;
- edit News feed configuration;
- change Weather coordinates.

Local Event Studio may create rules only for source/listing pairs already committed in `surface/conf/event_sources.json`. This keeps the local API bounded and prevents the kiosk process from becoming an unrestricted crawler or filesystem administration interface.
