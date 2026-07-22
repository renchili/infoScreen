from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False


def _bind_final_browser_runtime_to_review() -> None:
    """Make Studio use the final browser rules, not import-time snapshots.

    ``event_review`` imports browser constants with ``from .browser import ...``.
    Several authorities intentionally rewrite the browser JavaScript after that
    module has already been imported, so its local names otherwise remain stale.
    This binding is the single final handoff after every browser authority has run.
    """

    from . import event_review as review

    for name in (
        "CARD_JS",
        "CLICK_NEXT_PAGE_JS",
        "DETAIL_CARD_JS",
        "DOM_TIMEOUT_MS",
        "LOAD_MORE_ROUNDS",
        "MAX_LISTING_PAGES",
        "NAV_TIMEOUT_MS",
        "NEXT_WAIT_MS",
        "PREPARE_PAGE_JS",
        "launch_chromium",
        "merge_detail_payload",
    ):
        setattr(review, name, getattr(_browser, name))


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection starts in
    HTTP/1.1 mode directly. Listing navigation accepts a readable rendered document
    even when lifecycle events do not settle. Review detail pages remain part of the
    blocking Preview request, but stop waiting after response commit and readable
    activity content. Coverage, source, date, detail-payload, dynamic-listing, card,
    link, and listing-provenance authorities are applied before their final values
    are bound into Review Studio.
    """

    global _APPLIED
    if _APPLIED:
        return

    original_find = _browser.find_browser_executable

    def launch_chromium_http1(playwright: Any):
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

    from .complete_collection_authority import apply as apply_complete_collection

    apply_complete_collection()

    from .detail_date_authority import apply as apply_detail_date_authority

    apply_detail_date_authority()

    from .detail_payload_authority import apply as apply_detail_payload_authority

    apply_detail_payload_authority()

    from .review_detail_navigation_authority import (
        apply as apply_review_detail_navigation_authority,
    )

    apply_review_detail_navigation_authority()

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

    from .listing_provenance_authority import apply as apply_listing_provenance_authority

    apply_listing_provenance_authority()

    # event_review was imported by detail_date_authority before the dynamic and
    # structural JavaScript rewrites above. Rebind only after the final versions are
    # complete, otherwise Studio keeps stale parser and CARD_JS snapshots. The
    # detail-candidate function itself remains the bounded blocking implementation.
    _bind_final_browser_runtime_to_review()

    from .event_review_diagnostics import apply as apply_event_review_diagnostics

    apply_event_review_diagnostics()

    from .review_publish_authority import apply as apply_review_publish_authority

    apply_review_publish_authority()
    _APPLIED = True


__all__ = ["apply"]
