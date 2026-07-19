# Local Event Studio implementation plan

Status: temporary working record on `develop/surface-local-events-coverage`.

This file is not final product documentation. It must be deleted before delivery after live acceptance and final cross-document verification.

## Fixed constraints

- Work only on `develop/surface-local-events-coverage`.
- Do not modify `main`, create a PR, or merge without explicit approval.
- Use the existing `surface/serve_infoscreen.py` process and port `8765`.
- Do not add another HTTP server, port, daemon, database, systemd service, or duplicate application.
- Serve `/local-events/studio/` through the existing HTTP service.
- Store local state under `surface/.env/local_event_studio/`; never commit runtime rules, captures, logs, or screenshots.
- Drafts and test runs must not affect production collection.
- Published rules are enabled only for their configured source/listing pair.
- One source failure must not clear unrelated sources.
- Structured data may enrich an admitted rendered card but may not independently create an activity.
- Screenshot coordinates are UI aids only; published rules use selectors and explicit field mappings.
- Complete deterministic work without pausing for operator input. Operator participation begins only at real-source semantic acceptance.
- Do not claim live-source, Surface, browser, service, or semantic correctness without direct evidence for the exact commit.

## Product workflow

```text
choose configured source/listing
-> capture official listing page locally
-> inspect screenshot with DOM evidence overlay
-> identify repeated real activity cards
-> infer or edit card selector
-> map title / when / where / detail URL / summary / image
-> add exclusions and optional detail mappings
-> save inert draft
-> test against stored snapshot
-> inspect accepted/rejected rows and field evidence
-> publish exact tested fingerprint
-> run existing Local Events producer
-> inspect runtime and visible output
-> roll back by republishing history as a new version when needed
```

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

All writes are atomic. Source IDs and listing URLs are validated against `surface/conf/event_sources.json`. Runtime path components are derived from validated bindings.

## Rule and admission contract

A published rule is bound to one configured source/listing pair and contains:

- repeated card selector;
- zero or more exclusion selectors;
- explicit list-card mappings for title, when, where, URL, summary, and image;
- optional detail-page mappings;
- explicit source-default venue opt-in;
- public-detail URL and current/future date validation;
- monotonically increasing version and immutable history.

Mandatory publication fields are card, title, when, where, and URL selectors. Coordinates are never persisted as extraction authority.

Only a card matched on the configured official listing may become an activity. Page-wide JSON, XHR, JSON-LD, navigation, facilities, membership, parking, dining, and promotions cannot independently create output rows.

Field precedence is:

```text
explicit mapped detail-page field
-> explicit mapped list-card field
-> matched structured enrichment
-> explicit source default only when enabled
-> empty/reject according to field requirement
```

## Phase status

### Phase 0 — temporary plan and baseline

Complete.

- Baseline: `66a6567356ebf7b47817e40f896fc0cecaadb978`.
- All work remains on `develop/surface-local-events-coverage`.

### Phase 1 — rule storage and version management

Implemented.

- Pydantic schema and configured binding validation;
- draft save/load/delete;
- monotonic publication and immutable history;
- rollback as a new version;
- import/export;
- atomic writes and path confinement;
- deterministic storage tests.

### Phase 2 — existing `8765` rule API

Implemented.

- sources and per-listing state;
- draft/published/history reads;
- draft save/delete;
- publish, rollback, import, and export;
- request/response models and generated OpenAPI;
- HTTP lifecycle tests.

No additional process or port is introduced.

### Phase 3 — snapshot capture

Implemented.

- one-shot capture job invoked by the existing HTTP service;
- configured binding validation before browser launch;
- screenshot, rendered HTML, bounded DOM evidence, and metadata;
- atomic snapshot publication;
- snapshot catalog and whitelisted asset reads;
- path and symlink confinement;
- no page-wide network-response body collection;
- backend and HTTP snapshot tests.

Real browser capture remains unverified for the exact branch head.

### Phase 4 — local annotation UI

Implemented.

- `/local-events/studio/` through existing static serving;
- source/listing/snapshot selection;
- capture and reload;
- screenshot and DOM overlay;
- click and drag selection;
- repeated-card selector inference;
- field mappings and exclusions;
- draft, import/export, test, publication, history, and rollback controls;
- accepted/rejected evidence preview;
- initialization wait for the first source binding;
- frontend and responsive-style contracts.

