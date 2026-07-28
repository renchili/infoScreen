from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview

_APPLIED = False
_BASE_COLLECT = None


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _launch_preview_chromium(playwright: Any):
    """Launch Preview Chromium without forcing HTTP/1.1.

    The shared Local Events browser deliberately adds ``--disable-http2`` for sites
    that previously failed with HTTP/2 protocol errors. Marina Bay Sands is served by
    Akamai over HTTP/2 and can stall before navigation commit when that protocol is
    disabled. Preview therefore uses an isolated browser process with normal ALPN
    negotiation while the formal collector keeps its existing HTTP/1.1 policy.
    """

    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    executable = _browser.find_browser_executable()
    if executable:
        return playwright.chromium.launch(
            headless=True,
            executable_path=executable,
            args=args,
        )
    try:
        return playwright.chromium.launch(headless=True, args=args)
    except Exception as exc:
        raise _browser.MissingPlaywright(
            "missing_system_chromium: Playwright bundled Chromium is unavailable "
            "on this distro. Install a system browser and set "
            "INFOSCREEN_CHROMIUM_PATH if needed. Examples: sudo apt install "
            "chromium; or install Google Chrome and export "
            "INFOSCREEN_CHROMIUM_PATH=/usr/bin/google-chrome. "
            f"Original error: {exc}"
        ) from exc


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    if not _preview_store(store):
        return _BASE_COLLECT(store)

    original_launch = _browser.launch_chromium
    _browser.launch_chromium = _launch_preview_chromium
    try:
        return _BASE_COLLECT(store)
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


__all__ = ["apply", "collect_event_candidates"]
