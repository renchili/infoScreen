from __future__ import annotations

from typing import Any

from . import detail_date_authority as _detail_dates
from . import event_review as _review

_APPLIED = False
_BASE_DETAIL_CANDIDATE = None
_BASE_LOAD = None
_BASE_STATE_PAYLOAD = None
_BASE_REPLACE_EVENTS = None


def _repair_fields(
    raw: dict[str, Any],
    runtime_row: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the collected Review fields unchanged.

    Runtime snapshots, listing cards, parser reconstruction, and source defaults must
    not overwrite title, when, where, or summary returned by the detail collector.
    """

    return dict(raw)


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Preserve the exact result returned by the active detail collector."""

    result = dict(
        _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )
    )
    return {
        key: str(value or "") if key != "status" else value
        for key, value in result.items()
    }


def _expired(candidate: _review.EventCandidate) -> bool:
    """Apply lifecycle filtering to the collected When value without rewriting it."""

    return bool(_detail_dates._candidate_expired(candidate))


def _active_candidates(
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> tuple[list[_review.EventCandidate], dict[str, Any]]:
    active = [candidate for candidate in candidates if not _expired(candidate)]
    removed = len(candidates) - len(active)
    metadata = dict(collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = int(
        metadata.get("expired_candidate_count") or 0
    ) + removed
    return active, metadata


def load(store: _review.EventReviewStore) -> _review.ReviewState:
    """Load exact persisted fields and hide only candidates that are already past."""

    state = _BASE_LOAD(store)
    state.events, state.event_collection = _active_candidates(
        list(state.events),
        state.event_collection,
    )
    return state


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Expose exact persisted fields; do not backfill them from another runtime."""

    payload = dict(_BASE_STATE_PAYLOAD(store))
    events = [
        dict(row)
        for row in payload.get("events") or []
        if isinstance(row, dict)
    ]
    payload["events"] = [
        row
        for row in events
        if not _detail_dates._candidate_expired(
            _review.EventCandidate.model_validate(row)
        )
    ]
    collection = dict(payload.get("event_collection") or {})
    removed = len(events) - len(payload["events"])
    collection["candidate_count"] = len(payload["events"])
    collection["expired_candidate_count"] = int(
        collection.get("expired_candidate_count") or 0
    ) + removed
    payload["event_collection"] = collection
    return payload


def replace_events(
    store: _review.EventReviewStore,
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    """Persist exact collected fields and exclude only already-ended candidates."""

    active, metadata = _active_candidates(list(candidates), collection)
    return _BASE_REPLACE_EVENTS(store, active, metadata)


def apply() -> None:
    """Install exact-field Review state handling."""

    global _APPLIED, _BASE_DETAIL_CANDIDATE, _BASE_LOAD
    global _BASE_STATE_PAYLOAD, _BASE_REPLACE_EVENTS
    if _APPLIED:
        return

    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _BASE_LOAD = _review.EventReviewStore.load
    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events

    _review._detail_candidate = _detail_candidate
    _review.EventReviewStore.load = load
    _review.EventReviewStore.state_payload = state_payload
    _review.EventReviewStore.replace_events = replace_events
    _APPLIED = True


__all__ = [
    "apply",
    "load",
    "replace_events",
    "state_payload",
    "_detail_candidate",
    "_repair_fields",
]
