# Local Event Studio implementation plan

Status: temporary working record on `develop/surface-local-events-coverage`.

This file is not final product documentation. It must be deleted before delivery after its implemented content is consolidated into `docs/design.md`, `docs/questions.md`, `docs/api-spec.md`, and `README.md`.

## Fixed constraints

- Work only on `develop/surface-local-events-coverage`.
- Do not modify `main`, create a PR, or merge without explicit approval.
- Use the existing `surface/serve_infoscreen.py` process and port `8765`.
- Do not add another HTTP server, port, daemon, systemd service, or duplicate application.
- Serve the operator UI at `/local-events/studio/` through the existing HTTP service.
- Store local state under `surface/.env/local_event_studio/`; never commit runtime rules, captures, logs, or screenshots.
- Draft rules must not affect production collection.
- Published rules are enabled per configured source/listing pair.
- One source failure must not clear unrelated sources.
- Structured data may enrich an admitted rendered card but may not independently create an activity.
- Screenshot coordinates are UI aids only; published rules use DOM selectors and explicit field mappings.
- Complete deterministic code and test work without pausing for operator input. Operator participation begins only at real-source semantic acceptance.
- Do not claim live-source, Surface, browser, or semantic correctness without direct evidence for the exact commit.

## Product workflow

```text
choose configured source/listing
-> capture official listing page locally
-> inspect screenshot with DOM evidence overlay
-> identify two real activity-card examples
-> infer or edit card selector
-> map title / when / where / detail URL / summary / image
-> add exclusion selectors
-> save draft
-> test draft against stored snapshot
-> inspect accepted/rejected rows and field evidence
-> publish exact tested draft
-> activate published rule for that source/listing
-> inspect live output
-> roll back by publishing a historical version as a new version
```

The workflow is local to InfoScreen and does not require sending screenshots to an external reviewer or editing JSON manually.

## Local storage

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

All writes are atomic. Source IDs and listing URLs are validated against `surface/conf/event_sources.json`. User-controlled path components are never used directly as filesystem paths.

## Rule and admission contract

A published rule is bound to one configured source/listing pair and contains:

- repeated card selector;
- zero or more exclusion selectors;
- explicit list-card mappings for title, when, where, URL, summary, and image;
- optional detail-page mappings for title, when, where, summary, and image;
- explicit opt-in for source default venue;
- public-detail URL and current/future date validation flags;
- monotonically increasing published version and immutable history.

Mandatory publication fields are card, title, when, where, and URL selectors. Coordinates are never part of the persisted rule.

Only a card matched by the published selector on the configured official listing may become an activity. Page-wide JSON, XHR, JSON-LD, navigation, facilities, membership, parking, dining, and promotions cannot independently create output rows.

The admitted card must provide a public HTTP/HTTPS detail URL that belongs to the configured source domain and is not a listing, media/document, API/internal CMS path, fragment, or synthetic placeholder.

Field precedence is:

```text
explicit mapped detail-page field
-> explicit mapped list-card field
-> matched structured enrichment
-> explicit source default only when rule enables it
-> empty/reject according to field requirement
```

Every tested field records page role, selector, DOM evidence ID, raw value, normalized value, attribute, and precedence.

## Phase status

### Phase 0 — temporary plan and baseline

Complete.

- Baseline preserved at `66a6567356ebf7b47817e40f896fc0cecaadb978`.
- All Studio work remains on `develop/surface-local-events-coverage`.

### Phase 1 — rule storage and version management

Implemented.

- Pydantic rule schema and source/listing validation;
- draft save/load/delete;
- monotonic publication and immutable history;
- rollback as a new version;
- import/export;
- atomic writes and safe path derivation;
- deterministic storage tests.

### Phase 2 — existing `8765` rule API

Implemented.

- sources and per-listing state;
- draft/published/history reads;
- draft save/delete;
- publish, rollback, import, and export;
- request/response models and OpenAPI;
- HTTP lifecycle tests.

No additional process or port is introduced.

### Phase 3 — snapshot capture

Implemented.

- one-shot capture job invoked by the existing HTTP service;
- configured source/listing validation before browser launch;
- full-page screenshot, rendered HTML, bounded DOM evidence, and metadata;
- atomic snapshot publication;
- snapshot list and whitelisted asset reads;
- symlink/path confinement;
- no page-wide network-response collection;
- backend and HTTP snapshot tests.

Real browser capture remains unverified for the exact branch head.

