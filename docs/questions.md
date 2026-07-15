# InfoScreen implementation rationale and validation limits

This document preserves project context that cannot be understood from code structure alone. It records why selected behaviours exist, what real-world observations led to them, and where automated validation stops.

It is not a conversation transcript, a changelog, or a list of implementation mistakes. The most important purpose of this file is to prevent a future maintainer from simplifying the Local Events collector based only on passing repository tests while ignoring the conditions observed on the real sites and the real display environment.

## TTY style is an information language, not dot-matrix decoration

The requested TTY style refers to monospaced typography, compact spacing, aligned values, concise labels, restrained status colours, and clear panel boundaries.

It does not require a dot-matrix background, pixel grid, noisy CRT texture, or decorative pattern. Those effects were explicitly not required because they compete with the information and reduce readability on an always-on display.

The terminal character of the interface should come from typography, hierarchy, alignment, borders, and state presentation. The background should remain visually quiet.

## Local Events cannot be validated end to end by repository tests

The Local Events feature reads external official websites whose behaviour depends on the live page, network path, JavaScript execution, region, cookies, timing, anti-bot controls, and changes made by the publishing organisation.

The repository test suite does not prove that an official website is currently reachable, that its JavaScript still renders the same content, that its anti-bot behaviour permits collection, or that the current page still exposes the fields expected by the collector.

The development environment used for code changes cannot reproduce every real Surface and live-site condition. For this feature, validation by the project owner on the real network and real display is part of the development process, not an optional final check.

A passing fixture or parser test means only that a known input is handled as expected. It does not mean that a live source currently produces that input.

## Human verification is part of the Local Events development loop

The effective development loop is:

1. run the collector on the real Surface or equivalent real browser/network environment;
2. inspect what is actually displayed and what was written to the runtime JSON;
3. identify the affected official source and exact listing/detail page;
4. inspect `debug_by_source`, captured structured payloads, rendered cards, detail-page evidence, and rejection reasons;
5. describe the real failure precisely, such as a false event, missing date, wrong venue, missing source, partial coverage, or blocked page;
6. change the smallest appropriate source configuration, adapter, extraction rule, or output policy;
7. add an offline regression test or fixture that preserves the observed case;
8. rerun the real collector to confirm that the live behaviour is actually corrected.

The offline regression test is the final protection against reintroducing a known problem. It is not a replacement for step 1 or step 8.

## Why the collector is source-specific

The current collector is not a universal web scraper. The official sources do not expose events through one stable contract.

Observed and implemented source patterns include:

- structured JSON returned through XHR or embedded page state;
- cards that appear only after JavaScript rendering;
- listing cards with incomplete or ambiguous dates;
- useful fields available only on detail pages;
- facilities, memberships, promotions, navigation objects, or operating information mixed with event data;
- source-specific date and venue layouts;
- pages that time out, block automation, or return only partial coverage.

For that reason, `surface/conf/event_sources.json` records the official entrypoints, allowed domains, default venues, source order, and adapter choice for each organisation. The shared collector provides common stages, while source-specific handling exists where real pages require it.

Removing an adapter or targeted rule because a synthetic test still passes can remove live coverage that the test never exercised.

## Why structured data is preferred but not trusted blindly

Structured JSON is preferred because it can contain explicit start/end dates, venue fields, canonical URLs, and descriptions that are more reliable than guessing from rendered text.

Repository tests preserve several useful structured-data behaviours:

- separate `startDate` and `endDate` values become one closed display range;
- a structured record can replace a poorer same-title DOM date guess;
- a structured event bypasses DOM date guessing once it has already supplied canonical dates;
- explicit `@type: Event` is accepted even when the URL is not under the listing route.

However, live structured payloads also contain objects that are not events. Structured form is evidence about data shape, not proof of event meaning. Every structured candidate still requires event intent and normal quality checks before it becomes a runtime event.

## SAFRA Carpark showed why title blacklists are the wrong model

A real Local Events result displayed a SAFRA record with the title `Carpark`, a long range from 2024 to 2029, and the description `Carpark Rates`. The source page exposed enough structured fields for the earlier collector to convert it into an event-shaped record even though it was a facility information page.

The important finding was not that the word `Carpark` should be banned. It was that a title and date range do not establish event meaning.

A blacklist of names such as `carpark`, `gym`, `membership`, or every future facility type cannot be complete and can also reject a genuine event whose description happens to mention one of those words.

The current rule therefore uses positive event intent. An untyped structured record must be connected to the official event listing/detail route, or the structured type must explicitly describe an event, programme, or activity. A dated object outside that event context is not automatically accepted.

`tests/test_official_feeds.py` preserves this distinction with cases for:

- the SAFRA `Carpark` record outside the event route being rejected;
- another untyped membership record with dates being rejected;
- an untyped record inside the official event route being accepted;
- an explicitly typed Event outside that route being accepted.

These tests preserve the logic derived from the observed false positive. They do not prove that SAFRA's current live page still has the same structure or that the source can currently be collected.

