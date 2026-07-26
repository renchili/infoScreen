from __future__ import annotations

from typing import Any

from . import event_review as _review

_APPLIED = False
_BASE_REPLACE_EVENTS = None


def _confirmed_listing_urls(store: _review.EventReviewStore) -> set[str]:
    state = store.load()
    return {
        item.url
        for item in state.listing_pages
        if item.decision == "confirmed"
    }


def replace_events(
    store: _review.EventReviewStore,
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    """Replace only the listing pages participating in this collection run.

    Studio temporarily narrows confirmed listing pages when collecting one institution
    or one preview card. The legacy store replaced the complete Event list, so that
    temporary scope erased candidates belonging to every other institution. Preserve
    out-of-scope candidates while replacing all candidates from the active confirmed
    listing pages, including correctly removing stale rows when a scoped page now
    returns zero candidates.
    """

    scope_urls = _confirmed_listing_urls(store)
    state = store.load()
    preserved = [
        candidate
        for candidate in state.events
        if candidate.listing_url not in scope_urls
    ]
    combined = [*preserved, *candidates]

    metadata = dict(collection)
    metadata["collection_scope_listing_urls"] = sorted(scope_urls)
    metadata["collected_scope_candidate_count"] = len(candidates)
    metadata["preserved_out_of_scope_candidate_count"] = len(preserved)
    metadata["candidate_count"] = len(combined)
    return _BASE_REPLACE_EVENTS(store, combined, metadata)


def apply() -> None:
    """Install scoped Review replacement before effective-field wrapping."""

    global _APPLIED, _BASE_REPLACE_EVENTS
    if _APPLIED:
        return
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events
    _review.EventReviewStore.replace_events = replace_events
    _APPLIED = True


__all__ = [
    "apply",
    "replace_events",
    "_confirmed_listing_urls",
]
