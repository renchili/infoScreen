from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import preview_transport_authority as _transport

_APPLIED = False
_HOOKED = False
_BASE_TRANSPORT_APPLY = None


class PreviewBrowserLease:
    """Delegate to one browser while deferring close to the Preview request owner."""

    def __init__(self, browser: Any):
        self._browser = browser

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    def close(self) -> None:
        return None


def launch_preview_chromium(playwright: Any):
    """Launch the deployed Preview browser with the repository HTTP/1 policy."""

    _transport._navigation.apply()
    executable = _browser.find_browser_executable()
    netlog_path = _transport._new_netlog_path(executable)
    mode = "headless" if _transport._PREVIEW_HEADLESS else "headed"
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-http2",
        f"--log-net-log={netlog_path}",
        "--net-log-capture-mode=Default",
    ]
    if not _transport._PREVIEW_HEADLESS:
        args.append("--start-minimized")

    _transport._LAST_PREVIEW_DIAGNOSTIC = {
        "browser_executable": executable or "playwright-bundled-chromium",
        "browser_version": "",
        "browser_mode": mode,
        "browser_reuse": "single_process_per_preview_request",
        "netlog": str(netlog_path),
    }
    try:
        browser = (
            playwright.chromium.launch(
                headless=_transport._PREVIEW_HEADLESS,
                executable_path=executable,
                args=args,
            )
            if executable
            else playwright.chromium.launch(
                headless=_transport._PREVIEW_HEADLESS,
                args=args,
            )
        )
    except Exception as exc:
        raise _browser.MissingPlaywright(
            "preview_chromium_launch_failed: "
            f"executable={_transport._LAST_PREVIEW_DIAGNOSTIC['browser_executable']}; "
            f"mode={mode}; netlog={netlog_path}; original_error={exc}"
        ) from exc
    _transport._LAST_PREVIEW_DIAGNOSTIC["browser_version"] = (
        _transport._browser_version(browser)
    )
    return browser


def _normalise_transport_metadata(state: _review.ReviewState) -> _review.ReviewState:
    metadata = dict(state.event_collection)
    isolated_contexts = int(
        metadata.pop("preview_detail_isolated_browser_count", 0) or 0
    )
    metadata["preview_browser_process_count"] = 1
    metadata["preview_browser_reuse"] = "listing_and_details"
    metadata["preview_detail_transport"] = "single_http1_browser_process"
    if isolated_contexts:
        metadata["preview_detail_isolated_context_count"] = isolated_contexts
    state.event_collection = metadata
    return state


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    """Run the complete Preview pipeline through one browser process."""

    if not _transport._preview_store(store):
        return _transport._BASE_COLLECT(store)

    original_launch = _browser.launch_chromium
    original_headless = _transport._PREVIEW_HEADLESS
    _transport._LAST_PREVIEW_DIAGNOSTIC = {}
    _transport._PREVIEW_HEADLESS = not _transport._requires_headed_preview(store)
    if (
        not _transport._PREVIEW_HEADLESS
        and not _transport._graphical_session_available()
    ):
        _transport._PREVIEW_HEADLESS = original_headless
        raise RuntimeError(
            "MBS preview requires the existing Surface graphical session because the "
            "deployed Snap Chromium is reset by the server in headless mode; DISPLAY "
            "and WAYLAND_DISPLAY are both missing from infoscreen-http.service"
        )

    actual_browser: Any | None = None
    lease: PreviewBrowserLease | None = None

    def launch_once(playwright: Any) -> PreviewBrowserLease:
        nonlocal actual_browser, lease
        if lease is None:
            actual_browser = launch_preview_chromium(playwright)
            lease = PreviewBrowserLease(actual_browser)
        return lease

    _browser.launch_chromium = launch_once
    try:
        state = _transport._BASE_COLLECT(store)
        state = _normalise_transport_metadata(state)
        return store.save(state)
    except Exception as exc:
        diagnostic = dict(_transport._LAST_PREVIEW_DIAGNOSTIC)
        summary_path = _transport._write_netlog_summary(diagnostic)
        details = [
            str(exc),
            f"preview_browser={diagnostic.get('browser_executable') or 'unknown'}",
            f"preview_browser_version={diagnostic.get('browser_version') or 'unknown'}",
            f"preview_browser_mode={diagnostic.get('browser_mode') or 'unknown'}",
            f"preview_browser_reuse={diagnostic.get('browser_reuse') or 'unknown'}",
            f"preview_netlog={diagnostic.get('netlog') or 'unavailable'}",
        ]
        if summary_path:
            details.append(f"preview_netlog_summary={summary_path}")
        raise RuntimeError(" | ".join(details)) from exc
    finally:
        _browser.launch_chromium = original_launch
        _transport._PREVIEW_HEADLESS = original_headless
        if actual_browser is not None:
            try:
                actual_browser.close()
            except Exception:
                pass


def apply() -> None:
    """Replace the existing Preview transport at its diagnostics export point."""

    global _APPLIED
    _transport._launch_preview_chromium = launch_preview_chromium
    _transport.collect_event_candidates = collect_event_candidates
    _transport._diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


def install_transport_apply_hook() -> None:
    """Apply only after the established Preview pipeline has composed its base chain."""

    global _HOOKED, _BASE_TRANSPORT_APPLY
    if _HOOKED:
        return
    _BASE_TRANSPORT_APPLY = _transport.apply

    def apply_transport_with_single_session() -> None:
        _BASE_TRANSPORT_APPLY()
        apply()

    _transport.apply = apply_transport_with_single_session
    _HOOKED = True
    if _transport._APPLIED:
        apply()


__all__ = [
    "PreviewBrowserLease",
    "apply",
    "collect_event_candidates",
    "install_transport_apply_hook",
    "launch_preview_chromium",
]
