# InfoScreen requirement clarifications

This document records requirement areas that are easy to misread and the evidence needed to accept their implementation. It is organised by product requirement rather than conversation history.

## Visual language

### Easy-to-make interpretation

A TTY-inspired display requires decorative CRT noise, a dot grid, or a pixel wallpaper.

### Why it fails

Those effects compete with information and reduce readability on an always-on display.

### Correct requirement interpretation

TTY character comes from monospaced typography, aligned values, concise labels, restrained status colours, compact spacing, clear boundaries, and a quiet background.

### Required implementation

Use typography, hierarchy, alignment, borders, and state presentation rather than decorative noise.

### Acceptance evidence

Browser evidence must show readable content at the target display size and no pattern obscuring text.

## Calendar authority and unattended sync

### Easy-to-make interpretation

The Surface can act as a second Calendar client or any Python runtime can export EventKit.

### Why it fails

macOS Calendar owns accounts, permissions, and authoritative Event state. A Python runtime without `import EventKit` cannot export Calendar data.

### Correct requirement interpretation

Calendar follows EventKit -> Mac export -> SSH/SCP -> Surface runtime JSON -> browser.

### Required implementation

Probe an EventKit-capable Python, keep machine settings in uncommitted `mac/local.env`, and copy to the canonical Surface runtime file.

### Acceptance evidence

Show unattended LaunchAgent execution, a changed Surface file, current HTTP modification time, and visible Calendar output.

## Runtime freshness and refresh layers

### Easy-to-make interpretation

One online indicator or one generic refresh interval proves all data is current.

### Why it fails

The server can remain online while individual files are stale, missing, or unreachable. Producer refresh, browser reload, visual rotation, and operator-state refresh are different operations.

### Correct requirement interpretation

The Sync ticker observes per-file `Last-Modified`. The Local Event Studio refreshes only at explicit operations, manual reload, and tab return.

### Required implementation

Keep per-file freshness checks and do not continuously clear and rebuild review cards.

### Acceptance evidence

Leave the review page idle and during a long operation: it must not flash repeatedly or lose scroll.

## Local Events source-specific collection

### Easy-to-make interpretation

All official sites can be handled by one selector, recursive crawler, or generic search scraper.

### Why it fails

Official sites differ in rendering, expansion, APIs, detail fields, pagination, anti-bot behaviour, and timing.

### Correct requirement interpretation

`surface/conf/event_sources.json` defines curated official institutions, allowed domains, configured list URLs, and adapter behaviour. A rendered card on an official list proves membership.

### Required implementation

Render and expand every configured list, isolate official activity cards, preserve list evidence, and enrich admitted cards from their official detail page when one exists.

### Acceptance evidence

For an affected organisation, evidence must include a real collector run, list-card evidence, diagnostics, final runtime JSON, and visible output.

## Local Events complete inventory coverage

### Easy-to-make interpretation

A global deadline, small detail limit, queue timeout, or first-source success may be used to shorten a difficult collection run.

### Why it fails

Queued sources can be marked `skipped_by_global_deadline` without ever starting. A fixed small detail budget can discard later valid cards. This silently lowers the configured 18-source product scope and can reduce the final output to one institution.

### Correct requirement interpretation

Every configured source must receive an execution opportunity. Coverage limits are safety floors sized for the complete inventory and may be raised, but runtime configuration must not silently lower the supported scope.

### Required implementation

Apply collection budgets to the live runtime modules before collection, allow enough total time for all concurrency batches, allow each source enough time for its admitted detail pages, and keep card/detail limits aligned with the supported Event budget. The systemd and HTTP timeouts must exceed the complete producer budget.

### Acceptance evidence

Runtime `debug_by_source` must contain all configured sources without unstarted rows caused by queue waiting. Process and runtime evidence must show the effective concurrency, per-source timeout, complete-run timeout, and all source statuses for the exact revision.

## Local Events listing-date authority

### Easy-to-make interpretation

A list card should be rejected unless it already contains a date.

### Why it fails

Correct official Event lists may show only an image, title, category, and detail link. Date and venue may exist only on the detail page.

### Correct requirement interpretation

The official list proves membership. Date and venue can be obtained after admission by following the card’s official detail link.

### Required implementation

Do not require a list-card date. Preserve listing evidence, follow the detail URL, and show exact detail status or errors.

### Acceptance evidence

A date-less list card with one official detail link must be admitted and enriched from its detail page.

## Local Events cards without an independent detail page

### Easy-to-make interpretation

Every valid activity must have a separate detail URL.

### Why it fails

Some official lists, including activity cards that expose location, date, time, and description directly, do not provide an independent detail page.

### Correct requirement interpretation

A complete official list card can itself be the authoritative activity record. The official list URL is the public URL for that activity.

### Required implementation

Admit complete listing-only cards, preserve distinct card identity when several activities share one list URL, and do not open a nonexistent detail page.

### Acceptance evidence

Multiple distinct cards sharing one official listing URL must remain separate in review state, final JSON, and the Surface card.

## Local Events manual correct-list-page entry

### Easy-to-make interpretation

The operator can only accept or reject system-discovered URLs, or a correct URL must be added by editing committed configuration.

### Why it fails

Automated discovery can return the wrong page, and some institutions expose a shared or non-obvious entry point.

### Correct requirement interpretation

The Studio lets the operator select one institution, add one allowed official list URL to review state, and use the normal preview and decision flow.

### Required implementation

Validate `source_id`, absolute HTTP/HTTPS URL, and configured allowed domains. Save as `pending`; do not modify committed source configuration or collect automatically.

### Acceptance evidence

