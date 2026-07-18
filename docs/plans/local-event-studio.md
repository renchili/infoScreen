# Local Event Studio implementation plan

Status: temporary working plan on `develop/surface-local-events-coverage`.

This file exists only to coordinate the staged implementation. It is not part of the final product documentation and must be deleted before delivery. Final project-relevant content must be merged into the established documentation homes:

- architecture, storage, data flow, and runtime boundaries -> `docs/design.md`;
- requirement clarifications and acceptance conditions -> `docs/questions.md`;
- HTTP routes, payloads, errors, and side effects -> `docs/api-spec.md`;
- deployment, operation, and troubleshooting commands -> `README.md`.

## Fixed constraints

- Work only on `develop/surface-local-events-coverage`.
- Do not modify `main`.
- Do not create a pull request or merge without explicit approval.
- Use the existing `surface/serve_infoscreen.py` process and port `8765`.
- Do not add a second HTTP server, port, daemon, systemd service, or duplicate application.
- The operator surface is served at `/local-events/studio` by the existing HTTP service.
- Runtime and operator state belongs under `surface/.env/local_event_studio/` and is not committed.
- Unpublished rules must not affect production collection.
- Published rules are enabled per source/listing URL; one source failure must not clear unrelated sources.
- Structured data may enrich a rendered, admitted list card but may not independently create an activity.
- Screenshot coordinates are annotation aids only. Published extraction rules use DOM selectors and explicit field mappings.
- Each implementation phase has its own reviewable commit and tests. Do not advance a phase while its deterministic checks fail.
- Do not claim live-source, Surface deployment, browser, or semantic correctness without direct evidence for the exact commit.

## Product workflow

The complete local workflow is:

```text
choose source and listing URL
-> capture the official listing page
-> inspect screenshot and DOM evidence
-> identify repeated activity cards
-> map title, when, where, public detail URL, summary, and optional image
-> mark excluded content
-> save a draft rule
-> test the draft against a captured snapshot
-> inspect accepted and rejected rows with field evidence
-> publish a version
-> run that source with the published rule
-> inspect final runtime output
-> roll back when required
```

The workflow must be usable entirely on the Surface through the existing InfoScreen HTTP service. It must not depend on sending screenshots to an external reviewer or editing JSON manually.

## Local storage model

```text
surface/.env/local_event_studio/
├── snapshots/
│   └── <source-id>/<snapshot-id>/
│       ├── page.png
│       ├── page.html
│       ├── dom.json
│       └── metadata.json
├── rules/
│   └── <source-id>/<listing-key>/
│       ├── draft.json
│       ├── published.json
│       └── history/
├── test-runs/
└── crawl-runs/
```

Writes must be atomic. Source IDs and listing URLs must be validated against `surface/conf/event_sources.json`. File and directory names must be derived from validated identifiers rather than arbitrary request paths.

## Published rule contract