### Phase 4 — local annotation UI

Implemented.

- `/local-events/studio/` served by the existing server;
- source/listing/snapshot selection;
- capture and reload actions;
- screenshot and DOM overlay;
- click and drag selection;
- two-card selector inference;
- title/when/where/URL/summary/image mapping;
- exclusions and detail mappings;
- draft, import/export, publication, history, and rollback controls;
- frontend and responsive-style contracts.

Real browser interaction remains unverified for the exact branch head.

### Phase 5 — deterministic draft test and publication gate

Implemented.

- bounded snapshot selector engine;
- offline card matching and field extraction;
- official public URL and date validation;
- accepted/rejected rows with field evidence;
- atomic test-run persistence;
- exact semantic rule fingerprint;
- service-side publication gate requiring a current publishable test;
- accepted/rejected preview and stale-test indication;
- backend, HTTP, frontend, and style contracts.

### Phase 6 — per-source production integration

Implemented in code.

Runtime order is now:

```text
existing structured-first collector
-> apply only published Studio source/listing rules
-> synchronize Studio detail dates
-> mark failed or zero-acceptance Studio sources incomplete
-> normalize existing output contract
-> preserve existing partial-write protection
```

Activation behavior is:

```text
no published rule -> legacy result remains
all configured listings for source published -> source becomes Studio-only
some listings published -> replace only legacy rows with matching listing evidence
Studio source failure or zero accepted result -> source incomplete and payload partial
```

Implemented evidence includes:

- published-rule discovery;
- one reusable browser per Studio source;
- selector-based list admission;
- optional admitted-detail rendering;
- detail field precedence and evidence;
- source/listing activation metadata;
- unrelated-source preservation;
- final date synchronization after detail overrides;
- runtime bridge in `surface/jobs/local_event_search.py`;
- job-order, collector, pipeline, and runtime tests.

Repository-wide execution is not claimed: the current environment cannot clone the repository and the exact branch head has no attached CI status or workflow run.

### Phase 7 — Esplanade live migration and semantic acceptance

Pending operator interaction.

Operator input begins here because a human must confirm that visible official page regions and extracted fields represent real activities.

Required evidence:

- real Esplanade snapshot captured through Studio;
- two or more confirmed activity cards;
- explicit field mappings;
- publishable draft test;
- published rule version;
- live Local Events run;
- correct public detail URLs;
- detail/list evidence agreeing with `when` and `where`;
- zero non-activity rows in the inspected sample;
- unrelated sources still using their prior path.

Repository tests alone do not satisfy this phase.

### Phase 8 — incremental source migration

Pending.

Migrate one source at a time through capture, annotation, test, publish, live run, and semantic inspection. Never distribute one guessed selector or global title/path blacklist across all sources.

### Phase 9 — deployment and operation documentation

Pending consolidation into `README.md`.

Only the existing units may be used:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

Documentation must cover update, existing-unit reinstall, HTTP restart, immediate Local Events trigger, Studio access, rule inspection, test evidence, rollback, and source failure diagnosis.

### Phase 10 — final documentation consolidation and plan deletion

Pending after live acceptance.

- merge architecture/storage/runtime behavior into `docs/design.md`;
- merge requirement boundaries and acceptance evidence into `docs/questions.md`;
- merge actual routes and schemas into `docs/api-spec.md`;
- merge deployment and operation into `README.md`;
- delete this temporary plan;
- verify no references to it remain;
- verify no second port/service/server or unused temporary Studio implementation remains.

## Current evidence summary

| Phase | Status | Evidence level |
| --- | --- | --- |
| 0 — plan and baseline | complete | branch history and temporary plan |
| 1 — rule storage | implemented | source and deterministic tests present; repository-wide execution pending |
| 2 — `8765` rule API | implemented | models/OpenAPI/server/HTTP tests present; repository-wide execution pending |
| 3 — snapshot capture | implemented | code and deterministic tests present; real browser capture pending |
| 4 — annotation UI | implemented | frontend/style contracts present; real browser interaction pending |
| 5 — draft test | implemented | evaluator/API/UI tests present; repository-wide execution pending |
| 6 — production integration | implemented in code | collector/pipeline/job tests present; live run pending |
| 7 — Esplanade acceptance | pending operator interaction | no live evidence |
| 8 — source migration | pending | no live evidence |
| 9 — operations | pending | formal documentation not yet consolidated |
| 10 — consolidation | pending | temporary plan still present |
