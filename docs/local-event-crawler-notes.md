# Local Event Crawler: Extraction Requirements and Failure Notes

This document records the crawler failures found during the local event card work. It exists to prevent future changes from treating parser failures as source/data failures.

## Scope

The local event crawler has two separate jobs:

1. **Source discovery / registration**
   - Find and store confirmed official institution homepages only.
   - Example: `https://www.acm.nhb.gov.sg/` for Asian Civilisations Museum.
   - This stage must not store event listing URLs, event detail URLs, ticketing sites, tourism pages, blogs, or third-party aggregators.

2. **Event extraction from confirmed official sources**
   - Use confirmed official sources to discover official same-domain event/detail URLs.
   - Fetch detail pages.
   - Extract the primary event fields from the primary page content block.

These jobs must not be mixed.

## Core finding

The crawler already discovered many correct official URLs. The failures were caused by extraction, not by bad sources.

Bad conclusion:

```text
parser did not extract date => source/data is invalid
```

Correct conclusion:

```text
parser did not extract date => parser failed to locate fields
```

A correct official URL plus a fetched page is not enough. The crawler must prove that title/date/time/venue/summary belong to the same primary event block.

## Non-negotiable rules

1. Do not solve parser failures by hiding output, lowering output count, or claiming that the source has no valid data.
2. Do not use generic blacklists as the main event classifier.
3. Do not scan the full page for arbitrary dates and attach those dates to the page title.
4. Do not mix related programme dates, previous/next cards, recommended content, footer/nav text, or listing-card dates into a detail page's primary event fields.
5. Do not display fake fallback fields such as `Check official page` as if they were extracted event data.
6. Do not treat `missing extracted date` as `missing date in source`; it is a parser error unless proven otherwise by inspecting the page structure.
7. Do not change source registry or front-end display limits to compensate for bad extraction.

## Known bad examples

### ACM: `lets-play-2025`

URL:

```text
https://www.acm.nhb.gov.sg/whats-on/exhibitions/lets-play-2025
```

Expected primary event fields from the official detail page:

```text
Title: Let's Play! The Art and Design of Asian Games
Date: 5 Sep 2025–7 Jun 2026
Time: Daily - 10am–7pm / Fridays - 10am–9pm
Venue: Asian Civilisations Museum
```

Observed bad output:

```text
31 January Programmes / 30 May–28 June 2026 / 1 Oct / 3 Dec / +3 more
```

Reason this is wrong:

- Those dates come from lower-page programme/related sections.
- They are not the exhibition's primary metadata.
- The parser scanned the whole page instead of isolating the primary event detail block.

### ACM: `double-celebration-at-gbtb-acm`

URL:

```text
https://www.acm.nhb.gov.sg/whats-on/programmes/2025/campaigns/double-celebration-at-gbtb-acm
```

Problem:

- The URL path contains `2025/campaigns` and represents a historical campaign/programme page.
- The crawler must inspect the page's actual primary date fields before deciding whether it is current or expired.
- A 2025 path alone is not enough to decide, but parsed primary dates must drive expiry.

### ACM historical exhibition incorrectly rolled into future

Observed bad output in earlier results:

```text
Title: Life in Edo | Russel Wong in Kyoto
When: 16 April to 17 October 2021
Start date: 2027-04-16
```

Reason this is wrong:

- `2021` is explicit.
- A parser must never roll explicit past years into a future year.
- Date range parsing must preserve the explicit year at the end of the range.

### National Museum duplicate URL aliases

Observed duplicate pattern:

```text
/whats-on/exhibition/once-upon-a-tide
/exhibition/once-upon-a-tide
```

Requirement:

- Canonicalize aliases by source domain + event slug.
- Do not output the same event twice.

## Correct extraction principle

Do not use this rule:

```text
URL looks like an event page + page contains any date = event date
```

Use this rule:

```text
The same primary content block contains:
- primary title
- primary date
- primary time or venue
- official same-domain URL
```

Only then can the crawler treat the fields as belonging to the same event.

## Correct crawler architecture

```text
confirmed official source
  -> sitemap / official listing discovery
  -> candidate detail URL
  -> fetch official same-domain page
  -> parse structured data
  -> parse embedded JSON / hydration data
  -> locate primary DOM content block
  -> extract title/date/time/venue/summary from that block
  -> classify as current/expired only after date extraction
  -> canonical dedupe
  -> output card
```

## Common crawler techniques that should be used

### 1. URL discovery

Use these only to discover candidates:

- `sitemap.xml`
- `robots.txt` sitemap references
- official listing pages
- same-domain internal links

