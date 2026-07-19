# Local Event Studio implementation plan

Status: temporary working record on `develop/surface-local-events-coverage`.

This file is not final product documentation. It must be deleted before delivery after the implementation is folded narrowly into the existing project documents without replacing unrelated InfoScreen content.

## Fixed constraints

- Work only on `develop/surface-local-events-coverage`.
- Do not modify `main`, create a PR, merge, reset, force-push, delete branches, or release without explicit approval.
- Use the existing `surface/serve_infoscreen.py` process and port `8765`.
- Do not add another HTTP server, port, daemon, database, systemd service, or duplicate application.
- Serve `/local-events/studio/` through the existing HTTP service.
- Store local state under `surface/.env/local_event_studio/`; never commit runtime rules, browser profiles, captures, logs, or screenshots.
- Drafts and test runs must not affect production collection.
- Published rules are enabled only for their configured source/listing pair.
- One source failure must not clear unrelated sources.
- Structured data may enrich a candidate already admitted from the official listing but may not independently create an activity.
- Do not use an iframe or a screenshot as the operator interaction surface.
- Do not create or depend on a new CI workflow for this feature.
- Do not replace or broadly rewrite README, design, API, or questions content around Local Events.

## Problems this work must fix

1. Activity links must point to the matching public official detail page.
2. `when` and `where` must come from explicitly mapped fields on the admitted listing card or its verified detail page.
3. Navigation, membership, dining, parking, promotions, facilities, and other non-activity content must not become activities.
4. Official sites that require filters, scrolling, expansion, Load More, pagination, native selects, waits, or detail-page interaction must be handled as multi-step browser workflows rather than one static page read.
5. Every accepted listing candidate must open and verify its public official detail page before becoming output.
6. The operator must be able to correct each official source locally without changing Python extraction code for every page redesign.
7. A source-specific correction must not clear or alter unrelated sources.

## Development-branch install and run

Run on the Surface from the existing checkout:

```bash
cd ~/infoscreen
git fetch origin
git switch develop/surface-local-events-coverage \
  || git switch -c develop/surface-local-events-coverage \
       --track origin/develop/surface-local-events-coverage
git pull --ff-only origin develop/surface-local-events-coverage
bash deploy/scripts/install-user-systemd.sh
```

The existing installer is the only deployment entrypoint. It installs missing Python/Chromium dependencies, installs and restarts the existing user units, and checks the existing `8765` Studio route and source API.

Open on the Surface:

```text
http://127.0.0.1:8765/local-events/studio/
```

There is no second server, service, port, or deployment command.

## Correct product workflow

```text
choose configured source/listing in the existing Studio page
-> open a real headed Chromium window on the Surface desktop
-> browse the real official website normally
-> record required listing actions:
   click / repeat click / select option / scroll to bottom / wait
-> select the repeated activity-card DOM structure
-> select the public detail link inside that card
-> open real detail pages normally
-> record required detail-page actions
-> map title / when / where and optional summary / image on listing or detail pages
-> return to the configured listing
-> validate several real listing candidates by opening their real detail pages
-> save an inert draft and exact semantic fingerprint
-> publish only the exact live-validated draft
-> replay recorded actions in the existing Local Events producer
-> open and verify every accepted detail page sequentially
-> inspect final results in the existing Studio page
```

Screenshots may be retained only as diagnostic evidence after validation. They are not used for clicking, element selection, scrolling, or page interaction.

## Recorded browser actions

Published rules may contain ordered `listing_actions` and `detail_actions`.

Supported actions:

- `click`: click one required or optional control once;
- `click_repeat`: repeatedly click controls such as Load More until unavailable or the configured limit is reached;
- `select_option`: replay a native select value;
- `scroll_to_bottom`: scroll repeatedly until document height stabilizes;
- `wait`: wait for site-specific asynchronous rendering.

Each action is part of the rule fingerprint and immutable published history. Changing an action makes the previous validation stale and requires validation again.

Cookie or consent controls that may not appear on every run must be explicitly recorded as optional. Missing required action targets fail that source rather than silently continuing with an unprepared page.

## Listing and detail authority

A published rule is bound to one configured source/listing pair and contains:

