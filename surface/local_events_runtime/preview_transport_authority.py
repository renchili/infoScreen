from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview
from . import resilient_navigation_authority as _navigation

_APPLIED = False
_BASE_COLLECT = None
_LAST_PREVIEW_DIAGNOSTIC: dict[str, str] = {}
_NETLOG_EVENT_TOKENS = (
    "HTTP2",
    "SPDY",
    "HTTP_TRANSACTION",
    "URL_REQUEST",
    "SSL",
    "SOCKET",
)
_NETLOG_PARAM_KEYS = (
    "net_error",
    "error",
    "error_code",
    "description",
    "stream_id",
    "protocol",
    "url",
    "status",
)


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _snap_name(executable: str) -> str:
    path = Path(str(executable or ""))
    parts = path.parts
    if len(parts) >= 4 and parts[:3] == ("/", "snap", "bin"):
        return parts[3]
    if len(parts) >= 3 and parts[:2] == ("/", "snap"):
        return parts[2]
    return ""


def _new_netlog_path(executable: str) -> Path:
    configured = str(os.environ.get("INFOSCREEN_PREVIEW_NETLOG_DIR") or "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        snap_name = _snap_name(executable)
        if snap_name:
            # Strictly confined snaps have a private /tmp mount. A NetLog written to
            # /tmp by Snap Chromium is therefore invisible to the host Python process.
            # The snap's user-common directory is writable by Chromium and visible to
            # the host service after the browser process exits.
            root = Path.home() / "snap" / snap_name / "common" / "infoscreen-netlog"
        else:
            root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root / (
        f"infoscreen-preview-netlog-{os.getpid()}-{uuid.uuid4().hex[:12]}.json"
    )


def _browser_version(browser: Any) -> str:
    value = getattr(browser, "version", "")
    if callable(value):
        try:
            value = value()
        except Exception:
            value = ""
    return str(value or "")


def _filtered_netlog_events(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    constants = payload.get("constants")
    event_types = constants.get("logEventTypes") if isinstance(constants, dict) else {}
    type_names: dict[int, str] = {}
    if isinstance(event_types, dict):
        for name, raw_value in event_types.items():
            try:
                type_names[int(raw_value)] = str(name)
            except (TypeError, ValueError):
                continue

    output: list[dict[str, Any]] = []
    events = payload.get("events")
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        raw_type = event.get("type")
        try:
            type_name = type_names.get(int(raw_type), str(raw_type or ""))
        except (TypeError, ValueError):
            type_name = str(raw_type or "")
        if not any(token in type_name for token in _NETLOG_EVENT_TOKENS):
            continue
        raw_params = event.get("params")
        params = (
            {
                key: raw_params[key]
                for key in _NETLOG_PARAM_KEYS
                if isinstance(raw_params, dict) and key in raw_params
            }
            if isinstance(raw_params, dict)
            else {}
        )
        if not params and "HTTP2" not in type_name and "SPDY" not in type_name:
            continue
        output.append(
            {
                "time": event.get("time"),
                "phase": event.get("phase"),
                "type": type_name,
                "source": event.get("source"),
                "params": params,
            }
        )
    return output[-80:]


def _write_netlog_summary(diagnostic: dict[str, str]) -> str:
    raw_path = str(diagnostic.get("netlog") or "").strip()
    if not raw_path:
        return ""
    netlog_path = Path(raw_path)
    summary_path = netlog_path.with_suffix(".summary.json")
    summary: dict[str, Any] = {
        "browser_executable": diagnostic.get("browser_executable") or "",
        "browser_version": diagnostic.get("browser_version") or "",
        "netlog": str(netlog_path),
        "events": [],
    }
    try:
        payload = json.loads(netlog_path.read_text(encoding="utf-8"))
        summary["events"] = _filtered_netlog_events(payload)
    except Exception as exc:
        summary["summary_error"] = f"{type(exc).__name__}: {exc}"[:500]
    try:
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return str(summary_path)
    except Exception:
        return ""


def _launch_preview_chromium(playwright: Any):
    """Launch HTTP/2-capable Preview Chromium with readable-DOM recovery and NetLog."""

    global _LAST_PREVIEW_DIAGNOSTIC
    _navigation.apply()
    executable = _browser.find_browser_executable()
    netlog_path = _new_netlog_path(executable)
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        f"--log-net-log={netlog_path}",
        "--net-log-capture-mode=Default",
    ]
    _LAST_PREVIEW_DIAGNOSTIC = {
        "browser_executable": executable or "playwright-bundled-chromium",
        "browser_version": "",
        "netlog": str(netlog_path),
    }
    try:
        browser = (
            playwright.chromium.launch(
                headless=True,
                executable_path=executable,
                args=args,
            )
            if executable
            else playwright.chromium.launch(headless=True, args=args)
        )
    except Exception as exc:
        raise _browser.MissingPlaywright(
            "preview_chromium_launch_failed: "
            f"executable={_LAST_PREVIEW_DIAGNOSTIC['browser_executable']}; "
            f"netlog={netlog_path}; original_error={exc}"
        ) from exc
    _LAST_PREVIEW_DIAGNOSTIC["browser_version"] = _browser_version(browser)
    return browser


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    global _LAST_PREVIEW_DIAGNOSTIC
    if not _preview_store(store):
        return _BASE_COLLECT(store)

    _LAST_PREVIEW_DIAGNOSTIC = {}
    original_launch = _browser.launch_chromium
    _browser.launch_chromium = _launch_preview_chromium
    try:
        return _BASE_COLLECT(store)
    except Exception as exc:
        diagnostic = dict(_LAST_PREVIEW_DIAGNOSTIC)
        summary_path = _write_netlog_summary(diagnostic)
        details = [
            str(exc),
            f"preview_browser={diagnostic.get('browser_executable') or 'unknown'}",
            f"preview_browser_version={diagnostic.get('browser_version') or 'unknown'}",
            f"preview_netlog={diagnostic.get('netlog') or 'unavailable'}",
        ]
        if summary_path:
            details.append(f"preview_netlog_summary={summary_path}")
        raise RuntimeError(" | ".join(details)) from exc
    finally:
        _browser.launch_chromium = original_launch


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _diagnostics.collect_event_candidates = collect_event_candidates
        return

    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = [
    "apply",
    "collect_event_candidates",
    "_filtered_netlog_events",
    "_new_netlog_path",
    "_write_netlog_summary",
]
