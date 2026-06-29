# InfoScreen design

This document describes how InfoScreen is designed and how the current implementation should satisfy the dashboard requirements.

## Goals

InfoScreen is a local Surface/Ubuntu kiosk dashboard.

The dashboard should show:

- local time and date
- market data
- weather data
- event/news stream
- photo wall
- calendar/schedule board
- local event card with location search
- sync/runtime status

The project should run locally, be debuggable through files and systemd, and avoid hidden fallbacks that make runtime behavior hard to reason about.

## Non-goals

- Do not run large local VLM/LLM models by default.
- Do not embed Qwen, OCR, or transformer models in the default Python path.
- Do not depend on third-party aggregators for official local events.
- Do not use guessed institution domains or guessed `/events` paths as source truth.
- Do not keep multiple frontend state machines controlling the same local event widget.

## Repository layout

```text
surface/
  serve_infoscreen.py              # local HTTP server
  search_local_events.py           # local event refresh entrypoint
  fetch_live_data.py               # market refresh entrypoint
  fetch_event_stream.py            # event/news stream refresh entrypoint
  local_events_runtime/            # rendered DOM extraction runtime
  local_events_adapters/           # older adapter experiment; not the main path
  local_events_engine.py           # old generic crawler; not the main path
  conf/
    official_source_registry.json  # official homepage/domain registry only
    event_sources.json             # verified event listing entrypoints
    market_config.default.json
  web/
    index.html
    calendar_board.js
  .env/                            # runtime generated files, not committed

docs/
  api-spec.md
  design.md
  questions.md
```

## Runtime data model

All generated runtime files live under:

```text
surface/.env/
```

Important files:

```text
surface/.env/schedule.json
surface/.env/weather.json
surface/.env/market.json
surface/.env/market_config.json
surface/.env/event_stream.json
surface/.env/local_event_search_results.json
surface/.env/photos.json
surface/.env/public_photos/
surface/.env/local_event_debug_cards/
```

The server must not read root-level runtime JSON. Root fallback hides errors and causes stale data confusion.

## HTTP server design

`surface/serve_infoscreen.py` is a small local HTTP server using Python standard library `ThreadingHTTPServer`.

Responsibilities:

- serve static files from `surface/web/`
- serve runtime JSON from `surface/.env/`
- handle POST APIs for refresh/update actions
- disable browser caching with `Cache-Control: no-store`
- expose `/api/local-events/search` for local-event read/search
- strip the legacy inline local-event script from served HTML

The served dashboard root is sanitized at response time so the browser executes only the external local-event renderer in `calendar_board.js`.

## Frontend design

The browser should have one owner per UI panel.

### Calendar board

Owned by the first module in:

```text
surface/web/calendar_board.js
```

It reads:

```text
schedule.json
```

and renders a split-flap style schedule board.

### Local event card

Owned by the second module in:

```text
surface/web/calendar_board.js
```

It reads:

```text
/api/local-events/search
```

and renders one local event card at a time with previous/next paging.

Only this external module should bind these controls:

```text
localEventPrevButton
localEventNextButton
localEventLocationButton
localEventSearchButton
localEventCancelButton
localEventLocationInput
```

The old inline local-event script in `index.html` must not execute in the browser. It grouped results into a separate `localEventItems` state and caused the UI to collapse into the old `3/3` pager state after clicking next/previous.

## Local event source design

There are two separate source files with different responsibilities.

### `official_source_registry.json`

Purpose:

- identify official institution homepages
- list allowed official domains
- record source identity only

It must not store:

- event listing URLs
- event detail URLs
- ticketing URLs
- third-party aggregators

### `event_sources.json`

Purpose:

- hold verified event listing entrypoints
- map each source to an extraction strategy
- keep listing URLs out of the official homepage registry

Example source fields:

```json
{
  "id": "nationalmuseum",
  "name": "National Museum Singapore",
  "adapter": "nhb",
  "official_home": "https://www.nationalmuseum.nhb.gov.sg/",
  "allowed_domains": ["nationalmuseum.nhb.gov.sg"],
  "default_venue": "National Museum Singapore",
  "listing_urls": ["https://www.nationalmuseum.nhb.gov.sg/whats-on/exhibition"]
}
```

## Local event extraction design

Current main path:

