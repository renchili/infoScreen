# InfoScreen

## What this is

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. It combines the current day, personal schedule, weather, market movement, multilingual news, nearby official events, local photos, and runtime freshness in one stable kiosk page.

The project favours readable typography, compact information density, predictable layout, local ownership of personal data, and visible failure states.

## What this is not

InfoScreen is not a cloud dashboard, a general web-search scraper, a second Calendar account, or real Surface system monitoring. Local Events come from curated official organisation pages. Calendar authority remains on a Mac running macOS Calendar/EventKit. The current CPU/MEM/DSK/NET bars are simulated browser values, and POWER/DISPLAY/NETWORK labels are static text.

Runtime JSON, machine-local configuration, logs, debug captures, and personal photos are device state under `surface/.env/`; they are not repository source files or generated artifacts to commit.

## First 10 minutes

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

Open:

```text
http://127.0.0.1:8765/
```

Open API documentation:

```text
http://127.0.0.1:8765/docs
```

## Prerequisites

For the smallest local path:

- Python 3;
- a browser or `curl`;
- a checkout at `~/infoscreen` when following the supported deployment scripts.

For the full Surface deployment:

- a Linux user session with `systemd --user`;
- Chromium and the Python Playwright package for system-collected Local Events;
- Pydantic 2;
- outbound network access for Market, Weather, News, and official Local Event sources;
- `ffmpeg` for HEIC/HEIF conversion;
- ImageMagick `magick` for PNG/WebP-to-JPEG normalization;
- a Mac with an EventKit-capable Python runtime only when Calendar sync is required.

Without ImageMagick, existing JPEG files can still be copied safely, but PNG and WebP inputs are skipped rather than renamed to a false `.jpg` format.

## Runtime and configuration

Runtime and personal data belong under:

```text
~/infoscreen/surface/.env/
```

Committed configuration includes:

```text
surface/conf/market_config.default.json
surface/conf/event_sources.json
```

The process-local lifetime of the latest exact Local Event Preview candidate manifest can be changed with:

```text
INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS
```

The default is 21,600 seconds and the minimum accepted value is 60 seconds. This manifest is memory state, not a JSON file, and disappears when the HTTP service restarts.

Do not commit runtime JSON, logs, debug captures, personal photos, SSH details, or machine-local environment files.

## Product areas

The dashboard includes:

- current time, date, page refresh time, and page-session uptime;
- a Market card and global Market tape with configurable symbols;
- current Singapore weather with a visible retained-data error state when live retrieval fails;
- aligned English, French, and Chinese news rows, with Singapore sources selected before the random remainder;
- a Local Events card built from curated official organisation sources;
- a Calendar board supplied by macOS Calendar/EventKit;
- a local Photo wall;
- a Sync ticker showing whether Schedule, Weather, Market, and News runtime files are fresh, stale, missing, or unreachable;
- local OpenAPI documentation;
- a Local Event operator page for list-page review, Event review, manual correct-list-page entry, and diagnostics.

## Runtime model

```text
Mac, required only for Calendar
  macOS Calendar/EventKit
  -> LaunchAgent
  -> schedule.json over SSH/SCP

Surface or Ubuntu device
  systemd --user services and timers
  -> producer jobs
  -> runtime JSON under surface/.env/
  -> surface/serve_infoscreen.py on port 8765
  -> kiosk browser
  -> optional operator browser on another trusted LAN device
```

## Data sources and ownership

