from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection starts in
    HTTP/1.1 mode directly. Navigation accepts a readable rendered document even
    when analytics or consent requests prevent lifecycle events from settling.
    Coverage, source, date, dynamic-listing, card, and link authorities are applied
    sequentially before the review collector imports and binds their functions.
    """

    global _APPLIED
    if _APPLIED:
        return

    original_find = _browser.find_browser_executable

    def launch_chromium_http1(playwright: Any):
        # Playwright is guaranteed to be importable at this point. Install the
        # shared Page.goto wrapper before any browser page can be created.
        from .resilient_navigation_authority import apply as apply_navigation

        apply_navigation()

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

    # The runtime package is already imported by the time this bootstrap runs.
    # Apply live coverage floors before importing modules that bind browser and
    # extraction constants.
    from .complete_collection_authority import apply as apply_complete_collection

    apply_complete_collection()

    # Import and apply sequentially. Importing structural/diagnostic modules also
    # imports event_review, so every parser and CARD_JS patch must already be active.
    from .detail_date_authority import apply as apply_detail_date_authority

    apply_detail_date_authority()

    from .dynamic_listing_authority import apply as apply_dynamic_listing_authority

    apply_dynamic_listing_authority()

    from .open_ended_date_authority import apply as apply_open_ended_date_authority

    apply_open_ended_date_authority()

    from .gardens_field_authority import apply as apply_gardens_field_authority

    apply_gardens_field_authority()

    from .mandai_listing_authority import apply as apply_mandai_listing_authority

    apply_mandai_listing_authority()

    from .structural_link_authority import apply as apply_structural_link_authority

    apply_structural_link_authority()

    from .event_review_diagnostics import apply as apply_event_review_diagnostics

    apply_event_review_diagnostics()

    from .review_publish_authority import apply as apply_review_publish_authority

    apply_review_publish_authority()
    _APPLIED = True


__all__ = ["apply"]
