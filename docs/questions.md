# InfoScreen questions, missing inputs, and blockers

This document tracks user-confirmation items, missing inputs, open design questions, and blockers.

## Confirmed decisions

- Runtime files belong under `surface/.env/`, not the repository root.
- `official_source_registry.json` is only for official homepage/domain identity.
- Event listing URLs belong in a separate source config such as `surface/conf/event_sources.json`.
- The old generic crawler should not be the main local-event extractor.
- Default local-event extraction should not embed Qwen, OCR, VLM, or any other large local model.
- Playwright may be used as a browser control layer, but the browser executable should be a system Chromium/Chrome on unsupported distros.
- Local-event frontend rendering should have one state machine only.
- `infoscreen-local-events.timer` should remain disabled while extraction is being debugged.
- API schema should use Pydantic models plus framework-independent OpenAPI generation, not a FastAPI migration.

## Needs user confirmation

### 1. Physical deletion of legacy inline local-event script

Current state:

- `surface/serve_infoscreen.py` strips the legacy inline script from served HTML.
- The legacy script still exists in `surface/web/index.html` source.

Question:

- Should the old `<script id="local-event-inline-script">...</script>` block be physically removed from `surface/web/index.html` now?

Risk:

- `index.html` is a large file with many unrelated inline dashboard modules, so full-file surgery has higher risk than serving-time stripping.

### 2. Local event source scope

Current event sources are mostly museum/Mandai style official sources.

Question:

- Should default `Punggol Singapore` prioritize truly local sources such as One Punggol, NLB/Punggol Regional Library, OnePA/PA, SAFRA Punggol, and community venues?

Missing input:

- Confirm which source families are allowed.
- Confirm whether source freshness or geographic relevance matters more than source count.

### 3. OCR for image-only event cards

Current default:

- No OCR.
- No VLM.
- Card screenshots are saved only for debugging.

Question:

- If a card contains date/title only inside an image, should the project add optional OCR?

Possible approach:

- Add optional OCR backend only when explicitly configured.
- Do not enable OCR by default on Surface.

### 4. Timer refresh cadence

Current state:

- `infoscreen-local-events.timer` was disabled because it overwrote manual debugging output.

Question:

- After extraction is verified, what refresh cadence should be used?

Options:

- manual only
- hourly
- daily
- on login plus daily

Recommendation:

- Use a timer-controlled `oneshot` service only after output is verified.

### 5. Browser dependency target

Current behavior:

- Python Playwright package is required for rendered DOM extraction.
- Browser executable is resolved from system Chromium/Chrome paths.

Question:

- Should install docs standardize on `chromium`, Google Chrome, or an environment variable like `INFOSCREEN_CHROMIUM_PATH`?

Missing input:

- Surface OS/browser package availability.
- Whether Snap Chromium is acceptable.

### 6. Python dependency packaging

Current behavior:

- `/openapi.json` requires `pydantic>=2.0`.
- Rendered DOM extraction requires `playwright` plus a system browser.

Question:

- Should the repo add a committed requirements file, for example `surface/requirements.txt`, or keep install commands in docs only?

Current install commands:

```bash
python3 -m pip install --user 'pydantic>=2.0'
python3 -m pip install --user playwright
```

## Missing inputs

- Exact Surface OS release and package availability for Chromium/Chrome.
- Actual desired local event source list.
- Whether OCR is acceptable as an optional dependency.
- Whether event search should be location-aware beyond simple display sorting.
- Whether frontend should show all official events or only events with local relevance to the requested location.
- Whether debug screenshots under `surface/.env/local_event_debug_cards/` should be automatically cleaned up.
- Whether dependency management should be a root requirements file, `surface/requirements.txt`, `pyproject.toml`, or manual install docs.

## Open technical issues

### 1. Field splitting accuracy

Status:

- v41 improves `when`, `where`, and `summary` splitting.

Open issue:

- Real rendered cards still need review.
- Some card layouts may still mix category/title/date/venue in one DOM text block.

Verification:

```bash
python3 surface/search_local_events.py "Punggol Singapore"
python3 - <<'PY'
import json
d=json.load(open('surface/.env/local_event_search_results.json'))
print(d.get('extractor'))
print(d.get('count'))
for x in d.get('results', [])[:10]:
    print('\nTITLE:', x.get('title'))
    print('WHEN :', x.get('when'))
    print('WHERE:', x.get('where'))
    print('URL  :', x.get('url'))
PY
```

