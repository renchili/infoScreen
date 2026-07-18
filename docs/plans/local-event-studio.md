# Local Event Studio implementation plan

Status: temporary working record on `develop/surface-local-events-coverage`.

This file is not final product documentation. It must be deleted before delivery after its implemented content is merged into:

- architecture, storage, and runtime behavior -> `docs/design.md`;
- requirement clarifications and acceptance evidence -> `docs/questions.md`;
- HTTP routes and payloads -> `docs/api-spec.md`;
- deployment and operation -> `README.md`.

## Fixed constraints

- Work only on `develop/surface-local-events-coverage`.
- Do not modify `main`, create a PR, or merge without explicit approval.
- Use the existing `surface/serve_infoscreen.py` process and port `8765`.
- Do not add another HTTP server, port, daemon, systemd service, or duplicate application.
- Serve the operator UI at `/local-events/studio` through the existing HTTP service.
- Store local state under `surface/.env/local_event_studio/`; never commit runtime rules, captures, logs, or screenshots.
- Draft rules must not affect production collection.
- Published rules are enabled per configured source/listing pair.
- One source failure must not clear unrelated sources.
- Structured data may enrich an admitted rendered card but may not independently create an activity.
- Screenshot coordinates are UI aids only; published rules use DOM selectors and explicit field mappings.
- Complete one phase and its deterministic checks before entering the next phase.
- Do not claim live-source, Surface, browser, or semantic correctness without direct evidence for the exact commit.

## Product workflow

```text
choose configured source and listing
-> capture official listing page
-> inspect screenshot and DOM evidence
-> identify repeated activity cards
-> map title, when, where, public detail URL, summary, optional image
-> mark excluded elements
-> save draft
-> test draft against snapshot
-> inspect accepted/rejected rows and field evidence
-> publish version
-> run that source
-> inspect runtime output
-> roll back when required
```

The complete workflow must be usable locally on the Surface without sending screenshots elsewhere or editing JSON manually.

## Local storage model

```text
surface/.env/local_event_studio/
├── snapshots/<source-id>/<snapshot-id>/
│   ├── page.png
│   ├── page.html
│   ├── dom.json
│   └── metadata.json
├── rules/<source-id>/<listing-key>/
│   ├── draft.json
│   ├── published.json
│   └── history/
├── test-runs/
└── crawl-runs/
```

Writes must be atomic. Source IDs and listing URLs must be validated against `surface/conf/event_sources.json`. Filesystem names must be derived from validated identifiers and hashes, not request paths.

## Published rule contract

A published rule is versioned and bound to one configured source/listing pair.

```json
{
  "schema_version": 1,
  "source_id": "esplanade",
  "listing_url": "https://www.esplanade.com/whats-on",
  "version": 3,
  "status": "published",
  "card": {
    "selector": "main .event-card",
    "exclude_selectors": [".promotion-card"]
  },
  "fields": {
    "title": {"selector": "h2"},
    "when": {"selector": ".event-date"},
    "where": {"selector": ".event-venue", "allow_source_default": false},
    "url": {"selector": "a[href]", "attribute": "href"},
    "summary": {"selector": ".event-description", "optional": true}
  },
  "detail_page": {
    "enabled": true,
    "fields": {
      "when": {"selector": ".detail-date"},
      "where": {"selector": ".detail-venue", "allow_source_default": false}
    }
  },
  "validation": {
    "require_public_detail_url": true,
    "require_current_or_future_date": true
  }
}
```

## Admission and field authority

### Public detail URL

An accepted row must use the admitted card's public official detail URL or an explicitly configured source rewrite. It must belong to an allowed official domain, differ from the listing URL, and not be an image, document, JSON/API endpoint, internal CMS endpoint, fragment-only URL, or synthetic placeholder. The listing URL remains evidence rather than the output URL.

### When and where

Field precedence is fixed:

```text
mapped detail-page field
-> mapped list-card field
-> structured value matched to that admitted card
-> empty
```

The collector must not derive final `when` or `where` from arbitrary page-wide text. The source display name is not a venue fallback unless the published rule explicitly enables `allow_source_default`.

### Positive activity intent

A candidate is an activity only when it comes from the published card selector for the configured official listing and passes mandatory field and URL checks. XHR, embedded state, JSON-LD, navigation, facilities, membership, parking, dining, advertising, and promotions cannot independently create output rows.

## Phases

### Phase 0 — Temporary plan and baseline

Deliverables:

- temporary plan file;
- confirmed base `66a6567356ebf7b47817e40f896fc0cecaadb978`;
- no runtime behavior change.

