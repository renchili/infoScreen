# InfoScreen

InfoScreen is a local-first information dashboard designed for an always-on Surface or Ubuntu display. It combines personal schedule, weather, market data, multilingual news, nearby official events, local photos, and data freshness in one browser page.

## 1. Project overview

The project has three user-facing pages:

| Page | URL | Purpose |
| --- | --- | --- |
| Dashboard | `http://127.0.0.1:8765/` | Always-on information screen |
| Local Event Studio | `http://127.0.0.1:8765/local-events/studio/` | Review and manage official Local Event sources and results |
| API documentation | `http://127.0.0.1:8765/docs` | Inspect the local HTTP API |

The Surface or Ubuntu device serves the pages and stores runtime JSON. A Mac is only required when macOS Calendar data should appear on the dashboard.

## 2. Start the project

### 2.1 Minimal local start

```bash
git clone https://github.com/renchili/infoScreen.git ~/infoscreen
cd ~/infoscreen
python3 -m pip install --user 'pydantic>=2,<3'
mkdir -p surface/.env
python3 surface/serve_infoscreen.py
```

Open the dashboard:

```text
http://127.0.0.1:8765/
```

The minimal start serves the page and local APIs. Features that depend on scheduled producers, Chromium, Calendar sync, or photo conversion require the full setup below.

### 2.2 Full Surface or Ubuntu setup

Install the runtime dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip curl ca-certificates chromium imagemagick ffmpeg
python3 -m pip install --user 'pydantic>=2,<3' playwright
```

Install or update the Surface user services and timers:

```bash
cd ~/infoscreen
bash surface/deploy/install-user-systemd.sh
```

Check the complete Surface runtime state:

```bash
bash surface/scripts/infoscreen_status.sh
```

### 2.3 Update an existing installation

```bash
cd ~/infoscreen
git fetch origin
git switch main
git pull --ff-only origin main
bash surface/deploy/install-user-systemd.sh
systemctl --user restart infoscreen-http.service
```

## 3. Pages and their relationship

### 3.1 Dashboard

The dashboard is the always-on page. It displays:

- current date, time, page refresh time, and page-session uptime;
- market symbols and price movement;
- current weather and retained-data error state;
- aligned English, French, and Chinese news;
- official nearby Local Events;
- macOS Calendar events;
- local photos;
- freshness status for Schedule, Weather, Market, and News.

The browser reads runtime JSON through the local HTTP server. Each data area refreshes independently; the whole page does not need to reload whenever one JSON file changes.

### 3.2 Local Event Studio

The Studio is the operator page for Local Events. It is separate from the kiosk dashboard and is used to:

- collect candidate official Event list pages;
- add a correct official list page manually;
- preview Event candidates;
- confirm or reject list pages;
- classify Event candidates;
- inspect collection and page diagnostics;
- publish reviewed results back to the dashboard data.

From another trusted computer on the same LAN, open:

```text
http://<surface-lan-address>:8765/local-events/studio/
```

### 3.3 API documentation

The API documentation describes the local routes used by the dashboard and Studio:

```text
http://127.0.0.1:8765/docs
```

## 4. Data and page flow

```text
Market / Weather / News / Local Events producers
  -> runtime JSON under surface/.env/
  -> surface/serve_infoscreen.py
  -> dashboard or Local Event Studio

macOS Calendar / EventKit
  -> Mac Schedule sync
  -> Surface schedule.json
  -> dashboard Calendar area

Local photos
  -> photo builder
  -> photos.json and public photo files
  -> dashboard Photo area
```

The main refresh relationships are:

| Data | Producer or action | Default cadence | Browser behavior |
| --- | --- | --- | --- |
| Market and Weather | `infoscreen-live-data.timer` | 5 minutes | Reloaded without a full-page refresh |
| News | `infoscreen-event-stream.timer` | 5 minutes | Reloaded without a full-page refresh |
| Local Events | `infoscreen-local-events.timer` or Studio/API action | 6 hours by timer | Current results are re-read while active filters remain applied |
| Calendar | Mac LaunchAgent | 120 seconds | `schedule.json` is re-read without a full-page refresh |
| Photos | Manual photo builder | Manual | Updated after rebuilding `photos.json` |

## 5. Feature guide

### 5.1 Market symbols

The Market card supports up to 12 unique symbols.

- `SAVE` stores the selected symbols and refreshes Market data.
- `REFRESH` refreshes Market and Weather data.
- The committed default is `surface/conf/market_config.default.json`.
- The current local selection is stored in `surface/.env/market_config.json`.

### 5.2 Weather

Weather is produced together with Market data. When a live request fails, the page keeps the last successful data visible and shows the failure state instead of silently replacing it with empty content.

### 5.3 News

News is displayed in aligned English, French, and Chinese rows. Singapore sources are selected first, followed by the remaining configured sources.

### 5.4 Local Events on the dashboard

The dashboard reads the current Local Event results and supports local filtering by institution and text.

Filtering only changes the visible rows already loaded by the page. It does not start a new collection or open Chromium.

### 5.5 Local Event review

Use the Local Event Studio when collection sources or Event candidates need review. The dashboard displays the current published result; source discovery, preview, confirmation, rejection, and diagnostics remain in the Studio.

Detailed collection, review-state, and API behavior is documented in:

- `docs/design.md`;
- `docs/api-spec.md`;
- `docs/questions.md`.

### 5.6 Calendar and Schedule sync

The Mac owns Calendar accounts and exports EventKit data to the Surface.

Run once on the Mac to configure recurring sync:

```bash
cd ~/infoscreen
bash mac/scripts/setup-schedule-sync.sh \
  --host <surface-ip-or-hostname> \
  --user <surface-ssh-user> \
  --remote-path /home/<surface-ssh-user>/infoscreen/surface/.env/schedule.json \
  --interval 120