A published rule is versioned and bound to one configured source/listing URL pair.

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
      "title": "main h1",
      "when": "[data-field='date']",
      "where": "[data-field='venue']"
    }
  },
  "validation": {
    "require_public_detail_url": true,
    "require_current_or_future_date": true
  }
}
```

The persisted schema must use typed validation. Invalid selectors, unsupported fields, unknown sources, unconfigured listing URLs, unsafe paths, and malformed versions must be rejected before writing.

## Field and admission authority

### Public detail URL

An accepted row must use the public activity detail URL from the admitted card or an explicitly configured source rewrite. The URL must:

- belong to an allowed official domain;
- differ from the listing URL;
- not be an image, document, JSON/API endpoint, internal CMS endpoint, fragment-only URL, or synthetic placeholder;
- retain the listing URL separately as evidence;
- expose the DOM element and raw attribute used to obtain it.

### When and where

The fixed field precedence is:

```text
explicitly mapped detail-page field
-> explicitly mapped list-card field
-> structured value matched to that admitted card
-> empty
```

The collector must not derive final `when` or `where` from arbitrary page-wide text. The source display name is not a venue fallback unless the published rule explicitly enables `allow_source_default`.

Each tested field must retain evidence containing the page role, selector, raw text or attribute, normalized value, and chosen precedence.

### Positive activity intent

A candidate is an activity only when it comes from the published card selector for the configured official listing and passes the required field and URL checks. Page-wide XHR, embedded state, JSON-LD, navigation, facilities, membership, parking, dining, advertising, and promotion records cannot independently create output rows.

## Staged implementation

### Phase 0 — Temporary plan and baseline

Deliverables:

- this temporary plan;
- confirmed clean base `66a6567356ebf7b47817e40f896fc0cecaadb978`;
- no runtime behavior change.

Exit checks:

- branch differs from the base only by this plan file;
- no new service, port, source module, API, or frontend asset.

### Phase 1 — Rule storage and version management

Implement the local data layer only. Do not expose HTTP routes and do not connect it to production collection.

Capabilities:

- typed rule schema and validation;
- configured source/listing URL validation;
- draft save/load/delete;
- publish with monotonic version;
- immutable history copy;
- rollback by creating a new published version from history;
- atomic writes;
- safe path derivation;
- import/export of validated rules;
- deterministic unit tests using temporary directories.

Exit checks:

- production Local Events output is unchanged;
- invalid/unknown source and listing combinations are rejected;
- interrupted writes cannot replace a valid published rule with a partial file;
- history and rollback behavior are covered by tests.

### Phase 2 — Existing 8765 API integration

Add Local Event Studio routes to `surface/serve_infoscreen.py`, its Pydantic models, OpenAPI generation, and contract tests.

Planned routes:

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

The API remains local and unauthenticated under the repository's existing trusted-device boundary. Mutating routes must validate bodies and return specific errors. This phase still does not change production collection.

### Phase 3 — Snapshot capture

Add a one-shot capture job invoked by the existing HTTP server. It saves a full-page screenshot, HTML, normalized DOM evidence, and metadata under the local Studio directory.

Requirements:

- configured source/listing URL only;
- explicit timeout and subprocess result;
- no unrestricted site crawling;
- no page-wide network payload collection by default;
- stable DOM evidence IDs for annotation;
- capture status and failure details exposed through the existing API;
- tests use fixture HTML and mocked browser boundaries, not external network access.

### Phase 4 — Local annotation UI

Add the Studio frontend under `surface/web/` and serve it through `8765`.

Required interactions:

- choose source, listing URL, and snapshot;
- inspect screenshot and corresponding DOM outlines;
- click or box-select an element, then resolve it to DOM evidence;
- select at least two example cards to infer and preview a repeated card selector;
- map title, when, where, URL, summary, and optional image selectors;
- add exclusion selectors;
- edit selectors directly;
- save a draft;
- keyboard-accessible controls, loading, empty, error, success, and retry states.

Coordinates remain snapshot UI state and are not part of the published rule.

### Phase 5 — Draft test and evidence preview

Execute a draft rule against a stored snapshot without changing production runtime data.

The preview must show:

- matched card count;
- accepted and rejected rows;
- rejection reason per row;
- final title, when, where, URL, summary;
- selector, source page role, raw value, normalized value, and precedence per field;
- warnings for duplicate cards, listing URLs, non-public URLs, missing dates, and source-default venues.

Publishing is blocked when mandatory validation fails.

### Phase 6 — Per-source production integration

Production behavior becomes:

```text
no published Studio rule -> existing legacy collector for that source/listing
published Studio rule -> Studio selector-based collector for that source/listing
```

Requirements:

- activate one source/listing pair at a time;
- structured records can enrich only a matched admitted card;
- detail reads use only the admitted card's validated public URL;
- detail failure keeps valid list evidence and records the failure;
- one Studio source failure does not affect legacy or Studio results from other sources;
- previous verified source rows may be retained only under an explicit per-source partial policy;
- debug output identifies the rule version and evidence source.

### Phase 7 — Esplanade live migration and acceptance

Use the local Studio workflow to migrate Esplanade first.

Required evidence:

- real snapshot from the configured Esplanade listing;
- published rule version;
- test preview showing real activity cards and rejection evidence;
- live collector output for Esplanade;
- each accepted URL opens the correct public detail page;
- `when` and `where` agree with the mapped list/detail evidence;
- zero non-activity output in the inspected sample;
- all unconfigured sources retain their previous collection path.

Repository tests alone are not live-source acceptance.

### Phase 8 — Incremental source migration

Migrate sources one at a time using capture, annotation, draft test, publication, live run, and visible verification. Do not apply a guessed selector or global filter to every source simultaneously.

### Phase 9 — Deployment and operation

Use only existing units:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

Document code update, existing-unit reinstall, HTTP restart, immediate Local Events trigger, Studio access, rule version inspection, rollback, and per-source evidence inspection. Do not add a Studio service or port.

### Phase 10 — Final documentation consolidation and plan removal

This phase is mandatory before delivery.

- merge implemented architecture and storage into `docs/design.md`;
- merge requirement boundaries and acceptance evidence into `docs/questions.md` using its required clarification structure;
- merge actual routes and payload contracts into `docs/api-spec.md`;
- merge supported deployment and operation commands into `README.md`;
- remove stale claims contradicted by the final implementation;
- delete `docs/plans/local-event-studio.md`;
- verify no references to the temporary plan remain;
- verify no second port, service, duplicate server, or temporary annotation implementation remains.

## Commit and evidence discipline

For every phase:

- one focused commit or a small ordered set when tests must precede implementation;
- exact changed-file list;
- deterministic tests added in the existing test layout;
- actual checks distinguished from checks not run;
- final diff reviewed for unrelated files;
- no generated runtime data, screenshots, logs, caches, or local rules committed;
- no live-source or Surface correctness claim without exact-revision evidence.

## Current phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| 0 — plan and baseline | in progress | branch confirmed identical to `66a6567` before creating this file |
| 1 — rule storage | pending | none |
| 2 — 8765 API | pending | none |
| 3 — snapshot capture | pending | none |
| 4 — annotation UI | pending | none |
| 5 — draft test | pending | none |
| 6 — production integration | pending | none |
| 7 — Esplanade acceptance | pending | none |
| 8 — source migration | pending | none |
| 9 — operations | pending | none |
| 10 — consolidation and plan deletion | pending | none |
