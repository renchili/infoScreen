# Local Events

The local event crawler uses confirmed official sources only.

## Source registry

`official_source_registry.json` stores official institution homepages and allowed domains. It is not an event listing registry.

Accepted source data:

```text
institution name
official homepage
allowed domains
aliases
confirmed status
```

Rejected source data:

```text
event detail URL
event listing URL
ticketing site
tourism page
blog
social media
third-party aggregator
```

## Extraction flow

```text
official source
  -> same-domain URL discovery
  -> detail page fetch
  -> primary title area
  -> nearby metadata rows
  -> title/date/venue/summary output
```

The extractor must bind fields by page structure. A date found lower on the page is not automatically the date of the current event.

## Primary block rule

A valid event card needs a same-domain detail URL plus a primary content block that contains:

```text
title
date
venue or useful summary
```

Sections such as related cards, programmes, previous/next links, footer, legal text, and navigation are not used as primary event fields.

## Debug reasons

Useful debug reasons include:

```text
parser_error:title_not_found
parser_error:date_not_found
parser_error:generic_title
expired_event
not_detail_page
fetch_error:<type>
```

These categories separate parser failure from source validity.

## Validation

```bash
python3 surface/search_local_events.py --self-test
python3 surface/search_local_events.py "Punggol Singapore"
python3 -m json.tool local_event_search_results.json | head -n 120
```

Expected behavior:

- ACM `lets-play-2025` primary date is `5 Sep 2025–7 Jun 2026`.
- Programme dates below that page must not be merged into the exhibition date.
- `16 April to 17 October 2021` remains a 2021 range.
- National Museum `/whats-on/exhibition/<slug>` and `/exhibition/<slug>` aliases dedupe to one canonical event.
