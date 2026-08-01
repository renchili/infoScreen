from __future__ import annotations

from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import http1_browser as _http1
from . import preview_detail_enrichment_authority as _enrichment
from . import preview_event_selection_authority as _selection
from . import review_effective_fields_authority as _effective

_APPLIED = False
_BASE_BIND = None


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _bind_preview_store_replace_events() -> None:
    """Keep expired candidates only in the isolated Preview store.

    The effective-fields lifecycle owner normally removes expired candidates inside
    ``EventReviewStore.replace_events``. That is correct for persisted/formal Review
    collection, but Preview needs those candidates as classification evidence.

    Replace the effective module's public binding, not only the class attribute, so
    later calls to ``_effective.apply()`` keep reinstalling this conditional owner.
    """

    current = _effective.replace_events
    if getattr(current, "_infoscreen_preview_retains_expired", False):
        _review.EventReviewStore.replace_events = current
        return

    if not _effective._APPLIED:
        _effective.apply()
        current = _effective.replace_events

    formal_replace = current

    def replace_events(
        store: _review.EventReviewStore,
        candidates: list[_review.EventCandidate],
        collection: dict,
    ) -> _review.ReviewState:
        if not _preview_store(store):
            return formal_replace(store, candidates, collection)

        base_replace = _effective._BASE_REPLACE_EVENTS
        if base_replace is None:
            raise RuntimeError("Preview base replace-events binding is unavailable")
        metadata = dict(collection)
        metadata["candidate_count"] = len(candidates)
        metadata.pop("expired_candidate_count", None)
        return base_replace(store, list(candidates), metadata)

    replace_events._infoscreen_preview_retains_expired = True
    replace_events._infoscreen_formal_replace_events = formal_replace
    _effective.replace_events = replace_events
    _review.EventReviewStore.replace_events = replace_events


def _enrich_final_preview(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
) -> _review.ReviewState:
    """Verify that the direct Preview collector returned final detail results."""

    remaining = sum(
        _enrichment._needs_detail(candidate) for candidate in state.events
    )
    if remaining:
        raise RuntimeError(
            "Preview detail collection remained listing-only after the direct collector "
            f"completed ({remaining} candidate(s))"
        )
    return state


def _preview_listing(store: _review.EventReviewStore) -> _review.ListingPageCandidate:
    state = store.load()
    if len(state.listing_pages) != 1:
        raise RuntimeError("isolated Preview must contain exactly one List Page")
    return state.listing_pages[0]


def _collect_preview_without_formal_expiry_filter(
    store: _review.EventReviewStore,
) -> _review.ReviewState:
    """Run the installed Preview chain without entering the formal collector.

    ``http1_browser`` owns the formal collector and applies final expiry filtering
    after ``diagnostics.collect_event_candidates`` returns. Preview needs the same
    rendered listing and official-detail collection, but must retain expired Events
    as classification evidence. The diagnostics binding is already composed as:

    transport -> preview collector -> direct detail collector.

    Calling it directly keeps that complete Preview chain and avoids only the formal
    post-collection lifecycle filter.
    """

    state = _diagnostics.collect_event_candidates(store)
    metadata = dict(state.event_collection)
    metadata.pop("expired_candidate_count", None)
    metadata["candidate_count"] = len(state.events)
    state.event_collection = metadata
    return state


def _wrap_current_collector() -> None:
    _bind_preview_store_replace_events()

    base_collect = _review.collect_event_candidates
    if getattr(base_collect, "_infoscreen_preview_final_detail_handoff", False):
        return

    def collect_event_candidates(store: _review.EventReviewStore):
        if not _preview_store(store):
            return base_collect(store)

        listing = _preview_listing(store)
        # A failed or newer Preview must never leave an older candidate set eligible
        # for submission. The replacement manifest is issued only after final detail
        # collection and redirect handling have completed.
        _selection.invalidate_preview_manifest(listing.url)

        state = _collect_preview_without_formal_expiry_filter(store)
        state = _enrich_final_preview(store, state)
        remaining_listing_only = sum(
            _enrichment._needs_detail(candidate) for candidate in state.events
        )
        state.event_collection = {
            **state.event_collection,
            "candidate_count": len(state.events),
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

    _bind_preview_store_replace_events()
    if _http1._APPLIED:
        _wrap_current_collector()


def apply_preview_pipeline() -> None:
    """Install the complete Preview pipeline in its established order."""

    from .artscience_preview_authority import apply as apply_artscience_preview
    from .preview_collector_authority import apply as apply_preview_collector
    from .preview_direct_detail_collector_authority import (
        apply as apply_preview_direct_details,
    )
    from .preview_event_selection_authority import (
        apply as apply_preview_event_selection,
    )
    from .preview_transport_authority import apply as apply_preview_transport

    # Formal collection must be filtered by the operator's Preview decisions before
    # source-specific Preview wrappers are composed over the diagnostics collector.
    apply_preview_event_selection()
    apply_preview_collector()
    # Source-specific rendered-card recognition supplies the list-page extraction JS.
    apply_artscience_preview()
    # The exact Preview entrypoint owns listing and detail navigation in one existing
    # Playwright lifecycle. ArtScience documents use sequential browser processes.
    apply_preview_direct_details()
    # Transport remains outermost only to choose the deployed headed Chromium mode and
    # record NetLog diagnostics for MBS. It does not alter the negotiated HTTP protocol.
    apply_preview_transport()
    # Bind the Preview-specific store lifecycle and public HTTP collector last.
    apply()


__all__ = [
    "apply",
    "apply_preview_pipeline",
    "_bind_preview_store_replace_events",
    "_collect_preview_without_formal_expiry_filter",
    "_enrich_final_preview",
    "_wrap_current_collector",
]