| Product area | Producer or trigger | Runtime/API | Browser owner |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` or Market refresh | `market.json`, `weather.json` | `dashboard.js` |
| Multilingual News | `infoscreen-event-stream.timer` | `event_stream.json` | `local_event_card.js` |
| Local Events | `infoscreen-local-events.timer` or explicit collection API | `local_event_search_results.json`, `/api/local-events/search` | `local_event_card.js` |
| Local Event review | Operator actions | `/api/local-events/review/*`, `local_event_review/state.json`, `local_event_review/preview_event_selections.json`, process-local latest Preview manifest | Local Event Studio scripts |
| Calendar | Mac LaunchAgent | `schedule.json` | `calendar_board.js` |
| Photos | Manual photo builder | `photos.json`, `/public_photos/*` | `local_event_card.js` |
| Sync status | Browser `HEAD` checks | Runtime endpoints | `local_event_card.js` |

Each visible DOM mount has one renderer owner. Producers write runtime data; browser scripts render it; the HTTP server serves files and local APIs.

## Market symbols

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, and refreshes Market data.
- `REFRESH` sends `POST /api/market-refresh`.
- A Market refresh runs `surface/fetch_live_data.py`, so it refreshes both Market and Weather.
- At most 12 unique symbols are stored.

## Local-event dashboard filter

- The kiosk card reads the current results with `GET /api/local-events/search`; opening or applying its filter does not run a collection.
- The institution dropdown is built from the institutions present in the current event rows and includes `ALL INSTITUTIONS`.
- The text field filters title, institution/source, date/time, venue/place, and description. Multiple typed terms must all match the same event.
- The selected institution and text are stored in browser `localStorage` as `local_events_filter_source` and `local_events_filter_query`.
- Pressing `FILTER` only filters the already-loaded rows in browser memory. It does not send `POST /api/local-events/search`, launch Chromium, or rewrite runtime JSON.
- Periodic GET reloads keep the current filter applied to newly loaded results.

`POST /api/local-events/search` remains an explicit producer trigger for direct operator/API use; it is not the kiosk filter action.

## Local Event Studio

The operator page uses the existing HTTP service and port:

```text
http://127.0.0.1:8765/local-events/studio/
```

From another computer on the same trusted LAN:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

Update and restart the canonical branch:

```bash
cd ~/infoscreen
git fetch origin
git switch main
git pull --ff-only origin main
systemctl --user restart infoscreen-http.service
```

### Review system-collected list pages and Events

1. Select the global institution used to filter the visible Review cards.
2. Click `COLLECT LIST PAGES`. A previously discovered non-manual page that is no longer found is retired together with its committed Preview selection. A manually added page is preserved.
3. Inspect a candidate URL. A pending card exposes `PREVIEW BEFORE CONFIRM`; confirmed and rejected cards expose `PREVIEW EVENTS`.
4. Preview the page and classify every returned candidate as `REAL EVENT` or `NOT EVENT`. Preview works before or after a saved List Page decision and does not mutate persisted Review files by itself.
5. When every candidate is classified, confirm the List Page with its REAL EVENT selections, or reject the List Page when no candidate is a real Event. The complete selection set and List Page decision are committed by the same request only when the submitted candidate identities and original/final URLs exactly match the latest unexpired server Preview manifest.
6. After confirmation, use the page-level `COLLECT … SELECTED REAL EVENT(S)` action or the global `COLLECT EVENTS FROM CONFIRMED PAGES` action. Formal collection admits only committed REAL EVENT selections from confirmed pages and excludes unselected candidates before detail navigation.
7. Review each persisted Event and choose `RELATED ACTIVITY`, `NOT RELATED`, or `RESET`.

Preview and normal collection are separate operations. `POST /api/local-events/review/preview-events` copies Review state into an isolated temporary store, keeps only the selected page, marks only that temporary copy confirmed, clears copied Events and feedback, then uses the direct Preview collector to open the selected listing and all admitted official detail pages in one Playwright manager, one Chromium process, and one browser context. It preserves original list-card identity across redirects, closes the real browser once, and records the exact final candidate set in a process-local manifest. It does not call the list-decision API, modify persisted review files, rebuild the kiosk projection, or alter other page decisions.

A successful Preview reports `preview_browser_process_count: 1`, `preview_browser_reuse: listing_and_details`, `preview_detail_context_count: 1`, and `preview_detail_transport: same_browser_context`. If listing-only evidence remains after the direct collector, Preview fails instead of starting a second browser or issuing a manifest from incomplete detail results.

The Studio keeps the temporary panel and draft choices in `sessionStorage`. Browser-restored panel HTML and choices are drafts only; they are not candidate-set authority. A service restart, manifest expiry, newer Preview, List Page state change, reset, rejection, manual re-add, or discovery retirement invalidates the server manifest. Saving a stale draft then fails with guidance to run Preview again.

A Preview review is encoded in the existing `preview-review-v1:` `candidate_id` envelope sent to `POST /api/local-events/review/listing-decision`. Each row carries the original list-card `candidate_id`, the original `listing_detail_url`, the final redirected/public `detail_url`, and the operator decision. The backend validates the allow-list and stable identity, then compares the complete submitted set with the latest eligible manifest before persisting it.

The committed selection state is stored at:

```text
surface/.env/local_event_review/preview_event_selections.json
```

The latest exact Preview manifest is not stored in this file. It remains in the HTTP process for the configured TTL and is invalidated after a successful decision write.

The selection file is atomically replaced before the List Page state write. If that state write raises, the previous selection file is restored or the newly created file is removed, and the current manifest remains available for retry. This is exception rollback inside one request; it is not a cross-file transaction that can guarantee recovery from an abrupt process crash between the two writes.

Normal `POST /api/local-events/review/collect-events` reads confirmed pages with committed REAL EVENT selections. It filters the original list-card links before opening detail pages, then retains only results matching the selected candidate identity, original link, or final redirected/public URL. A listing card needs a usable title and one official detail link. The list card itself does not need to repeat date or venue. The collector follows admitted detail pages for title, date/time, location, summary, and detail status.

Every Event candidate shows its originating list URL, DOM selector, selector match number, listing page index, document position, detail URL, and detail result.

### Add a correct Event list page manually

The manual input is directly below the top collection toolbar.

1. Select exactly one value in `Global institution`.
2. Paste the correct official Event list URL into `Add an official Event list page to the selected global institution`.
3. Click `ADD LIST PAGE`.
4. The page is saved as `pending` and appears in the left-side Event list pages. Re-adding the same URL clears its old committed Preview selection and process-local manifest.
5. Use `PREVIEW BEFORE CONFIRM` and classify every candidate as `REAL EVENT` or `NOT EVENT`.
6. Confirm the page with at least one committed REAL EVENT selection, or reject it when no candidate is a real Event.
7. Formal collection includes only that page’s committed REAL EVENT selections while the page remains confirmed.

The backend validates that:

- the institution exists in `surface/conf/event_sources.json`;
- the URL is absolute HTTP/HTTPS;
- the hostname is within that institution’s `allowed_domains`.

Manual addition does not modify committed `event_sources.json` and does not collect Events automatically. Adding the same URL again resets it to `pending` for re-review and requires a fresh Preview. If the Review-state write fails after the old selection was removed, the previous selection file is restored. Isolated preview remains available in `pending`, `confirmed`, and `rejected` states; normal persisted collection requires both a confirmed page and a committed REAL EVENT selection.

### Zero-result diagnostics

A zero result must show the exact failed recognition stage rather than only `0 EVENT`. Diagnostics include page access, visible links, official-domain links, possible detail links, extracted cards, admitted cards, DOM evidence, selector generation, candidates, and detail-page status.

### HTTP/2 handling

Formal discovery and collection do not first try HTTP/2 and then retry. Their supported entrypoints apply:

```text
surface/local_events_runtime/http1_browser.py
```

before collector imports, and Chromium on those paths includes:

```text
--disable-http2
```

This applies to:

- Studio list-page discovery and confirmed-page formal Event collection through `surface/serve_infoscreen.py`;
- scheduled and HTTP-triggered Local Events through `surface/search_local_events.py`.

Isolated Preview is a separate path. `preview_direct_detail_collector_authority.py` uses one Chromium process and context for listing and detail reads. `preview_transport_authority.py` may run Marina Bay Sands Preview in headed mode and records NetLog diagnostics, but it does not force HTTP/1 or otherwise alter Chromium protocol negotiation.

### Interactive browser feedback status

The downloadable Chrome Helper, ZIP generator, unpacked extension files, and remote helper transport were removed. The Studio marks Ability 2 as `NOT IMPLEMENTED`; no download or generated archive is required or produced.

Review state is stored under:

```text
surface/.env/local_event_review/state.json
surface/.env/local_event_review/preview_event_selections.json
```

The latest exact Preview manifest is process-local and therefore has no third file path.

## Local Events collection policy

The maintained institution inventory is:

```text
surface/conf/event_sources.json
```

Collection behaviour includes:

- rendering and expanding configured official lists;
- admitting isolated list cards with one official detail URL and a usable title;
- allowing listing cards without dates;
- following admitted detail pages for required date/time, location, title, summary, and public URL;
- using XHR/fetch JSON and embedded structured state only to enrich a matched list card;
- discarding unmatched structured records;
- avoiding title and URL blacklists as the primary decision mechanism;
- preserving configured source order;
- recording per-source and per-listing evidence;
- preserving previous verified rows when a partial run would replace them with fewer results.

Primary output:

```text
surface/.env/local_event_search_results.json
```

Incomplete diagnostic output:

```text
surface/.env/local_event_search_results.partial.json
```

Debug evidence:

```text
surface/.env/local_event_debug_cards/
```

## Refresh behaviour

| Data | Scheduler | Default frequency |
| --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes |
| News | `infoscreen-event-stream.timer` | 5 minutes |
| Local Events | `infoscreen-local-events.timer` | 6 hours |
| Calendar | Mac LaunchAgent | 120 seconds |
| Photos | Manual builder | No timer |

The Local Event Studio loads on initial entry, explicit operations, manual `RELOAD`, and return to the browser tab. It does not register an idle polling interval. Full-card rendering emits one completion event, and the scroll guard restores the previous card anchor or scroll position after that completed render.

## Project structure

```text
surface/serve_infoscreen.py                         local HTTP server and APIs
surface/fetch_live_data.py                          Market and Weather producer
surface/fetch_event_stream.py                       multilingual News producer
surface/search_local_events.py                      supported Local Events wrapper
surface/jobs/local_event_search.py                  Local Events job
surface/local_events_runtime/                       collector, review, diagnostics, browser policy
surface/conf/                                       committed defaults and institution inventory
surface/web/                                        kiosk and operator frontend
surface/.env/                                       local runtime and personal data
mac/                                                EventKit export and schedule push
deploy/systemd/user/                                Surface user units
scripts/                                            status and acceptance scripts
docs/                                               architecture, API, requirement clarifications
tests/                                              unit and contract tests
```

## Deployment

Install dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium imagemagick ffmpeg
python3 -m pip install --user playwright pydantic
```

Install or update user services:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

The installer never deletes conflicting legacy runtime directories. When both the legacy root path and `surface/.env/` destination exist, it preserves the legacy path under `surface/.env/migration_backup/` and stops rather than overwriting an existing backup.

When dependencies and unit files are already installed:

```bash
systemctl --user restart infoscreen-http.service
```

Restarting `infoscreen-http.service` invalidates all process-local Preview manifests. Any Preview panel restored from browser session storage must be collected again before its decisions can be saved.

## Operation and troubleshooting

Check deployment:

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

Check HTTP service:

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
curl -v http://127.0.0.1:8765/
```

Check Local Events:

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

When a Studio preview fails, inspect `event_collection.listing_diagnostics`, `detail_page_errors`, and the Preview browser/NetLog details returned in the error. Persisted Review state remains at:

```text
surface/.env/local_event_review/state.json
surface/.env/local_event_review/preview_event_selections.json
```

When saving reports that the Preview manifest is missing, expired, superseded, or no longer matches the List Page, run `PREVIEW BEFORE CONFIRM` or `PREVIEW EVENTS` again and repeat the candidate classifications. The browser may still show an old panel because that panel is only a session draft.

A failure before DOM parsing should be shown as a page/navigation error. Missing date on the listing card is not a rejection reason.

## Calendar sync

Run on the Mac that owns the Calendar accounts:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user <surface-ssh-user> \
  --remote-path /home/<surface-ssh-user>/infoscreen/surface/.env/schedule.json \
  --interval 120
```

The setup command resolves an EventKit-capable Python and stores the Python path, Surface host, SSH user, remote Schedule path, local JSON name, and log directory directly in the LaunchAgent `ProgramArguments`. These values are not supplied by transient shell environment assignments during unattended runs. Re-run the setup command when any of those values changes.

`--remote-path` accepts either a safe absolute path or a `~/` path relative to the remote SSH user's home directory. `mac/local.env` is supported only as migration input for older installations and is not required by subsequent LaunchAgent executions.

Each successful run exports Calendar data, validates the local JSON, uploads a temporary remote file, renames it atomically to `schedule.json`, and verifies the published JSON. The Calendar board reloads Schedule data independently, so new Calendar content appears in an already-open kiosk page without a full-page refresh.

The Surface does not generate Calendar data.

## Photos

Place files under:

```text
surface/.env/photos/
```

Then rebuild:

```bash
python3 surface/build_photos_json.py
```

The public `photos.json` contains only browser URLs, captions, and output types; it does not expose original absolute filesystem paths. JPEG inputs can be copied safely without ImageMagick. PNG and WebP require ImageMagick, while HEIC and HEIF require `ffmpeg`.

## Development and validation

Install test dependencies:

```bash
python3 -m pip install --user pytest pydantic
```

Repository checks include:

```bash
python3 -m py_compile surface/*.py surface/jobs/*.py surface/local_events_runtime/*.py
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

Run only checks appropriate to the requested task and report exactly what was or was not executed.

## Documentation

```text
README.md          onboarding, capabilities, interaction, deployment, troubleshooting
docs/design.md     architecture, ownership, data flow, implementation boundaries
docs/api-spec.md   HTTP methods, payloads, side effects, runtime mapping
docs/questions.md  requirement clarifications and acceptance evidence
AGENT.md           repository-specific contribution rules
AGENTS.md          required read order and safe boundary
```