```

The setup command saves the values used by the automatic LaunchAgent runs. Run the setup command again when the Surface host, SSH user, remote path, Python path, or interval changes. Do not rely on a one-off environment-variable prefix for recurring sync.

After a successful sync, the already-open dashboard re-reads `schedule.json`; a forced browser refresh is not required.

### 5.7 Photos

Place source photos under:

```text
surface/.env/photos/
```

Rebuild the browser photo index:

```bash
python3 surface/build_photos_json.py
```

JPEG inputs can be copied directly. PNG and WebP conversion requires ImageMagick, while HEIC and HEIF conversion requires `ffmpeg`.

### 5.8 Sync status

The dashboard shows whether Schedule, Weather, Market, and News data is fresh, stale, missing, or unreachable. This status reflects the runtime files served to the browser; it is separate from the page-session uptime display.

## 6. Configuration and runtime data

Committed configuration:

```text
surface/conf/market_config.default.json
surface/conf/event_sources.json
```

Machine-local runtime and personal data:

```text
surface/.env/
```

Typical runtime files include:

```text
market.json
weather.json
event_stream.json
schedule.json
photos.json
local_event_search_results.json
local_event_search_results.partial.json
local_event_review/state.json
local_event_review/preview_event_selections.json
```

Do not commit runtime JSON, logs, browser captures, personal photos, SSH details, or other machine-local state.

## 7. Common operations

### Restart the HTTP page and API

```bash
systemctl --user restart infoscreen-http.service
```

### Check service and timer state

```bash
bash surface/scripts/infoscreen_status.sh
```

### Inspect HTTP service logs

```bash
systemctl --user status infoscreen-http.service --no-pager -l
journalctl --user -u infoscreen-http.service -n 200 --no-pager
```

### Inspect Local Events producer logs

```bash
systemctl --user status infoscreen-local-events.timer infoscreen-local-events.service --no-pager -l
journalctl --user -u infoscreen-local-events.service -n 300 --no-pager
```

### Inspect current runtime JSON

```bash
python3 -m json.tool surface/.env/market.json
python3 -m json.tool surface/.env/weather.json
python3 -m json.tool surface/.env/schedule.json
python3 -m json.tool surface/.env/local_event_search_results.json
```

## 8. Troubleshooting

### The page does not open

```bash
systemctl --user status infoscreen-http.service --no-pager -l
curl -v http://127.0.0.1:8765/
```

### One dashboard area is stale

Run:

```bash
bash surface/scripts/infoscreen_status.sh
```

Then inspect the matching producer, runtime JSON, and HTTP response. A healthy HTTP server does not guarantee that every producer completed successfully.

### Calendar content is old

Check the Mac Schedule sync result and confirm that the Surface `schedule.json` modification time changes. The Calendar area re-reads the file independently, so a page refresh should not be required after the file is updated.

### Local Events returns no results

Use the Local Event Studio diagnostics. The Studio reports whether the failure occurred during page access, list-page recognition, candidate extraction, detail-page collection, or result publication.

## 9. Project structure

The repository is organized by platform ownership. Surface-specific deployment, operations, and tests stay under `surface/`; Mac Calendar synchronization and its tests stay under `mac/`; CI-only helpers stay under `.github/`.

```text
surface/serve_infoscreen.py        local HTTP server and API routes
surface/fetch_live_data.py         Market and Weather producer
surface/fetch_event_stream.py      multilingual News producer
surface/search_local_events.py     Local Events command entrypoint
surface/jobs/                      producer orchestration
surface/local_events_runtime/      Local Events collection and review logic
surface/conf/                      committed configuration
surface/web/                       dashboard and Studio frontend
surface/deploy/                    Surface installer, user services, and timers
surface/scripts/                   Surface status and operator utilities
surface/tests/                     Surface unit, API, frontend, and contract tests
surface/.env/                      local runtime and personal data
mac/                               macOS Calendar export and Schedule sync
mac/tests/                         Mac Schedule and LaunchAgent tests
.github/scripts/                   CI and repository-validation entrypoints
.github/tests/                     repository-wide contract tests
.github/pytest.ini                 pytest discovery and marker configuration
docs/                              design, API, and requirement documentation
skills/                            reusable repository-work instructions
```

There are no generic root-level `deploy/`, `scripts/`, `tests/`, or `pyproject.toml` owners. A file must live with its Surface, Mac, CI, or genuinely repository-wide owner.

## 10. Development and documentation

Install development dependencies:

```bash
python3 -m pip install --user pytest 'pydantic>=2,<3'
```

Repository validation entrypoints include:

```bash
python3 -m compileall -q surface mac .github/scripts .github/tests
python3 -m pytest -c .github/pytest.ini
bash .github/scripts/run_full_ci_tests.sh
```

Documentation roles:

| File | Content |
| --- | --- |
| `README.md` | Project introduction, startup, pages, feature use, and operations |
| `docs/design.md` | Architecture, ownership, state, and internal data flow |
| `docs/api-spec.md` | HTTP routes, payloads, and side effects |
| `docs/questions.md` | Requirement clarifications and acceptance boundaries |
| `AGENT.md` / `AGENTS.md` | Repository contribution rules |
