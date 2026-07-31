# Local Events Preview static acceptance report

Date: 2026-07-31 (Asia/Singapore)

Branch: `develop/surface-local-events-coverage`

Reviewed head before this report: `a5ad706e0ff742a941eb99d493c99f4653df13c9`

## 1. Result

**Static acceptance: PASS WITH RUNTIME VALIDATION REQUIRED**

**Full acceptance: NOT COMPLETE**

The reviewed source, static contracts, state boundaries, frontend protocol, OpenAPI descriptions, and regression definitions are internally consistent for the fixes covered by this report. No runtime, browser, device, service, test-suite, or CI evidence was produced during this review, so this report does not claim end-to-end operational acceptance.

## 2. Acceptance scope

This report covers the Local Event Studio Preview pipeline and the subsequent selected-event collection path, including:

- Preview authority composition order;
- ArtScience Preview recognition and detail enrichment ownership;
- isolated Preview state handling;
- REAL EVENT / NOT EVENT selection persistence;
- List Page decision and selection-file consistency;
- detail-page redirect identity handling;
- selected-only filtering before formal detail navigation;
- Studio workflow guidance and encoded review protocol;
- OpenAPI and architecture contract alignment;
- static regression definitions associated with these boundaries.

It does not accept unrelated dashboard, Calendar, Market, Weather, News, photo, deployment, or producer behaviour.

## 3. Accepted findings and fixes

### 3.1 Preview composition ownership

The complete Preview pipeline is composed by `preview_final_detail_handoff_authority.apply_preview_pipeline()` in the established order:

1. Preview event selection;
2. Preview collector;
3. ArtScience Preview recognition;
4. Preview detail enrichment;
5. Preview transport;
6. final detail and expiry handoff.

`review_summary_authority` delegates to this owner instead of maintaining a second copy of the order. Existing authority modules and compatibility entrypoints remain present.

Status: **accepted by static inspection**.

### 3.2 Outdated owner tests

Static tests that still inspected the former composition owner were updated to inspect the final handoff owner. Tests that still expected final Preview output to remain `listing_evidence_only` were aligned with the current `official_detail_pages` handoff contract while preserving the assertion that the listing stage itself does not open detail pages.

Status: **accepted by static inspection**.

### 3.3 Selection-file rollback

The Preview selection file is written through atomic replacement. If the subsequent List Page state write fails, the previous selection-file bytes are restored, or a newly created file is removed. A rollback failure is surfaced explicitly rather than silently leaving a half-committed state.

Status: **accepted by static inspection and regression definition**.

### 3.4 Redirect-safe candidate identity

Before the fix, Preview detail enrichment could replace `candidate_id` using the final redirected detail URL, while formal collection filtered cards before navigation using the original listing-card URL. A redirected selected REAL EVENT could therefore be discarded before its detail page was opened.

The corrected contract is:

- `candidate_id` retains the original rendered list-card link identity;
- `listing_detail_url` records the original official listing link;
- `detail_url` records the final public detail URL after navigation or redirect;
- the Studio submits both URLs in the existing `preview-review-v1:` envelope;
- backend validation checks both URLs against the institution allow-list;
- identity validation uses the original listing link;
- formal pre-navigation filtering accepts the original candidate identity or original URL;
- final result filtering accepts candidate identity, original URL, or final URL;
- old persisted selection rows without `listing_detail_url` fall back to `detail_url`.

No new field was added to the `EventCandidate` model. The additional mapping is Preview metadata and selection-protocol state only.

Status: **accepted by static inspection and regression definitions**.

### 3.5 Preview workflow guidance

The initial Preview panel no longer says candidates cannot be reviewed or that review actions are disabled. It now accurately explains that every candidate must be classified as REAL EVENT or NOT EVENT and that choices are committed only when the List Page review is saved.

Status: **accepted by static inspection**.

### 3.6 Review-state isolation and locking

`POST /api/local-events/review/preview-events`, List Page decisions, and formal Event collection are all executed under the same `REVIEW_MUTATION_LOCK`. The isolated Preview uses a temporary Review root and does not directly alter the real `state.json`, persisted Event candidates, feedback, collection metadata, or kiosk projection.

The temporary global collector/browser substitutions remain order-sensitive implementation details, but the HTTP mutation lock prevents these operations from overlapping through `ThreadingHTTPServer` review mutation routes.

