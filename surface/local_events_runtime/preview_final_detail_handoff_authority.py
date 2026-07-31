from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import http1_browser as _http1
from . import preview_detail_enrichment_authority as _enrichment
from . import preview_event_selection_authority as _selection
from . import preview_transport_authority as _transport

_APPLIED = False
_BASE_BIND = None


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _keep_preview_candidates(state: Any, effective: Any):
    """Preview is classification evidence, so do not hide expired real Events."""

    return state


def _enrich_final_preview(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
) -> _review.ReviewState:
    """Guarantee that no listing-only row escapes the final HTTP handoff.

    The normal composed Preview chain should enrich before transport returns. This final
    guard handles any authority-order regression by reusing the exact same installed
    Chromium and MBS headed policy while the result is still inside the server request.
    """

    if not any(_enrichment._needs_detail(candidate) for candidate in state.events):
        return state

    original_launch = _browser.launch_chromium
    original_headless = _transport._PREVIEW_HEADLESS
    _transport._PREVIEW_HEADLESS = not _transport._requires_headed_preview(store)
    if not _transport._PREVIEW_HEADLESS and not _transport._graphical_session_available():
        _transport._PREVIEW_HEADLESS = original_headless
        raise RuntimeError(
            "MBS preview detail enrichment requires the existing Surface graphical "
            "session; DISPLAY and WAYLAND_DISPLAY are both missing"
        )

    _browser.launch_chromium = _transport._launch_preview_chromium
    try:
        return _enrichment.enrich_preview_state(store, state)
    finally:
        _browser.launch_chromium = original_launch
        _transport._PREVIEW_HEADLESS = original_headless


def _preview_listing(store: _review.EventReviewStore) -> _review.ListingPageCandidate:
    state = store.load()
    if len(state.listing_pages) != 1:
        raise RuntimeError("isolated Preview must contain exactly one List Page")
    return state.listing_pages[0]


def _wrap_current_collector() -> None:
    base_collect = _review.collect_event_candidates
    if getattr(base_collect, "_infoscreen_preview_final_detail_handoff", False):
        return

    def collect_event_candidates(store: _review.EventReviewStore):
        if not _preview_store(store):
            return base_collect(store)

        listing = _preview_listing(store)
        # A failed or newer Preview must never leave an older candidate set eligible
        # for submission. The replacement manifest is issued only after final detail
        # enrichment and redirect handling have completed.
        _selection.invalidate_preview_manifest(listing.url)

        original_filter = _http1._filter_final_expired_events
        _http1._filter_final_expired_events = _keep_preview_candidates
        try:
            state = base_collect(store)
        finally:
            _http1._filter_final_expired_events = original_filter

        state = _enrich_final_preview(store, state)
        remaining_listing_only = sum(
            _enrichment._needs_detail(candidate) for candidate in state.events
        )
        state.event_collection = {
            **state.event_collection,
            "preview_detail_mode": "official_detail_pages",
            "detail_page_requests_skipped": 0,
            "preview_expiry_policy": "retain_for_operator_review",
            "listing_only_candidates_remaining": remaining_listing_only,
        }
        state = _selection.issue_preview_manifest(listing, state)
        return store.save(state)

    collect_event_candidates._infoscreen_preview_final_detail_handoff = True
    collect_event_candidates._infoscreen_base_collect = base_collect
    _review.collect_event_candidates = collect_event_candidates


def _bind_final_event_collector() -> None:
    _BASE_BIND()
    _wrap_current_collector()


def apply() -> None:
    """Patch and verify the final HTTP Preview collector exported by bootstrap."""

    global _APPLIED, _BASE_BIND
    if not _APPLIED:
        _BASE_BIND = _http1._bind_final_event_collector
        _http1._bind_final_event_collector = _bind_final_event_collector
        _APPLIED = True

    if _http1._APPLIED:
        _wrap_current_collector()


def apply_preview_pipeline() -> None:
    """Install the complete Preview pipeline in its established order.

    This function centralizes composition only. Each existing authority still owns its
    current behavior, state, compatibility entrypoints, and idempotent apply guard.
    """

    from .artscience_preview_authority import apply as apply_artscience_preview
    from .preview_browser_session_authority import install_transport_apply_hook
    from .preview_collector_authority import apply as apply_preview_collector
    from .preview_detail_enrichment_authority import (
        apply as apply_preview_detail_enrichment,
    )
    from .preview_event_selection_authority import (
        apply as apply_preview_event_selection,
    )
    from .preview_transport_authority import apply as apply_preview_transport

    # Register the single-browser transport before the established pipeline applies its
    # outer transport wrapper. The hook preserves the complete base chain, then replaces
    # only the final Preview transport with one HTTP/1 Chromium lease shared by listing
    # and detail reads.
    install_transport_apply_hook()

    # Formal collection must be filtered by the operator's Preview decisions before
    # source-specific Preview wrappers are composed over the diagnostics collector.
    apply_preview_event_selection()
    apply_preview_collector()
    # Source-specific rendered-card recognition identifies official detail URLs first.
    apply_artscience_preview()
    # Preview review requires the actual official detail fields. Selection controls must
    # not downgrade candidates to listing-only evidence.
    apply_preview_detail_enrichment()
    # Transport remains outermost so both the listing and detail Chromium sessions use
    # the verified headed policy for MBS on the deployed Surface.
    apply_preview_transport()
    # Patch the final HTTP handoff last so enriched Preview rows cannot be downgraded or
    # hidden by the base expiry filter. This owner also records the exact final Preview
    # candidate set used by the subsequent List Page review request.
    apply()


__all__ = [
    "apply",
    "apply_preview_pipeline",
    "_enrich_final_preview",
    "_wrap_current_collector",
]
