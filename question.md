# InfoScreen local event cleanup status

## Current decision

Local event extraction and rendering should not rely on the old generic crawler or duplicate frontend state machines.

## Backend/runtime changes

- Runtime JSON is written under `surface/.env/local_event_search_results.json`.
- `surface/search_local_events.py` now uses the rendered DOM extractor path.
- Extractor version expected after the latest backend work: `rendered-dom-card-v41`.
- The rendered DOM extractor uses Playwright as a browser control layer only.
- It does not embed Qwen, OCR, VLM, or any local model by default.
- On unsupported Playwright bundled Chromium distros, `surface/local_events_runtime/browser.py` tries a system browser such as `chromium` or `google-chrome`.
- The event timer that was overwriting manual results was identified as `infoscreen-local-events.timer` triggering `infoscreen-local-events.service`.

## Frontend cleanup

- The served `/` and `/index.html` are sanitized by `surface/serve_infoscreen.py` to strip the legacy `<script id="local-event-inline-script">...</script>` block before sending HTML to the browser.
- `surface/web/calendar_board.js` is now the only active local-event frontend renderer.
- The previous watchdog / MutationObserver / external-owner workaround was removed from `calendar_board.js`.
- Local event paging is owned by one state machine only, so clicking next/previous should not collapse into the old grouped `3/3` state.

## Verification commands

```bash
cd ~/infoscreen
git fetch origin
git reset --hard origin/fix/local-event-one-card
systemctl --user restart infoscreen-http.service
```

Verify served HTML does not contain the legacy inline script:

```bash
curl -s http://127.0.0.1:8765/ | grep -n "local-event-inline-script" || true
```

Verify the only local-event frontend is the external JS:

```bash
curl -s http://127.0.0.1:8765/calendar_board.js | grep -n "MutationObserver\|watchdog\|external-local-events\|localEventItems" || true
```

Verify runtime output:

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

## Still pending

- Confirm on the Surface browser that paging no longer switches to the old `3/3` view.
- Confirm v41 field splitting is accurate enough on real rendered cards.
- If dates are present only inside images, add optional OCR backend later. Do not enable OCR or VLM by default.

## Do not claim yet

- Do not claim final extraction accuracy is solved until real output is checked.
- Do not claim the inline code is deleted from the source file; it is stripped from served HTML by the server.
- Do not re-enable `infoscreen-local-events.timer` until the extractor output is verified.
