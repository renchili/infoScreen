# InfoScreen questions

This file records only durable product and architecture decisions that remain valid across implementations.

Installation commands, job schedules, status troubleshooting, test and CI rules, repository layout rules, and one-off defect histories do not belong here. They belong in `README.md`, `docs/design.md`, `AGENT.md`, tests, or code.

## What are InfoScreen's runtime boundaries?

Decision: A Surface or Ubuntu device runs the HTTP service, background data jobs, runtime data, and kiosk page. The browser only consumes the page and APIs; it does not produce data.

Reason: Reloading or restarting the browser, or a frontend failure, must not change how background data is produced. Runtime state must remain inspectable without the browser.

## Where do runtime and personal data live?

Decision: Weather, market, news, local events, schedule data, photo indexes, logs, and other runtime content live under `surface/.env/`. User photo inputs live under `surface/.env/photos/`. None of this content is committed to the source repository.

Reason: These files are device state or personal data, not reusable project source.

## Where does schedule data come from?

Decision: The authoritative schedule source is macOS Calendar/EventKit on the Mac. The Mac exports events and pushes `schedule.json` to the Surface. The Surface only stores, serves, and renders schedule data; it does not generate calendar events.

Reason: Calendar accounts and EventKit permissions exist on the Mac. The Surface must not duplicate or invent another schedule source.

## Which sources are allowed for local events?

Decision: Local events use the official organisation listing and detail pages configured in `surface/conf/event_sources.json`. Search-engine results, unofficial reposts, and aggregator sites are not authoritative event sources.

Reason: Event titles, dates, venues, and links must be verifiable against the publishing organisation, with a clear ownership boundary when a source page changes.

## What counts as a local event?

Decision: A record must have positive event-intent evidence, such as official structured data explicitly declaring an `Event`, or a record located within an official event listing and its detail route. A title, date range, venue, or long validity period alone does not prove that a record is an event.

Do not classify non-events by continuously enumerating facility, membership, parking, or operating-information names. Date fields may represent validity periods, publication dates, or configuration ranges.

Reason: Official pages and JSON commonly mix events with facilities, membership products, navigation data, and long-lived content. The collector must establish why a record is an event instead of adding a new negative keyword after every false positive.

## Which layer owns local-event data quality?

Decision: Invalid links, incorrect titles, incorrect dates, incorrect venues, non-event structured records, and duplicates must be handled in the collection and extraction layer. The frontend only displays accepted backend results and must not hide bad records with title-specific rules.

Reason: The same runtime result is consumed by the API, debugging tools, and other clients. Cleaning before runtime JSON is written keeps all consumers consistent.

## How are local events ordered?

Decision: Group events by the organisation order in `surface/conf/event_sources.json`; preserve extractor order within each organisation.

Reason: Organisation is the most stable browsing context and keeps backend output, API responses, and page rendering in the same order.