### Phase 1 — Rule storage and version management

Implement only the local data layer:

- Pydantic rule schema;
- configured source/listing validation;
- safe path derivation;
- draft save/load/delete;
- publish with monotonic version;
- immutable history;
- rollback as a new published version;
- atomic writes;
- validated import/export;
- deterministic temporary-directory tests.

Do not expose HTTP routes or connect the module to production collection.

### Phase 2 — Existing `8765` API integration

Add the Studio routes to `surface/serve_infoscreen.py`, API models, OpenAPI, and contract tests. Production collection remains unchanged.

```text
GET    /local-events/studio
GET    /api/local-events/studio/sources
GET    /api/local-events/studio/rules
PUT    /api/local-events/studio/draft
DELETE /api/local-events/studio/draft
POST   /api/local-events/studio/publish
POST   /api/local-events/studio/rollback
POST   /api/local-events/studio/import
GET    /api/local-events/studio/export
```

### Phase 3 — Snapshot capture

Add a one-shot capture job invoked by the existing HTTP server. Save full-page screenshot, HTML, normalized DOM evidence, and metadata. Accept only configured source/listing pairs. Do not perform unrestricted crawling or page-wide network payload collection by default.

### Phase 4 — Local annotation UI

Add the Studio frontend under `surface/web/` and serve it through `8765`.

Required interactions:

- select source, listing, and snapshot;
- inspect screenshot and DOM outlines;
- click or box-select and resolve to DOM evidence;
- infer repeated card selector from multiple examples;
- map title, when, where, URL, summary, optional image;
- add exclusion selectors;
- edit selectors;
- save draft;
- provide loading, empty, error, success, retry, keyboard, and focus behavior.

Coordinates must not enter the published rule.

### Phase 5 — Draft test and evidence preview

Execute a draft against a stored snapshot without changing production runtime data. Show matched cards, accepted/rejected rows, rejection reasons, final fields, raw evidence, selectors, normalization, precedence, duplicates, invalid URLs, missing dates, and source-default venue warnings. Block publishing when mandatory validation fails.

### Phase 6 — Per-source production integration

```text
no published Studio rule -> existing collector for that source/listing
published Studio rule -> Studio selector collector for that source/listing
```

Structured records may enrich only matched cards. Detail reads use only validated admitted URLs. One Studio source failure must not affect other sources. Debug output must include rule version and evidence source.

### Phase 7 — Esplanade live migration and acceptance

Migrate Esplanade first. Required evidence includes a real snapshot, published rule version, preview, live collector output, correct public URLs, correct `when` and `where`, zero inspected non-activity rows, and unchanged behavior for sources without published rules.

Repository tests alone are not live-source acceptance.

### Phase 8 — Incremental source migration

Migrate one source at a time through capture, annotation, test, publish, live run, and visible verification. Do not apply guessed selectors or one global filter to every source.

### Phase 9 — Deployment and operation

Use only existing units:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

Document code update, existing-unit reinstall, HTTP restart, immediate crawl, Studio access, rule inspection, rollback, and per-source evidence inspection.

### Phase 10 — Documentation consolidation and plan deletion

Mandatory final cleanup:

- merge implemented architecture and storage into `docs/design.md`;
- merge clarified boundaries and acceptance evidence into `docs/questions.md`;
- merge actual route contracts into `docs/api-spec.md`;
- merge supported operation commands into `README.md`;
- remove stale contradictory claims;
- delete `docs/plans/local-event-studio.md`;
- remove every reference to this temporary plan;
- verify no second port, service, server, or temporary annotation implementation remains.

## Commit and evidence discipline

For every phase:

- use one focused commit or a small ordered set;
- modify only required files;
- add tests in the existing test layout;
- distinguish checks run from checks not run;
- review the final diff for unrelated files;
- commit no runtime data or generated evidence;
- make no claim stronger than the available evidence.

## Current phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| 0 — plan and baseline | complete | branch was identical to `66a6567`; temporary plan committed as `6fcc5e65` |
| 1 — rule storage | implemented; repository validation pending | `studio_rules.py` commit `af8f2ec3`; tests commit `4f506b8a`; exact-content isolated run: 8 passed |
| 2 — 8765 API | pending | none |
| 3 — snapshot capture | pending | none |
| 4 — annotation UI | pending | none |
| 5 — draft test | pending | none |
| 6 — production integration | pending | none |
| 7 — Esplanade acceptance | pending | none |
| 8 — source migration | pending | none |
| 9 — operations | pending | none |
| 10 — consolidation and plan deletion | pending | none |
