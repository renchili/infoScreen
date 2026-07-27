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


def _is_explicit_open_schedule(value: object) -> bool:
    """Preserve the existing explicit open-ended schedule policy."""
    from . import extract

    text = extract.clean(value).casefold()
    return text.startswith("from ") or "ongoing" in text or "permanent" in text


def _filter_final_expired_events(state, effective):
    """Use the final detail parser for the final HTTP lifecycle decision."""
    from . import extract

    active = []
    removed = 0
    for candidate in state.events:
        if _is_explicit_open_schedule(candidate.when):
            active.append(candidate)
            continue
        dates = effective._line_dates(candidate.when)
        if dates and max(dates) < extract.TODAY:
            removed += 1
            continue
        active.append(candidate)

    state.events = active
    metadata = dict(state.event_collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = int(
        metadata.get("expired_candidate_count") or 0
    ) + removed
    state.event_collection = metadata
    return state


def _bind_final_event_collector() -> None:
    """Pin every HTTP collection run to the final detail owner.

    The HTTP server imports ``event_review.collect_event_candidates`` only after this
    bootstrap completes. This wrapper refreshes the final owner immediately before
    the diagnostics collector starts, so no import-time snapshot or later monkey
    patch can route POST collection through an older detail implementation.
    """
    from . import event_review as review
    from . import event_review_diagnostics as diagnostics
    from . import review_effective_fields_authority as effective

    def collect_event_candidates(store):
        effective.apply()
        review._detail_candidate = effective.detail_candidate
        state = diagnostics.collect_event_candidates(store)
        state = _filter_final_expired_events(state, effective)
        state.event_collection = {
            **state.event_collection,
            "detail_owner_module": effective.detail_candidate.__module__,
            "detail_owner_name": effective.detail_candidate.__qualname__,
            "detail_owner_file": str(effective.__file__),
        }
        store.save(state)
        return state

    review.collect_event_candidates = collect_event_candidates


def apply() -> None:
    """Install the shared Local Events browser and review-backend bootstrap.

    The Surface has observed Chromium navigation failures with
    ERR_HTTP2_PROTOCOL_ERROR on official Event sites. Collection starts in
    HTTP/1.1 mode directly. Browser operations are clamped to the active source and
    global collection deadlines so timed-out workers close before systemd's outer
    service limit. Listing navigation accepts a readable rendered document even when
    lifecycle events do not settle. Review detail navigations start in a bounded
    batch, are consumed synchronously by the existing blocking reader, and are closed
    immediately after extraction. A per-context URL cache prevents overlapping
    listing pages from downloading the same detail document repeatedly. Coverage,
    source, date, detail-field, section-aware summary, listing-provenance,
    listing-membership, dynamic-listing, card, and link authorities are applied before
    their final values are bound into Review Studio.
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

    from .deadline_authority import apply as apply_deadline_authority
    apply_deadline_authority()

    from .complete_collection_authority import apply as apply_complete_collection
    apply_complete_collection()

    from .detail_date_authority import apply as apply_detail_date_authority
    apply_detail_date_authority()

    from .detail_payload_authority import apply as apply_detail_payload_authority
    apply_detail_payload_authority()

    from .detail_summary_authority import apply as apply_detail_summary_authority
    apply_detail_summary_authority()

    from .review_detail_navigation_authority import (
        apply as apply_review_detail_navigation_authority,
    )
    apply_review_detail_navigation_authority()

    from .dynamic_listing_authority import apply as apply_dynamic_listing_authority
    apply_dynamic_listing_authority()

    from .open_ended_date_authority import apply as apply_open_ended_date_authority
    apply_open_ended_date_authority()

    from .open_detail_fields_authority import apply as apply_open_detail_fields_authority
    apply_open_detail_fields_authority()

    from .gardens_field_authority import apply as apply_gardens_field_authority
    apply_gardens_field_authority()

    from .listing_provenance_authority import apply as apply_listing_provenance_authority
    apply_listing_provenance_authority()

    from .listing_membership_authority import apply as apply_listing_membership_authority
    apply_listing_membership_authority()

    from .mandai_listing_authority import apply as apply_mandai_listing_authority
    apply_mandai_listing_authority()

    from .structural_link_authority import apply as apply_structural_link_authority
    apply_structural_link_authority()

    from .listing_url_authority import apply as apply_listing_url_authority
    apply_listing_url_authority()

    # Apply this last over the composed event authority so explicit Where/Location
    # labels and public URL rewrites survive every source/membership wrapper.
    from .detail_authority import apply as apply_detail_authority
    apply_detail_authority()

    # event_review was imported before the final JavaScript rewrites above. Rebind
    # only after all browser and event authorities have their final values.
    _bind_final_browser_runtime_to_review()

    from .review_effective_fields_authority import (
        apply as apply_review_effective_fields_authority,
    )
    apply_review_effective_fields_authority()

    from .event_review_diagnostics import apply as apply_event_review_diagnostics
    apply_event_review_diagnostics()

    from .review_summary_authority import apply as apply_review_summary_authority
    apply_review_summary_authority()

    from .review_publish_authority import apply as apply_review_publish_authority
    apply_review_publish_authority()

    # This is the final HTTP handoff. The server imports the wrapper from event_review
    # after apply() returns, and the wrapper pins every POST to the effective owner.
    _bind_final_event_collector()
    _APPLIED = True


__all__ = ["apply"]