```text
surface/search_local_events.py
  -> surface/local_events_runtime.collect_events
  -> surface/local_events_runtime.browser.render_listing_cards
  -> surface/local_events_runtime.extract.event_from_card
  -> surface/.env/local_event_search_results.json
```

Extractor version expected after this work:

```text
rendered-dom-card-v41
```

### Why rendered DOM

Some pages are not useful through raw `requests.get()` because:

- important cards are rendered by client-side JavaScript
- HTML text around links can be incomplete
- listing cards may contain images, alt text, hidden structure, or layout-dependent grouping

The current default implementation uses Playwright only as a browser control layer:

- load listing page
- wait for rendering
- inspect visible DOM anchors
- find nearest useful card container
- collect heading, link text, visible text, image alt text, URL, and bounding box
- save debug screenshots
- use Python schema/date validation to produce events

It does not use local VLM/OCR by default.

### Browser runtime handling

On Ubuntu versions unsupported by Playwright bundled Chromium, the runtime should use a system browser.

`surface/local_events_runtime/browser.py` checks for:

```text
INFOSCREEN_CHROMIUM_PATH
PLAYWRIGHT_CHROMIUM_EXECUTABLE
chromium
chromium-browser
google-chrome
google-chrome-stable
microsoft-edge
brave-browser
/usr/bin/chromium
/usr/bin/google-chrome
/snap/bin/chromium
```

If no browser is available, the extractor must report the missing browser explicitly. It must not silently fall back to fake data.

## Local event schema design

Each extracted event should contain:

```text
title       display title
when        exact date/date-range substring only
where       venue phrase or source fallback
host        organizer/source display name
source_name official source display name
url         official HTTP/HTTPS detail URL
summary     short readable description
start_date  YYYY-MM-DD if parseable
kind        event
source_type rendered_dom_card
```

`when` must not be the whole card text. It should only be the date/date-range substring.

`where` should prefer venue text after the date range when available, for example:

```text
B1 Exhibition Galleries
```

`summary` should remove repeated title/date/venue text where possible.

## Timers and refresh design

The old local event systemd timer was identified as:

```text
infoscreen-local-events.timer
```

It triggered:

```text
infoscreen-local-events.service
```

which ran:

```text
/usr/bin/python3 %h/infoscreen/surface/search_local_events.py Punggol Singapore
```

During debugging, this caused manual output to appear as if it was being rolled back.

The timer should remain disabled until the extractor output is verified.

Future timer design should be explicit:

- service should be `Type=oneshot`
- service should have `WorkingDirectory=%h/infoscreen`
- timer should control refresh cadence
- no service should be installed directly as `WantedBy=default.target` for this job

## Debugging and verification

### Verify local event runtime

```bash
python3 surface/search_local_events.py "Punggol Singapore"
python3 - <<'PY'
import json
d=json.load(open('surface/.env/local_event_search_results.json'))
print(d.get('extractor'))
print(d.get('runtime'))
print(d.get('count'))
for x in d.get('results', [])[:5]:
    print(x.get('title'), '|', x.get('when'), '|', x.get('where'))
PY
```

### Verify timer is stopped

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
systemctl --user list-units --all | grep -i infoscreen || true
```

### Verify served frontend is clean

```bash
curl -s http://127.0.0.1:8765/ | grep -n "local-event-inline-script" || true
curl -s http://127.0.0.1:8765/calendar_board.js | grep -n "MutationObserver\|watchdog\|external-local-events" || true
```

Expected:

- no legacy inline script in served HTML
- no watchdog/MutationObserver owner hack in external JS
- local event paging remains on the full result count and does not switch to old `3/3`

## Implementation principles

- Prefer explicit failure over hidden fallback.
- Runtime output should include enough metadata to identify writer process, cwd, Python path, and git head.
- Listing pages are primary sources; listing page URLs themselves are not event items.
- Detail pages can supplement but should not override more accurate listing-card structure blindly.
- No large model should be imported in the default path.
- Debug artifacts such as card screenshots belong under `surface/.env/`.

## Known current limitation

The old inline local-event script has not yet been physically removed from `surface/web/index.html`. It is stripped from served HTML by `surface/serve_infoscreen.py`.

Physical deletion from the source HTML should be done later with a careful full-file edit, because `index.html` is currently large and contains multiple unrelated inline dashboard modules.
