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

## Rule contract

A published rule is bound to one configured source/listing pair and contains:

- repeated card selector;
- zero or more exclusion selectors;
- explicit list-card mappings for title, when, where, URL, summary, and image;
- optional detail-page mappings for title, when, where, summary, and image;
- explicit opt-in for source default venue;
- public-detail URL and current/future date validation flags;
- monotonically increasing published version and immutable history.

Mandatory publication fields are card, title, when, where, and URL selectors. Coordinates are never part of the persisted rule.

## Admission and field authority

### Activity membership

Only a card matched by the published selector on the configured official listing may become an activity. Page-wide JSON, XHR, JSON-LD, navigation, facilities, membership, parking, dining, and promotions cannot independently create output rows.

### Public URL

The admitted card must provide a public HTTP/HTTPS detail URL that:

- belongs to the source's allowed domain;
- is not the listing URL;
- is not a media/document/API/internal CMS path;
- is not a fragment or synthetic placeholder;
- may use only configured source-level public-prefix rewrites.

### Field precedence

```text
explicit mapped detail-page field
-> explicit mapped list-card field
-> matched structured enrichment
-> explicit source default only when rule enables it
-> empty/reject according to field requirement
```

Every tested field records page role, selector, DOM evidence ID, raw value, normalized value, attribute, and precedence.

## Phases

### Phase 0 — temporary plan and baseline

- Preserve baseline `66a6567356ebf7b47817e40f896fc0cecaadb978`.
- Keep this plan as the only temporary planning document.
- Remove and consolidate it in Phase 10.

### Phase 1 — rule storage and version management

Implemented scope:

- Pydantic rule schema;
- source/listing binding validation;
- draft save/load/delete;
- monotonic publication;
- immutable history;
- rollback as a new version;
- import/export;
- atomic writes and safe path derivation;
- deterministic storage tests.

### Phase 2 — existing `8765` rule API

Implemented scope:

- sources and per-listing state;
- read draft/published/history;
- save/delete draft;
- publish, rollback, import, and export;
- Pydantic request/response models;
- generated OpenAPI routes and schemas;
- HTTP closed-loop storage lifecycle tests.

No additional process or port is introduced.

### Phase 3 — snapshot capture

Implemented scope:

- one-shot capture job invoked by the existing HTTP service;
- configured source/listing validation before browser launch;
- full-page screenshot, rendered HTML, bounded DOM evidence, and metadata;
- atomic snapshot-directory publication;
- snapshot list and whitelisted asset reads;
- symlink/path confinement;
- no page-wide network-response collection;
- backend and HTTP snapshot tests.

### Phase 4 — local annotation UI

Implemented scope:

- `/local-events/studio/` served as ordinary static content by the existing server;
- source/listing/snapshot selection;
- capture and reload actions;
- screenshot and DOM overlay;
- click and drag selection;
- two-card selector inference;
- title/when/where/URL/summary/image mapping;
- exclusions and detail mappings;
- draft, import/export, publication, history, and rollback controls;
- frontend and responsive-style contracts.

### Phase 5 — deterministic draft test and publication gate

Implemented scope:

- bounded snapshot selector engine;
- offline card matching and field extraction;
- official public URL validation;
- date and duplicate validation;
- accepted/rejected rows with field evidence;
- atomic test-run persistence;
- exact semantic rule fingerprint;
- service-side publication gate requiring a current publishable test;
- accepted/rejected preview in Studio;
- stale-test indication after rule edits;
- backend, HTTP, frontend, and style contracts.

### Phase 6 — per-source production integration

In progress scope:

```text
no published rule -> legacy result remains
all configured listings for source published -> source becomes Studio-only
some listings published -> replace only legacy rows with matching listing evidence
Studio source failure or zero accepted result -> source incomplete and payload partial
```

Implemented supporting modules:

- published-rule discovery;
- live list rendering with one reusable browser per source;
- selector-based list admission;
- optional admitted-detail rendering;
- detail field precedence and evidence;
- source/listing activation metadata;
- unrelated-source preservation;
- live rule health gates;
- final date synchronization after detail overrides;
- deterministic per-source and runtime-pipeline tests.

Remaining Phase 6 work:

- connect the runtime pipeline between the existing collector and existing normalization/write flow;
- add the job-order contract test;
- run repository checks available for the exact branch head.

### Phase 7 — Esplanade live migration and semantic acceptance

Operator input begins here because a human must confirm that the visible official page regions and extracted semantic fields represent real activities.

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

Migrate one source at a time through capture, annotation, test, publish, live run, and semantic inspection. Never distribute one guessed selector or global title/path blacklist across all sources.

### Phase 9 — deployment and operation

Use only:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

Document update, existing-unit reinstall, HTTP restart, immediate Local Events trigger, Studio access, rule inspection, test evidence, rollback, and source failure diagnosis.

### Phase 10 — final documentation consolidation and plan deletion

Mandatory final cleanup:

- merge architecture/storage/runtime design into `docs/design.md`;
- merge corrected requirement boundaries and acceptance conditions into `docs/questions.md`;
- merge actual endpoints and schemas into `docs/api-spec.md`;
- merge deployment and operation commands into `README.md`;
- delete this file;
- verify no references to this plan remain;
- verify no second port/service/server or unused temporary Studio implementation remains.

## Current status

| Phase | Status | Evidence level |
| --- | --- | --- |
| 0 — plan and baseline | complete | branch history and temporary plan |
| 1 — rule storage | implemented | source and deterministic tests present; full repo run pending |
| 2 — `8765` rule API | implemented | models/OpenAPI/server/HTTP tests present; full repo run pending |
| 3 — snapshot capture | implemented | capture/API/path tests present; real browser capture pending |
| 4 — annotation UI | implemented | frontend/style contracts present; real browser interaction pending |
| 5 — draft test | implemented | evaluator/API/UI tests present; full repo run pending |
| 6 — production integration | in progress | collector/pipeline/tests present; job bridge pending |
| 7 — Esplanade acceptance | pending operator interaction | no live evidence |
| 8 — source migration | pending | no live evidence |
| 9 — operations | pending | documentation not yet consolidated |
| 10 — consolidation and plan deletion | pending | temporary plan still present |
