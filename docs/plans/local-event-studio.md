# Local Event Studio implementation plan

Status: temporary working record on `develop/surface-local-events-coverage`.

This file is not final product documentation. It must be deleted before delivery after the final implementation is folded into the existing project documents without replacing unrelated InfoScreen content.

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
- Complete deterministic work without pausing for operator input. Operator participation begins only at real-source semantic selection.
- Do not create or depend on a new CI workflow for this feature.
- Do not replace or broadly rewrite README, design, API, or questions content around Local Events.

## Current development-branch install and run

Run this on the Surface from the existing checkout:

```bash
cd ~/infoscreen
git fetch origin
git switch develop/surface-local-events-coverage \
  || git switch -c develop/surface-local-events-coverage \
       --track origin/develop/surface-local-events-coverage
git pull --ff-only origin develop/surface-local-events-coverage
bash deploy/scripts/install-user-systemd.sh
```

The existing installer now:

- installs missing Ubuntu packages required by the current runtime (`python3`, `python3-pip`, `curl`, and Chromium);
- installs Pydantic 2 and Playwright for the same user that runs the existing systemd user service;
- installs and restarts the existing `infoscreen-http.service` and existing producer units;
- checks `http://127.0.0.1:8765/local-events/studio/`;
- checks `/api/local-events/studio/sources`;
- exits with the HTTP service status and journal when either check fails;
- prints the dashboard and Studio URLs when ready.

After the command finishes successfully, open on the Surface:

```text
http://127.0.0.1:8765/local-events/studio/
```

There is no second server, service, port, or separate deployment command.

## Problems this work must fix

1. Activity links must point to the matching public official detail page.
2. `when` and `where` must come from explicitly mapped fields on the admitted list card or its validated detail page.
3. Navigation, membership, dining, parking, promotions, facilities, and other non-activity content must not become activities.
4. The operator must be able to correct each official source locally without changing Python extraction code for every page redesign.
5. A source-specific correction must not clear or alter unrelated sources.

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

Code present on the development branch:

- Pydantic schema and configured binding validation;
- draft save/load/delete;
- monotonic publication and immutable history;
- rollback as a new version;
- import/export;
- atomic writes and path confinement;
- deterministic storage tests.

### Phase 2 — existing `8765` rule API

Code present on the development branch:

- sources and per-listing state;
- draft/published/history reads;
- draft save/delete;
- publish, rollback, import, and export;
- request/response models and generated OpenAPI;
- HTTP lifecycle tests.

No additional process or port is introduced.

### Phase 3 — snapshot capture

Code present on the development branch:

- one-shot capture job invoked by the existing HTTP service;
- configured binding validation before browser launch;
- screenshot, rendered HTML, bounded DOM evidence, and metadata;
- atomic snapshot publication;
- snapshot catalog and whitelisted asset reads;
- path and symlink confinement;
- no page-wide network-response body collection.

### Phase 4 — local annotation UI

Code present at `/local-events/studio/`:

- source/listing/snapshot selection;
- capture and reload;
- screenshot and DOM overlay;
- click and drag selection;
- repeated-card selector inference;
- field mappings and exclusions;
- draft, import/export, test, publication, history, and rollback controls;
- accepted/rejected evidence preview;
- production run and result inspection.

### Phase 5 — deterministic draft test and publication gate

Code present on the development branch:

- bounded selector engine;
- offline snapshot evaluation;
- official public URL and date validation;
- accepted/rejected rows with field evidence;
- atomic test-run persistence;
- semantic rule fingerprint;
- service-side publication gate;
- stale-test indication.

### Phase 6 — per-source production integration

Code present in the existing Local Events job path:

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

### Phase 7 — Esplanade rule creation

Not completed.

Required work in the running Studio:

- capture the configured Esplanade listing;
- select at least two actual repeated activity cards;
- map title, when, where, and public detail URL;
- exclude visible non-activity cards;
- test the draft and inspect accepted/rejected rows;
- publish the exact tested draft;
- run Local Events from the same page;
- correct any remaining link, time, venue, or non-activity errors.

### Phase 8 — incremental source migration

Pending after Esplanade. Migrate one source at a time through capture, annotation, test, publish, run, and correction. Never distribute one guessed selector or global blacklist across all sources.

### Phase 9 — final documentation consolidation

Pending.

The four permanent project documents were restored to their pre-Studio content after an earlier broad rewrite. At delivery, add only the narrowly relevant material:

- deployment and operator commands in the existing README deployment/operation sections;
- architecture and data flow in `docs/design.md`;
- endpoint contracts in `docs/api-spec.md`;
- misunderstood requirement boundaries in `docs/questions.md`.

Do not recast the entire InfoScreen project around Local Event Studio.

### Phase 10 — final consolidation and plan deletion

Pending after the source rules and operator flow are complete.

- verify no second port/service/server or abandoned duplicate implementation;
- verify permanent documents contain only narrow, accurate additions;
- verify no references depend on this temporary plan;
- delete this file before delivery.