Real browser interaction remains unverified for the exact branch head.

### Phase 5 — deterministic draft test and publication gate

Implemented.

- bounded selector engine;
- offline snapshot evaluation;
- official public URL and date validation;
- accepted/rejected rows with field evidence;
- atomic test-run persistence;
- semantic rule fingerprint;
- service-side publication gate;
- stale-test indication;
- backend, API, HTTP, frontend, and style contracts.

### Phase 6 — per-source production integration

Implemented in code.

```text
existing structured-first collector
-> published Studio source/listing replacement
-> Studio detail-date synchronization
-> source health enforcement
-> existing output normalization
-> completion aggregation by source
-> output-compatible partial-cache protection
```

Activation behavior:

```text
no published rule -> existing result remains
all configured listings published -> source becomes Studio-only
some listings published -> replace only matching listing-evidence rows
Studio failure or zero accepted result -> source incomplete and payload partial
```

Additional deterministic protections:

- legacy and Studio debug rows group by common source identity;
- multiple listing rows do not inflate completed source count;
- one failed listing makes its source incomplete;
- a pre-existing `partial: true` signal is retained;
- current `structured-first` missing-policy rows remain cache-eligible because the output layer displays them;
- obsolete non-empty policies remain ineligible;
- unrelated sources are preserved;
- the existing primary/partial writer boundary remains.

Repository-wide execution is not yet claimed. A branch workflow now calls the existing `scripts/run_full_ci_tests.sh` and writes an exact commit status, but the current head has not yet reported a status through the available interface.

### Phase 7 — Esplanade live migration and semantic acceptance

Pending operator interaction.

Operator input begins here because a human must confirm that visible official page regions and extracted fields represent real activities.

Required evidence:

- real Esplanade snapshot captured through Studio;
- at least two confirmed activity cards;
- explicit title/when/where/public-detail URL mappings;
- rejected non-activity rows inspected;
- publishable exact draft test;
- published rule version;
- live Local Events run;
- runtime JSON and visible card inspection;
- zero non-activity rows in the inspected sample;
- at least one unrelated source confirmed intact.

Repository tests alone do not satisfy this phase.

### Phase 8 — incremental source migration

Pending after the first live migration.

Migrate one source at a time through capture, annotation, test, publish, live run, and semantic inspection. Never distribute one guessed selector or global blacklist across all sources.

### Phase 9 — deployment and operation documentation

Complete in documentation.

- `README.md` covers Studio access, existing-unit installation/update, HTTP restart, immediate Local Events trigger, capture/test/publish workflow, rule inspection, rollback, and failure diagnosis;
- `docs/design.md` covers storage, lifecycle, production routing, completion aggregation, cache protection, and evidence levels;
- `docs/api-spec.md` covers actual routes, payloads, side effects, and activation;
- `docs/questions.md` covers requirement interpretations and acceptance boundaries.

Only existing units are used:

```text
infoscreen-http.service
infoscreen-local-events.service
infoscreen-local-events.timer
```

### Phase 10 — final consolidation and plan deletion

Pending after live acceptance.

- incorporate exact live acceptance evidence into final documents;
- verify routes/models/docs still match the accepted revision;
- verify no second port/service/server or abandoned duplicate implementation;
- verify no references depend on this temporary plan;
- delete this file before delivery.

## Current evidence summary

| Phase | Status | Evidence level |
| --- | --- | --- |
| 0 — plan and baseline | complete | branch history |
| 1 — rule storage | implemented | source and deterministic tests present; CI status pending |
| 2 — `8765` rule API | implemented | models/OpenAPI/server/HTTP tests present; CI status pending |
| 3 — snapshot capture | implemented | deterministic code/tests; real browser capture pending |
| 4 — annotation UI | implemented | frontend/style contracts; real browser interaction pending |
| 5 — draft test | implemented | evaluator/API/UI contracts; CI status pending |
| 6 — production integration | implemented in code | collector/pipeline/job/cache tests; live run pending |
| 7 — Esplanade acceptance | pending operator interaction | no live evidence |
| 8 — source migration | pending | no live evidence |
| 9 — operations documentation | complete | README/design/API/questions updated |
| 10 — final consolidation | pending | temporary plan retained until live acceptance |
