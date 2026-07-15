# InfoScreen operator runbook

InfoScreen is a local-first kiosk dashboard for an always-on Surface or Ubuntu display. The Surface runs the HTTP server and background data jobs. A Mac supplies Calendar data through macOS EventKit. Runtime and personal data stay under `surface/.env/` and are not committed.

This file is the operator manual: deploy, start, update, configure refresh behavior, inspect runtime state, and recover failed components. Architecture and implementation rationale live in `docs/design.md`; discussion-derived decisions live in `docs/questions.md`; HTTP contracts live in `docs/api-spec.md`.

## 1. Supported topology

```text
Mac, optional but required for Calendar
  macOS Calendar/EventKit
  -> LaunchAgent
  -> schedule.json over SSH/SCP

Surface or Ubuntu device
  systemd --user services and timers
  -> runtime JSON under surface/.env/
  -> surface/serve_infoscreen.py on 127.0.0.1:8765
  -> Chromium kiosk page
```

Repository root:

```text
~/infoscreen
```

Runtime root:

```text
~/infoscreen/surface/.env
```

## 2. First-time deployment on the Surface

Install the runtime packages used by the current implementation:

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium
python3 -m pip install --user playwright
```

`surface/local_events_runtime/browser.py` uses an installed Chromium-compatible browser. Set `INFOSCREEN_CHROMIUM_PATH` only when browser auto-detection does not find the correct executable.

Install the committed user services and timers:

```bash
cd ~/infoscreen
bash deploy/scripts/install-user-systemd.sh
```

This is the supported Surface installation entrypoint. It:

- creates `surface/.env/`;
- copies `deploy/systemd/user/*.service` and `*.timer` to `~/.config/systemd/user/`;
- enables and starts `infoscreen-http.service`;
- enables the live-data, news, and local-event timers;
- starts one immediate refresh for those producers.

Open the dashboard:

```text
http://127.0.0.1:8765/
```

## 3. Verify the deployment

Run the built-in operator status script:

```bash
cd ~/infoscreen
bash scripts/infoscreen_status.sh
```

It reports:

- HTTP service status;
- enabled timers and unit files;
- recent producer logs;
- runtime JSON existence, size, modification time, and age;
- local HTTP and runtime endpoint checks;
- a short preview of each runtime file.

Minimum manual checks:

```bash
systemctl --user --no-pager status infoscreen-http.service
systemctl --user list-timers --all | grep infoscreen
curl -fsSI http://127.0.0.1:8765/
curl -fsS http://127.0.0.1:8765/market.json | python3 -m json.tool | head -n 40
curl -fsS http://127.0.0.1:8765/api/local-events/search | python3 -m json.tool | head -n 80
```

Expected user units:

```text
infoscreen-http.service
infoscreen-live-data.service
infoscreen-live-data.timer
infoscreen-event-stream.service
infoscreen-event-stream.timer
infoscreen-local-events.service
infoscreen-local-events.timer
```

## 4. Update an existing deployment

Pull the current branch and reinstall the committed unit files:

```bash
cd ~/infoscreen
git pull --ff-only
bash deploy/scripts/install-user-systemd.sh
```

Rerunning the installer is required after unit-file changes because the active copies live under `~/.config/systemd/user/`.

For frontend-only changes, reload the kiosk page after pulling. For backend or route changes, restart the HTTP service:

```bash
systemctl --user restart infoscreen-http.service
```

## 5. Producer refresh and configuration map

The producer schedule determines when runtime JSON is regenerated. Changing browser polling does not change producer frequency.

| Product data | Producer trigger | Default frequency | Producer | Runtime output | Data source | Configuration point |
| --- | --- | --- | --- | --- | --- | --- |
| Market and weather | `infoscreen-live-data.timer` | 5 minutes | `surface/fetch_live_data.py` | `market.json`, `weather.json` | Nasdaq, CNBC, Stooq, Yahoo fallback; Open-Meteo | Timer: `deploy/systemd/user/infoscreen-live-data.timer`; symbols: UI or `market_config.json`; weather coordinates currently in `fetch_live_data.py` |
| Multilingual news | `infoscreen-event-stream.timer` | 5 minutes | `surface/fetch_event_stream.py` | `event_stream.json` | Google News RSS, CNA, France24, RFI, BBC Chinese, Google Translate | Timer unit; feed list and `ITEM_COUNT` in `fetch_event_stream.py` |
| Local events | `infoscreen-local-events.timer` | 6 hours | `surface/search_local_events.py` → `surface/jobs/local_event_search.py` | `local_event_search_results.json`; partial results may go to `.partial.json` | Source-specific official listing/detail pages | Timer unit; source inventory/adapters in `surface/conf/event_sources.json`; crawl budgets at the top of `surface/jobs/local_event_search.py` |
| Calendar | Mac LaunchAgent | 120 seconds by default | `mac/export.py` + `mac/sync_schedule.sh` | `schedule.json` on the Surface | macOS Calendar/EventKit | `mac/scripts/setup-schedule-sync.sh --interval`; SSH target in `mac/local.env` |
| Photos | Manual builder | No systemd timer in the supported deployment | `surface/build_photos_json.py` | `photos.json`, `public_photos/` | Files in `surface/.env/photos/` | Add/remove local files, then rerun the builder |
| HTTP/API | `infoscreen-http.service` | Continuous | `surface/serve_infoscreen.py` | Serves page, JSON, photos, and local APIs | Runtime files and committed frontend | Service unit and `INFOSCREEN_ENV_DIR` when running an isolated environment |

To change a Surface timer interval, edit the corresponding committed timer under `deploy/systemd/user/`, then rerun:

```bash
bash deploy/scripts/install-user-systemd.sh
```

Do not edit only the copy under `~/.config/systemd/user/`; the next install would overwrite it.

## 6. Browser reload and visual rotation

Browser behavior is separate from producer refresh:

| UI area | Browser data reload | Visual rotation |
| --- | --- | --- |
| Market card and tape | Page load and every 60 seconds; immediately after Market UI refresh | Tape animation is CSS/DOM based |
| Weather | Page load and every 5 minutes | None |
| News | Page load and every 5 minutes | Continuous ticker animation |
| Sync status | Page load and `HEAD` every 60 seconds | Continuous ticker animation |
| Local events | Page load and immediately after an on-demand location search | One accepted event every 15 seconds; previous/next buttons change immediately |
| Calendar | Page load only | Visible event group changes every 7 seconds |
| Photos | Page load and every 5 minutes | Photo changes every 9 seconds |
| Clock and page uptime | Every second | None |
| Demo CPU/MEM/DSK/NET | Every 6 seconds | Values are simulated, not Surface monitoring |

Operational consequence: a background Local Events or Calendar producer may update its runtime file while the page still shows the previously loaded data. Reload the kiosk page to consume the new file. Market, Weather, News, Sync status, and Photos already re-read their runtime data periodically.

## 7. User interactions and persistent configuration

### Market symbols and manual refresh

The gear button next to the Market panel is owned by `market_custom.js`.

- `SAVE` sends `POST /api/market-config`, writes `surface/.env/market_config.json`, then triggers a Market refresh.
- `REFRESH` sends `POST /api/market-refresh`, which runs `surface/fetch_live_data.py` and refreshes both Market and Weather runtime files.
- At most 12 unique symbols are kept.
- Browser `localStorage` is only a fallback for displaying the last symbol list when the API cannot be read; the server runtime file is the active producer configuration.

Default symbols are defined in:

```text
surface/conf/market_config.default.json
```

### Local-event location search

The search control in the Local Event panel opens a location input.

- The browser stores the last location in `localStorage` as `local_events_location`.
- Submitting sends `POST /api/local-events/search` with the location.
- The HTTP server runs `surface/search_local_events.py` synchronously and returns the resulting runtime payload.
- The configured official source set does not change when the location changes; the location is an input to the source-specific collector.
- The page provides previous/next controls and otherwise advances every 15 seconds.

### Calendar

There is no Surface-side calendar account or Calendar UI configuration. Calendar selection and permissions belong to macOS Calendar/EventKit on the Mac. Configure only the Mac-to-Surface sync target and interval.

### Photos

Place user files under:

```text
surface/.env/photos/
```

Then rebuild:

```bash
cd ~/infoscreen
python3 surface/build_photos_json.py
```

The browser never scans the filesystem directly; it reads `photos.json` and `/public_photos/*`.

## 8. Local Events operation and source-specific collection

Local Events is not a generic search-engine scraper. It is a maintained set of official source entrypoints and adapter choices in:

```text
surface/conf/event_sources.json
```

The current source set includes official museum, library, community, attraction, shopping-centre, venue, and institution sites. Each entry defines:

- stable source ID and display name;
- adapter type;
- official home page;
- allowed domains;
- default venue;
- one or more official listing URLs.

The two current adapter modes are:

- `rendered_dom_card`: extract event candidates from the rendered official listing and structured payloads;
- `nhb`: use the same structured-first flow and additionally open eligible detail pages when listing cards do not contain a complete date. The adapter name is historical and is used by non-NHB sources where detail enrichment is required.

The collector also contains targeted handling developed for real source behavior, including:

- structured JSON extraction before DOM fallback;
- positive event-intent validation so dated facilities or membership records are not treated as events;
- detail-page date enrichment for sources whose listing cards omit full dates;
- Gardens by the Bay date-range and venue repair;
- rejection of synthetic Mandai location cards;
- configured source ordering and per-source debug evidence;
- preservation of the previous complete runtime result when a new run is partial and would replace it with fewer events.

Manual refresh:

```bash
cd ~/infoscreen
python3 surface/search_local_events.py "Punggol Singapore"
```

Run the installed unit instead:

```bash
systemctl --user start infoscreen-local-events.service
```

Inspect results and evidence:

```bash
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
journalctl --user -u infoscreen-local-events.service -n 200 --no-pager
find surface/.env/local_event_debug_cards -maxdepth 2 -type f | sort | tail -n 100
```

Important fields:

- `results`: accepted events shown by the UI;
- `sources`: configured source order and source summary;
- `debug_by_source`: per-source page access, card counts, accepted counts, and rejection reasons;
- `partial`: whether the run covered fewer sources than configured;
- `write_policy`: whether the previous complete result was preserved.

## 9. Mac Calendar setup and recovery

Run on the Mac:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user <surface-ssh-user> \
  --remote-path '~/infoscreen/surface/.env/schedule.json' \
  --interval 120
```

Optional `--python` selects a Python runtime that can `import EventKit`.

The setup script writes local-only configuration to:

```text
mac/local.env
```

It installs:

```text
~/Library/LaunchAgents/com.renchili.infoscreen.schedule-sync.plist
```

Trigger immediately:

```bash
launchctl kickstart -k gui/$(id -u)/com.renchili.infoscreen.schedule-sync
```

Inspect:

```bash
launchctl print gui/$(id -u)/com.renchili.infoscreen.schedule-sync
ls -l ~/Library/Logs/infoscreen-sync/
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.out.log
tail -n 100 ~/Library/Logs/infoscreen-sync/launchd.err.log
```

The supported remote path is:

```text
~/infoscreen/surface/.env/schedule.json
```

The Surface does not generate Calendar data.

## 10. Runtime files and HTTP paths

| Runtime path | HTTP path | Writer |
| --- | --- | --- |
| `surface/.env/schedule.json` | `/schedule.json` | Mac schedule sync |
| `surface/.env/weather.json` | `/weather.json` | `fetch_live_data.py` |
| `surface/.env/market.json` | `/market.json` | `fetch_live_data.py` |
| `surface/.env/market_config.json` | `/market_config.json`, `/api/market-config` | Market config API |
| `surface/.env/event_stream.json` | `/event_stream.json` | `fetch_event_stream.py` |
| `surface/.env/local_event_search_results.json` | `/local_event_search_results.json`, `/api/local-events/search` | Local-event job |
| `surface/.env/photos.json` | `/photos.json` | Photo builder |
| `surface/.env/public_photos/` | `/public_photos/*` | Photo builder |

The server sends `Last-Modified` for runtime files. The left sync ticker uses that header; it does not parse producer-specific `updated_at` fields.

## 11. Troubleshooting by symptom

### The page does not open

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
systemctl --user restart infoscreen-http.service
curl -v http://127.0.0.1:8765/
```

### Market or Weather is stale or missing

Both are written by the same producer:

```bash
systemctl --user status infoscreen-live-data.timer infoscreen-live-data.service --no-pager -l
journalctl --user -u infoscreen-live-data.service -n 200 --no-pager
systemctl --user start infoscreen-live-data.service
python3 -m json.tool surface/.env/market.json | head -n 80
python3 -m json.tool surface/.env/weather.json | head -n 80
```

A Market item with `provider: stale-cache` means all live providers failed for that symbol and the previous usable item was retained. `session: ERR` and `price: N/A` means no provider and no usable previous item succeeded.

### News is stale or empty

```bash
systemctl --user status infoscreen-event-stream.timer infoscreen-event-stream.service --no-pager -l
journalctl --user -u infoscreen-event-stream.service -n 200 --no-pager
systemctl --user start infoscreen-event-stream.service
python3 -m json.tool surface/.env/event_stream.json | less
```

Inspect `errors` for feed or translation failures. A failed EN/FR/ZH triple is skipped rather than emitting misaligned rows.

### Local Events is empty, stale, partial, or contains a bad record

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
python3 -m json.tool surface/.env/local_event_search_results.json | less
python3 -m json.tool surface/.env/local_event_search_results.partial.json | less
```

Then inspect `debug_by_source` for the affected organisation before changing extraction logic. Determine whether the failure is page access, pagination/load-more, structured payload extraction, listing-card extraction, detail-page enrichment, date parsing, event-intent rejection, or the total runtime budget. Data-quality fixes belong in the collector/extractor, not in frontend title hiding.

When Playwright or Chromium is missing, the service log contains `missing_playwright_python_package` or `missing_system_chromium`.

### Schedule is stale, missing, or shows old data

The producer is on the Mac, not the Surface. Check the Mac LaunchAgent, `mac/local.env`, Mac logs, SSH reachability, and the exact remote target. On the Surface:

```bash
ls -l surface/.env/schedule.json
curl -fsSI http://127.0.0.1:8765/schedule.json
```

The Calendar UI reads `schedule.json` on page load. Reload the kiosk page after confirming the file changed.

### Photos are empty

```bash
find surface/.env/photos -maxdepth 1 -type f -print
python3 surface/build_photos_json.py
python3 -m json.tool surface/.env/photos.json | less
curl -fsSI http://127.0.0.1:8765/photos.json
```

### Sync `AGE` is unexpectedly large

The ticker compares the browser clock with the Surface file `Last-Modified` value. Check:

- producer service or Mac LaunchAgent;
- runtime file modification time;
- HTTP `Last-Modified`;
- browser and Surface system clocks;
- Mac system clock for `SCHEDULE`.

`ERR` means the browser's `HEAD` request failed and does not by itself prove that the producer failed.

## 12. Manual producer commands

```bash
cd ~/infoscreen
python3 surface/fetch_live_data.py
python3 surface/fetch_event_stream.py
python3 surface/search_local_events.py "Punggol Singapore"
python3 surface/build_photos_json.py
```

## 13. Validation

Install test dependencies:

```bash
python3 -m pip install --user pytest pydantic
```

Run the repository suite:

```bash
cd ~/infoscreen
python3 -m pytest
bash scripts/run_full_ci_tests.sh
```

The full runner uses fixture runtime data and writes logs, JUnit XML, generated OpenAPI, and a summary under:

```text
${ACCEPTANCE_ARTIFACT_DIR:-/tmp/infoscreen-acceptance}
```

It does not write fixture data into the real `surface/.env/`.

## 14. Documentation ownership

```text
README.md          operator deployment, configuration, refresh, and recovery
docs/design.md     architecture, data flow, frontend ownership, and source-specific implementation
docs/api-spec.md   HTTP methods, callers, payloads, side effects, and runtime mapping
docs/questions.md  discussion-derived decision records and the reasons behind the current design
AGENT.md            repository rules
AGENTS.md           required agent read order
```
