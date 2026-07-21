from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection starts in
    HTTP/1.1 mode directly. The same bootstrap installs listing authority and
    the review diagnostic collector before ``serve_infoscreen`` binds its local
    ``collect_event_candidates`` reference; otherwise the Studio can only show
    the generic ``backend_diagnostics_not_loaded`` placeholder.
    """

    global _APPLIED
    if _APPLIED:
        return

    original_find = _browser.find_browser_executable

    def launch_chromium_http1(playwright: Any):
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-http2",
        ]
        executable = original_find()
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

    _browser.launch_chromium = launch_chromium_http1

    # This function is called by serve_infoscreen before it imports and binds
    # collect_event_candidates. Install the same listing-card authority used by
    # production first, then replace the review collector with its diagnostic
    # implementation. The replacement therefore sees the patched CARD_JS and
    # the no-listing-date admission policy.
    from .detail_date_authority import apply as apply_detail_date_authority
    from .event_review_diagnostics import apply as apply_event_review_diagnostics

    apply_detail_date_authority()
    apply_event_review_diagnostics()
    _APPLIED = True


__all__ = ["apply"]
