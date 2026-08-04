from __future__ import annotations

from typing import Any

from . import event_review as _review
from . import listing_page_policy as _policy
from . import preview_event_selection_authority as _selection
from . import scoped_listing_collection as _scoped

_APPLIED = False
_BASE_CONFIGURED_CANDIDATES = None
_BASE_DISCOVER_HOME_LINKS = None
_BASE_STATE_PAYLOAD = None
_BASE_CONFIRMED_SELECTIONS = None


def _configured_candidates(
    source: dict[str, Any],
    discovered_at: str,
) -> dict[str, _review.ListingPageCandidate]:
    candidates = _BASE_CONFIGURED_CANDIDATES(source, discovered_at)
    return {
        candidate_id: candidate
        for candidate_id, candidate in candidates.items()
        if _policy.is_current_listing_page(candidate.url, candidate.link_text)
    }


def _discover_home_links(
    source: dict[str, Any],
    candidates: dict[str, _review.ListingPageCandidate],
    discovered_at: str,
    errors: list[dict[str, str]],
) -> None:
    _BASE_DISCOVER_HOME_LINKS(source, candidates, discovered_at, errors)
    rejected = [
        candidate_id
        for candidate_id, candidate in candidates.items()
        if not _policy.is_current_listing_page(candidate.url, candidate.link_text)
    ]
    for candidate_id in rejected:
        del candidates[candidate_id]


def _state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Hide retired archive pages immediately while preserving state until discovery."""

    payload = dict(_BASE_STATE_PAYLOAD(store))
    raw_pages = payload.get("listing_pages")
    pages = raw_pages if isinstance(raw_pages, list) else []
    active_pages = [
        row
        for row in pages
        if isinstance(row, dict)
        and _policy.is_current_listing_page(row.get("url"), row.get("link_text"))
    ]
    retired_urls = {
        str(row.get("url") or "")
        for row in pages
        if isinstance(row, dict)
        and not _policy.is_current_listing_page(row.get("url"), row.get("link_text"))
    }

    raw_events = payload.get("events")
    events = raw_events if isinstance(raw_events, list) else []
    payload["listing_pages"] = active_pages
    payload["events"] = [
        row
        for row in events
        if not isinstance(row, dict)
        or str(row.get("listing_url") or "") not in retired_urls
    ]
    payload["retired_archive_listing_count"] = len(pages) - len(active_pages)
    return payload


def _confirmed_selections(store: _review.EventReviewStore):
    """Never admit a persisted archive page into formal collection."""

    ids, urls, skipped = _BASE_CONFIRMED_SELECTIONS(store)
    state = store.load()
    listings = {item.url: item for item in state.listing_pages}
    retired = [
        listing_url
        for listing_url in ids
        if (
            listing_url not in listings
            or not _policy.is_current_listing_page(
                listing_url,
                listings[listing_url].link_text,
            )
        )
    ]
    for listing_url in retired:
        ids.pop(listing_url, None)
        urls.pop(listing_url, None)

    if not ids:
        raise ValueError(
            "no current confirmed List Page has a committed REAL EVENT selection"
        )
    return ids, urls, skipped


def apply() -> None:
    """Exclude archive/history pages from discovery, Studio, and formal collection."""

    global _APPLIED
    global _BASE_CONFIGURED_CANDIDATES
    global _BASE_DISCOVER_HOME_LINKS
    global _BASE_STATE_PAYLOAD
    global _BASE_CONFIRMED_SELECTIONS

    if _APPLIED:
        _scoped._configured_candidates = _configured_candidates
        _scoped._discover_home_links = _discover_home_links
        _review.EventReviewStore.state_payload = _state_payload
        _selection._confirmed_selections = _confirmed_selections
        return

    _BASE_CONFIGURED_CANDIDATES = _scoped._configured_candidates
    _BASE_DISCOVER_HOME_LINKS = _scoped._discover_home_links
    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_CONFIRMED_SELECTIONS = _selection._confirmed_selections
    _scoped._configured_candidates = _configured_candidates
    _scoped._discover_home_links = _discover_home_links
    _review.EventReviewStore.state_payload = _state_payload
    _selection._confirmed_selections = _confirmed_selections
    _APPLIED = True


__all__ = ["apply", "_confirmed_selections"]