Do not treat discovered URL alone as event proof.

### 2. Structured data first

Try these before DOM heuristics:

- JSON-LD `schema.org/Event`
- embedded CMS JSON
- React/Next/Nuxt hydration data
- AEM data blobs where available

Extract:

```text
name/headline
startDate
endDate
location.name
location.address
description
url
```

### 3. DOM primary block extraction

When structured data is missing or incomplete:

- Parse HTML as DOM, not as one flattened text string.
- Locate `main`, `article`, or the container around `h1`.
- Find the metadata rows near the title.
- Use icon/label/sibling relationships:
  - calendar/date row
  - clock/time row
  - pin/location row

### 4. Boundary control

Exclude from primary field extraction:

- related programmes
- recommended cards
- previous programme
- next programme
- listing cards
- nav/footer/header
- ticketing widgets unless they contain primary date metadata
- legal/terms/copyright blocks

This is not a blacklist classifier; it is content-boundary separation.

### 5. Site template extractors

A generic regex-only extractor is not enough. Each official source family should have a template extractor.

Recommended template extractors:

```text
NHB ACM extractor
NHB National Museum extractor
Mandai extractor
```

Each extractor should define:

```text
source family
sample URLs
primary title selector
primary metadata container selector
primary date selector
primary time selector
primary venue selector
summary selector
ignored containers
canonical URL rule
```

## Required extractor table

Before adding or changing parser code, complete this table for each source.

### Asian Civilisations Museum

Sample URL:

```text
https://www.acm.nhb.gov.sg/whats-on/exhibitions/lets-play-2025
```

Required notes:

```text
primary title selector:
primary metadata container selector:
primary date selector:
primary time selector:
primary venue selector:
summary selector:
ignored containers:
canonical URL rule:
```

### National Museum Singapore

Sample URL:

```text
https://www.nationalmuseum.nhb.gov.sg/whats-on/exhibition/once-upon-a-tide
```

Required notes:

```text
primary title selector:
primary metadata container selector:
primary date selector:
primary time selector:
primary venue selector:
summary selector:
ignored containers:
canonical URL rule:
```

### Mandai Wildlife Group

Sample URL:

```text
https://www.mandai.com/en/discover-mandai/events/night-safari/meet-our-pango-pup.html
```

Required notes:

```text
primary title selector:
primary metadata container selector:
primary date selector:
primary time selector:
primary venue selector:
summary selector:
ignored containers:
canonical URL rule:
```

## Debugging requirements

Debug output must distinguish parser failure from source invalidity.

Use categories like:

```text
candidate_fetched
structured_event_found
primary_block_found
primary_title_found
primary_date_found
primary_time_found
primary_venue_found
parser_error:title_not_found
parser_error:date_not_found
parser_error:primary_block_not_found
expired_event
canonical_duplicate
```

Do not use vague categories like:

```text
not_confirmed_current_event
invalid_source
source_has_no_data
```

Those hide parser errors.

## Acceptance tests

Add tests before further crawler changes.

### ACM `lets-play-2025`

Must produce:

```text
URL: https://www.acm.nhb.gov.sg/whats-on/exhibitions/lets-play-2025
Date: 5 Sep 2025–7 Jun 2026
Venue: Asian Civilisations Museum
```

Must not produce:

```text
31 January Programmes / 30 May–28 June 2026 / 1 Oct / 3 Dec / +3 more
```

### ACM historical date range

Input date:

```text
16 April to 17 October 2021
```

Must not become:

```text
2027-04-16
```

### National Museum duplicate aliases

These should resolve to one card:

```text
/whats-on/exhibition/once-upon-a-tide
/exhibition/once-upon-a-tide
```

### Missing extracted date

If a page appears to be a valid official detail page but no date is extracted:

```text
result: parser_error:date_not_found
```

Not:

```text
source invalid
source has no data
```

## Development workflow

Before changing code:

1. Pick one known correct URL.
2. Save raw HTML locally for inspection.
3. Identify actual selector/path for title/date/time/venue.
4. Add a fixture or test expectation.
5. Implement only the extractor needed for that template.
6. Run the fixture test.
7. Run the full crawler.
8. Compare extracted fields with official page fields.

Do not iterate by changing filters and checking whether the total count looks better.

## Product display rule

The frontend should display only fields actually extracted from the official page. It should not invent placeholders such as:

```text
WHEN Check official page
```

If data is incomplete, the debug/developer output should show parser diagnostics. The user-facing card should not pretend that a missing field was successfully parsed.