A valid URL appears immediately and can be previewed and decided. Invalid institution, malformed URL, and disallowed domain return HTTP `400` without changing state.

## Local Events positive Event intent

### Easy-to-make interpretation

A title plus dates, explicit `Event` type, event-looking route, or absence of blacklist terms proves activity intent.

### Why it fails

Facilities, memberships, promotions, and navigation records can be Event-shaped or typed as Events.

### Correct requirement interpretation

Positive Event intent means membership in the correct official activity list. Structured data and detail pages cannot independently create output rows.

### Required implementation

Require rendered official list evidence and match enrichment back to that card.

### Acceptance evidence

Reject unmatched typed Event objects and accept matched enrichment without adding title blacklists.

## Local Events operator decisions and final output ownership

### Easy-to-make interpretation

Operator-confirmed Events can replace the producer output, or the producer can later overwrite confirmed Events. Another incorrect interpretation is to run confirmed candidates through crawler admission rules again.

### Why it fails

Those designs create competing writers for `local_event_search_results.json`. They can remove correct automatically collected activities, remove confirmed activities on the next scheduled run, or reject an explicit operator decision because a detail field is missing.

### Correct requirement interpretation

The producer owns automatically collected rows. Review decisions are an immediate overlay on that producer result. Both sets form one final runtime. A confirmation is authoritative for activity membership and is not subjected to a second crawler-admission pass.

### Required implementation

The producer normalizes its new system rows, applies partial-result protection, overlays all current `confirmed` review candidates, and atomically writes the primary runtime. The Event decision endpoint applies the same overlay immediately to the existing primary runtime. Reject or reset removes only rows published from review state; unrelated producer rows remain unchanged. Listing-only confirmed Events use their official list URL and may retain blank unavailable fields.

### Acceptance evidence

Tests and runtime evidence must prove: producer rows survive confirmation and rejection; confirmed rows survive later complete and partial producer runs; duplicate system/review Events are not doubled; two listing-only cards sharing one URL remain separate; and the Surface count matches final JSON after both decision and scheduled collection flows.

## Local Events zero-result diagnostics

### Easy-to-make interpretation

A zero count can be displayed as “no Events returned” without explaining the failed extraction stage.

### Why it fails

The operator cannot distinguish a load failure from card-boundary, route, selector, detail-page, date, or budget failure.

### Correct requirement interpretation

Every attempted list page produces diagnostics tied to the exact canonical URL and reports the first failed stage.

### Required implementation

Persist and display page access, visible links, allowed-domain links, possible detail links, extracted and admitted cards, DOM evidence, selectors, candidates, detail results, and stable reason codes.

### Acceptance evidence

A zero-result collection shows a stable reason code, reason text, stage counts, and sample links when available.

## Local Events HTTP/2 handling

### Easy-to-make interpretation

The collector should first try normal Chromium HTTP/2 navigation and retry after `ERR_HTTP2_PROTOCOL_ERROR`.

### Why it fails

That doubles navigation behaviour, complicates diagnostics, and still begins with the known failing protocol.

### Correct requirement interpretation

Supported collection entry points disable HTTP/2 before Chromium launches. There is no HTTP/2-first request or protocol retry loop.

### Required implementation

Apply `surface/local_events_runtime/http1_browser.py` for Studio and scheduled or HTTP-triggered collection. Every patched Chromium launch includes `--disable-http2`.

### Acceptance evidence

Runtime launch evidence shows the flag on both paths, and navigation failure is reported directly rather than hidden behind a retry.

## Generated helper and archive boundary

### Easy-to-make interpretation

A browser interaction requirement can be solved by generating a ZIP and asking the operator to install an unpacked extension.

### Why it fails

That adds an unrequested deliverable and installation workflow and changes the product boundary.

### Correct requirement interpretation

Do not generate helper archives or extension installation flows unless explicitly requested.

### Required implementation

Keep removed helper, ZIP, extension, and remote transport paths absent. Unimplemented abilities must be labelled honestly.

### Acceptance evidence

Repository search and rendered Studio contain no active helper download, extension source, ZIP builder, or remote helper route.

## Local Events evidence and partial-result protection

### Easy-to-make interpretation

A total count is enough to diagnose coverage, and every producer run may replace the primary file.

### Why it fails

Failure can occur at many stages. Re-normalizing a previous runtime can also remove unrelated correct rows. A partial run can erase valid producer or review Events.

### Correct requirement interpretation

New producer rows are normalized once. Previously verified rows retained for partial protection are copied without re-admission. Partial evidence is kept separately, while the primary runtime continues to contain protected producer rows plus current confirmed review rows.

### Required implementation

Record per-source evidence, calculate source completion, atomically write the partial payload, protect verified primary rows when the incomplete run would reduce coverage, and apply the same review overlay in complete and partial paths.

### Acceptance evidence

Tests and runtime evidence cover complete-to-partial transitions, exact preservation of unrelated rows, retained diagnostics, and current review decisions.

## Validation boundaries

### Easy-to-make interpretation

Static review or a fixture test proves live sources, Chromium flags, services, LAN access, and visible UI all work.

### Why it fails

Offline checks cannot prove current reachability, live DOM/API structure, process arguments, service deployment, or browser behaviour.

### Correct requirement interpretation

Static inspection, offline tests, live producer runs, service execution, and visible UI acceptance are separate evidence levels.

### Required implementation

Tie each claim to the exact revision and actual command, test, log, runtime file, process argument, screenshot, or interaction.

### Acceptance evidence

A final acceptance record states the exact revision, checks run, checks not run, remaining gaps, and a verdict no stronger than the evidence.