Status: **accepted by static inspection**.

### 3.7 Documentation and OpenAPI

The design and OpenAPI contracts now describe:

- `preview_event_selections.json`;
- complete REAL EVENT / NOT EVENT review;
- the `preview-review-v1:` envelope;
- selection rollback when List Page state persistence fails;
- selected-only formal collection;
- the distinction between isolated Preview transport and formal HTTP/1 collection policy.

Status: **partially accepted**. See remaining documentation gaps below.

## 4. Preserved functionality

The reviewed changes do not intentionally remove or bypass:

- Preview from pending, confirmed, or rejected List Pages;
- isolated temporary Review state;
- ArtScience source-specific Preview recognition;
- ArtScience fresh browser process per detail candidate;
- MBS headed Chromium and diagnostic NetLog handling;
- official detail-page enrichment;
- REAL EVENT / NOT EVENT decisions;
- Preview panel session restoration;
- selected-only formal collection;
- final Preview expiry retention for operator review;
- HTTP/1 collection policy;
- persisted Event review and kiosk projection.

## 5. Static evidence added or corrected

The reviewed branch contains static or unit-test definitions covering:

- Preview pipeline owner and exact composition order;
- ArtScience-before-transport order;
- final detail handoff ownership;
- selection-file rollback on List Page write failure;
- mandatory REAL EVENT / NOT EVENT review before confirmation;
- selected-card filtering before detail navigation;
- preservation of original candidate identity across redirects;
- storage and transport of `listing_detail_url` and final `detail_url`;
- frontend Preview workflow and script order;
- OpenAPI selected-event collection and Preview selection descriptions.

These are test definitions only. They were inspected but not executed in this review.

## 6. Checks not run

The following were not run:

- Python imports or compilation;
- pytest or any other test suite;
- JavaScript execution;
- Playwright or Chromium;
- live ArtScience or MBS collection;
- HTTP server or API requests;
- Surface systemd services or timers;
- deployment scripts;
- repository acceptance scripts;
- GitHub Actions or CI reruns;
- manual browser interaction.

Reason: the controlling repository instructions for this task require static-only work and prohibit project execution and CI triggering.

## 7. Remaining gaps and blockers

### 7.1 Runtime acceptance is still required

The exact branch head must still be exercised on the Surface or equivalent deployment to prove:

- Preview loads real candidates;
- ArtScience/MBS detail pages complete under the deployed browser/session constraints;
- REAL EVENT / NOT EVENT choices survive render and page-state refresh;
- saving a List Page commits the expected selection file and page decision;
- a redirected selected candidate survives formal pre-navigation filtering;
- formal collection persists only selected REAL EVENT candidates;
- no unselected candidate detail page is opened;
- failure rollback leaves both persistence files consistent;
- the final Studio UI and kiosk projection are correct.

### 7.2 Documentation remains incomplete

`README.md` and `docs/api-spec.md` still contain older descriptions that imply a confirmed List Page causes unrestricted collection of all recognised candidates. They must be updated to describe complete Preview classification and selected-only formal collection.

### 7.3 Empty URL canonicalisation boundary

The browser helper `canonical("")` may resolve an empty value against the current Studio page URL. The current rendered Preview path is expected to provide detail links, but this boundary should be hardened and covered before full acceptance.

### 7.4 Commit-history cleanliness

Earlier reverted cleanup commits remain in branch history. The final tree was restored before the accepted incremental work, but the history has not been rewritten or squashed because doing so would require an explicitly authorised destructive ref update.

## 8. Final verdict

| Gate | Result |
| --- | --- |
| Source ownership and composition | PASS (static) |
| Preview state isolation | PASS (static) |
| Selection persistence consistency | PASS (static) |
| Redirect-safe selected-event identity | PASS (static) |
| Frontend/backend protocol consistency | PASS (static) |
| Static regression definitions | PASS (definitions inspected, not executed) |
| Documentation consistency | PARTIAL |
| Runtime/browser/device validation | NOT RUN |
| Test-suite validation | NOT RUN |
| CI validation | NOT RUN |
| Full production acceptance | BLOCKED |

The branch is suitable for the next runtime validation stage, but it is not valid to describe it as fully accepted until the remaining documentation gaps are corrected and the runtime gates above pass on the exact reviewed head.