- ordered listing actions;
- repeated activity-card selector;
- zero or more exclusion selectors;
- explicit listing-card mappings for title, when, where, detail URL, summary, and image;
- ordered detail actions;
- optional detail-page field mappings;
- explicit source-default venue opt-in;
- public-detail URL and current/future date validation;
- monotonically increasing version and immutable history.

Only a card matched on the configured official listing may become a candidate. Page-wide JSON, XHR, JSON-LD, navigation, facilities, membership, parking, dining, and promotions cannot independently create output rows.

Every candidate must then pass all of these detail checks:

- URL is a public HTTP/HTTPS URL on an allowed official domain;
- URL is not the listing itself, an API/internal endpoint, media file, PDF, or synthetic fragment;
- detail request succeeds and does not redirect outside allowed official domains;
- detail page contains readable content;
- recorded detail actions replay successfully;
- required title, time/date, and venue values are present after detail mapping;
- date parses and is current or future;
- duplicate final detail URLs are rejected.

Field precedence is:

```text
explicit mapped detail-page field
-> explicit mapped listing-card field
-> matched structured enrichment
-> explicit source default only when enabled
-> reject when a required value remains missing
```

## Local storage

```text
surface/.env/local_event_studio/
├── live/
│   ├── <source-listing>.json
│   ├── <source-listing>.log
│   └── <source-listing>-profile/
├── snapshots/<source-id>/<snapshot-id>/
│   ├── page.png
│   ├── page.html
│   ├── dom.json
│   └── metadata.json
├── rules/<source-id>/<listing-hash>/
│   ├── draft.json
│   ├── published.json
│   └── history/vNNNNNN.json
└── test-runs/<source-id>/<run-id>.json
```

Rule and test writes are atomic. Source IDs and listing URLs are validated against `surface/conf/event_sources.json`. Runtime path components are derived from validated bindings.

## Current implementation status

Code currently present on the development branch includes:

- Pydantic rule, selector, validation, and browser-action models;
- configured source/listing binding checks;
- draft, publish, immutable history, import/export, and rollback storage;
- existing `8765` rule APIs and Studio route;
- detached headed Chromium worker started by the existing HTTP process;
- real-site shadow-DOM selection toolbar;
- semantic repeated-card ancestor selection with narrower/wider adjustment;
- listing and detail field selection against the real DOM;
- recording of listing/detail clicks, repeat clicks, native selects, scroll, and wait actions;
- live validation that opens several official detail pages;
- publication fingerprint including recorded actions;
- production replay of recorded actions;
- sequential detail-page verification before output;
- per-source production replacement and partial-source protection;
- Studio display of mappings, actions, live validation, publication, and final producer output.

This status means code exists on the branch. It does not mean the current commit has been run successfully on the Surface.

## Remaining work

### Static and offline checks

- run Python compilation for all affected modules;
- run focused rule/action/frontend/backend tests;
- run the repository test suite;
- correct any syntax, import, schema, or contract failures;
- review the full branch diff for abandoned screenshot UI code and unrelated changes.

### Surface interaction check

- update and restart the existing deployment;
- open the Studio route;
- confirm `OPEN REAL BROWSER` opens visible Chromium on the Surface desktop;
- confirm the toolbar survives scrolling, full navigation, and same-page application navigation;
- confirm recorded actions appear in the main Studio page;
- confirm changing a selector or action invalidates the previous live validation.

### Esplanade source rule

- prepare the real Esplanade listing using recorded actions when required;
- select at least two repeated real activity cards;
- select the public detail link;
- map required fields on the real detail pages;
- validate several candidates and inspect rejections;
- publish the exact tested draft;
- run the existing Local Events producer;
- correct remaining wrong links, times, venues, or non-activity rows.

### Incremental source migration

After Esplanade, migrate one configured listing at a time through real browsing, action recording, mapping, validation, publication, production run, and correction. Never distribute one guessed selector or global title/path blacklist across all sources.

### Final consolidation

- verify no second port, service, server, or abandoned duplicate implementation;
- add only narrow, accurate operator/API/design clarifications to existing permanent documents;
- remove temporary or obsolete screenshot-annotation tests/assets;
- delete this temporary plan before delivery.