### 2. Mandai extraction

Status:

- Earlier HTML adapter found `cards: 0` for Mandai.

Open issue:

- Need verify rendered DOM extractor output for Mandai.
- If rendered DOM still fails, Mandai may need a source-specific DOM selector or JSON extraction path.

### 3. Old source files still present

Status:

- `surface/local_events_engine.py` and `surface/local_events_adapters/` still exist.
- Main entrypoint no longer uses them.

Open issue:

- Decide whether to remove them after v41 is verified.

Recommendation:

- Keep until rendered DOM path is proven stable.
- Delete only after confirmation.

### 4. Frontend source cleanup

Status:

- Served HTML is clean because server strips the legacy local-event inline script.
- Source HTML still contains the legacy block.

Open issue:

- Physical deletion from `surface/web/index.html` remains pending.

### 5. API timeout

Current timeout:

- `/api/local-events/search` POST timeout is 130 seconds.

Open issue:

- Rendered browser extraction may be slower or faster than the old crawler depending on source pages and browser startup time.

Need confirm:

- Actual runtime on Surface.
- Whether timeout should remain 130 seconds.

### 6. OpenAPI runtime verification

Current state:

- `surface/api_models.py` defines Pydantic schemas.
- `surface/openapi_spec.py` builds OpenAPI 3.1.
- `surface/serve_infoscreen.py` exposes `/openapi.json` and `/docs`.

Open issue:

- Need verify on Surface that Pydantic is installed and `/openapi.json` returns generated spec.

Verification:

```bash
python3 -m pip install --user 'pydantic>=2.0'
python3 surface/openapi_spec.py | python3 -m json.tool | head -n 80
curl -s http://127.0.0.1:8765/openapi.json | python3 -m json.tool | head -n 80
```

## Blockers

### 1. Browser runtime missing

Symptoms:

- local event payload contains `missing_playwright_python_package`
- local event payload contains `missing_system_chromium`
- Playwright bundled Chromium install fails with unsupported distro, such as Ubuntu 26.04

Resolution:

```bash
python3 -m pip install --user playwright
sudo apt install -y chromium
# or install Google Chrome and set:
export INFOSCREEN_CHROMIUM_PATH=/usr/bin/google-chrome
```

Do not run this on unsupported distros as the only browser solution:

```bash
python3 -m playwright install chromium
```

### 2. Pydantic missing

Symptoms:

- `GET /openapi.json` returns `openapi_generation_failed`
- `python3 surface/openapi_spec.py` fails with `No module named 'pydantic'`

Resolution:

```bash
python3 -m pip install --user 'pydantic>=2.0'
```

### 3. Timer overwriting manual output

Symptoms:

- manual run writes expected `extractor`
- later JSON reverts unexpectedly

Known source:

```text
infoscreen-local-events.timer -> infoscreen-local-events.service
```

Resolution:

```bash
systemctl --user stop infoscreen-local-events.timer
systemctl --user disable infoscreen-local-events.timer
systemctl --user stop infoscreen-local-events.service
systemctl --user daemon-reload
```

Verification:

```bash
systemctl --user list-timers --all | grep -i infoscreen || true
```

### 4. Browser cache or old kiosk process

Symptoms:

- served code has changed but UI still behaves like old frontend
- next/previous click still switches to old `3/3` grouping

Resolution:

```bash
systemctl --user restart infoscreen-http.service
pkill -f chromium || true
```

Verification:

```bash
curl -s http://127.0.0.1:8765/ | grep -n "local-event-inline-script" || true
curl -s http://127.0.0.1:8765/calendar_board.js | grep -n "MutationObserver\|watchdog\|external-local-events" || true
```

Expected:

- no legacy inline script in served HTML
- no watchdog/MutationObserver hack in `calendar_board.js`

## Do not claim yet

- Do not claim final extraction accuracy is solved until real v41 output is reviewed.
- Do not claim the legacy inline script is physically deleted from `index.html`; currently it is stripped at serve time.
- Do not claim the timer can be re-enabled until the extractor output is verified.
- Do not claim OCR/VLM support exists; only debug screenshots exist.
- Do not claim Mandai is fixed until rendered DOM output proves it.
- Do not claim OpenAPI is working on Surface until `/openapi.json` is verified after installing Pydantic.