## Why listing extraction and detail-page enrichment both exist

Some official listing cards expose enough information to create an event directly. Others omit a complete date, venue, or description and require a detail-page read.

The collector therefore supports both rendered listing-card extraction and a detail-enriched adapter path. Detail pages are opened selectively rather than recursively crawling the entire site, because unrestricted crawling increases runtime, duplicate results, unrelated content, and blocking risk.

The detail-enrichment path should be retained only for sources that need it and must be revalidated against the real source when its page structure changes. A parser test can prove that a stored detail response is interpreted correctly; it cannot prove that the live detail page is still reachable or still contains that response.

## Why per-source debug evidence is part of the product

A result count alone cannot explain why Local Events coverage changed. A source can fail at page access, structured extraction, rendered-card discovery, pagination, detail enrichment, date parsing, event-intent validation, normalization, or the total crawl budget.

The runtime payload therefore includes `debug_by_source`, and optional evidence is written under `surface/.env/local_event_debug_cards/`.

This evidence exists so a maintainer can answer:

- which configured source was reached;
- which listing pages were attempted;
- how many cards or structured candidates were found;
- how many records were accepted;
- why individual candidates were rejected;
- whether the job stopped because of a source timeout or total budget;
- whether a source-specific rule is still matching the live page.

When the project owner reports a bad card or missing organisation, this evidence is the bridge between the visible real-world result and an offline regression fixture.

## Why a partial run does not replace a better complete result

External sources fail independently. A single run can finish with fewer sources and fewer events because one or more pages timed out, blocked automation, changed layout, or exceeded the crawl budget.

Replacing a larger complete runtime result with that smaller partial result would make the always-on display degrade immediately even though the previous data may still be more useful.

`surface/jobs/local_event_search.py` therefore keeps the previous complete primary result when a new run is partial and contains fewer events. The incomplete run is written to `local_event_search_results.partial.json` with `write_policy: kept_previous_complete_result` and its debug evidence.

`tests/test_local_event_output.py` verifies the write policy and text normalization using local data. The test proves the retention algorithm; only a real collection run can show why a particular source became partial.

## Why text normalization happens before runtime delivery

Official pages can return HTML fragments, repeatedly escaped markup, hidden spans, scripts, list elements, and different aliases such as `description`, `summary`, `venue`, and `where`.

The runtime output is normalized before it reaches the API and frontend so every consumer sees the same plain-text event fields. This avoids requiring the browser to interpret source HTML or to implement source-specific cleanup.

`tests/test_local_event_output.py` preserves known normalization cases, including HTML removal, repeated entity decoding, description-to-summary promotion, venue-to-where promotion, and normalization of a retained previous result.

Again, these tests prove the local transformation of a supplied payload. They do not prove that a live official page will supply the expected field.

## Current targeted rules are evidence of observed source differences

The current collector contains targeted behaviour such as Gardens by the Bay date/venue handling and rejection of synthetic Mandai location cards.

These rules should be understood as records of source behaviour encountered during development, not as a claim that those sites will remain unchanged. Before deleting, generalising, or replacing one of these rules, a maintainer must inspect the corresponding live official page and the current `debug_by_source` evidence.

A rule that looks redundant in an isolated unit test may still be required by the real rendered page. Conversely, a rule that once matched may become obsolete when the organisation redesigns its site. Only real-site verification can distinguish those cases.

## What automated tests can prove

Repository tests can prove deterministic behaviour for supplied local inputs, including:

- date-range parsing and formatting;
- structured-versus-DOM preference;
- positive event-intent classification for known URL/type cases;
- text and field normalization;
- partial-result retention policy;
- payload shape and frontend/backend contracts;
- regression cases captured from previously observed failures.

These tests are essential because they prevent a later change from reintroducing a known parsing or policy failure.

## What automated tests cannot prove

Repository tests cannot prove:

- that an official source is reachable today;
- that Playwright is not blocked on the deployment network;
- that the source still renders the same DOM or structured payload;
- that pagination or load-more controls still work;
- that every configured organisation is covered in the latest run;
- that extracted dates and venues are semantically correct on the live page;
- that the collection finishes within the real Surface resource and timing limits;
- that the final visible card is acceptable to the project owner.

A mocked browser, stored fixture, or successful `pytest` run must never be reported as live-source verification.

## Required validation when changing a Local Events source

A source or adapter change is complete only when the evidence states separately:

1. what real page or displayed result triggered the change;
2. what the project owner observed in the real environment;
3. which source configuration or collector path was changed;
4. what offline regression test was added or updated;
5. which local tests were actually run;
6. whether the real source was rerun after the change;
7. whether the Surface UI was inspected after new runtime data was written;
8. what could not be verified because of network, browser, region, session, or anti-bot limitations.

When real-source or Surface validation has not happened, the correct conclusion is that the implementation is only partially verified. Passing repository tests must not be presented as proof that Local Events works end to end.
