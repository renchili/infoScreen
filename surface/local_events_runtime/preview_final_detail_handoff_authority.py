from __future__ import annotations

from typing import Any

from . import event_review as _review
from . import http1_browser as _http1
from . import preview_detail_enrichment_authority as _enrichment
from . import preview_event_selection_authority as _selection

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


def _collector_chain(root: Any):
    """Yield every callable reachable through the installed collector wrappers."""

    pending = [root]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if not callable(current) or id(current) in seen:
            continue
        seen.add(id(current))
        yield current

        for attribute in ("_infoscreen_base_collect", "__wrapped__", "func"):
            nested = getattr(current, attribute, None)
            if callable(nested):
                pending.append(nested)

        for value in getattr(current, "__defaults__", None) or ():
            if callable(value):
                pending.append(value)
        for value in (getattr(current, "__kwdefaults__", None) or {}).values():
            if callable(value):
                pending.append(value)

        for cell in getattr(current, "__closure__", None) or ():
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if callable(value):
                pending.append(value)


def _patch_expiry_filters(root: Any) -> list[tuple[dict[str, Any], Any]]:
    """Patch the actual inner collector globals that execute expiry filtering."""

    patched: list[tuple[dict[str, Any], Any]] = []
    seen_globals: set[int] = set()
    for collector in _collector_chain(root):
        namespace = getattr(collector, "__globals__", None)
        code = getattr(collector, "__code__", None)
        if not isinstance(namespace, dict) or code is None:
            continue
        if "_filter_final_expired_events" not in code.co_names:
            continue
        if "_filter_final_expired_events" not in namespace:
            continue
        namespace_id = id(namespace)
        if namespace_id in seen_globals:
            continue
        seen_globals.add(namespace_id)
        patched.append((namespace, namespace["_filter_final_expired_events"]))
        namespace["_filter_final_expired_events"] = _keep_preview_candidates

    if not patched:
        raise RuntimeError(
            "Preview collector chain does not expose the executing expiry filter"
        )
    return patched


def _restore_expiry_filters(patched: list[tuple[dict[str, Any], Any]]) -> None:
    for namespace, original in reversed(patched):
        namespace["_filter_final_expired_events"] = original


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
        # collection and redirect handling have completed.
        _selection.invalidate_preview_manifest(listing.url)

        patched = _patch_expiry_filters(base_collect)
        try:
            state = base_collect(store)
        finally:
            _restore_expiry_filters(patched)

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
    # Patch the final HTTP handoff last so Preview candidates remain visible even when
    # their official date range has expired and can still be classified by the operator.
    apply()


__all__ = [
    "apply",
    "apply_preview_pipeline",
    "_collector_chain",
    "_enrich_final_preview",
    "_patch_expiry_filters",
    "_wrap_current_collector",
]
