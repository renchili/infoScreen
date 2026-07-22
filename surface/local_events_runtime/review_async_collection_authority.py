from __future__ import annotations

import threading
from typing import Any

from . import event_review as _review
from .review_collection_jobs import (
    CollectionAlreadyRunning,
    CollectionStoreView,
    EventCollectionJobManager,
)

_APPLIED = False
_BASE_COLLECT = None
_BASE_STATE_PAYLOAD = None
_BASE_SAVE = None
_STATE_WRITE_LOCK = threading.RLock()
JOBS = EventCollectionJobManager()


def _locked_save(store: _review.EventReviewStore, state: _review.ReviewState):
    """Serialize every Review state replacement, including background completion."""

    with _STATE_WRITE_LOCK:
        return _BASE_SAVE(store, state)


def _confirmed_listing_ids(store: _review.EventReviewStore) -> list[str]:
    state = store.load()
    return sorted(
        item.candidate_id
        for item in state.listing_pages
        if item.decision == "confirmed"
    )


def _response_state(
    store: _review.EventReviewStore,
    job: dict[str, Any],
) -> _review.ReviewState:
    state = store.load().model_copy(deep=True)
    state.event_collection = {
        **dict(state.event_collection or {}),
        "background_job": job,
    }
    return state


def collect_event_candidates(
    store: _review.EventReviewStore,
) -> _review.ReviewState:
    """Start the canonical collector in the background and return immediately.

    The confirmed listing IDs are snapshotted before the HTTP request returns. This
    preserves the existing per-listing Preview flow, which temporarily marks only the
    target page confirmed and restores the operator's decisions after the request.
    The worker receives a scoped view and therefore does not depend on those temporary
    decisions remaining in the persisted state.
    """

    listing_ids = _confirmed_listing_ids(store)
    if not listing_ids:
        raise ValueError("no confirmed listing pages")

    view = CollectionStoreView(
        store,
        _STATE_WRITE_LOCK,
        listing_candidate_ids=listing_ids,
    )

    try:
        job = JOBS.start(
            lambda: _BASE_COLLECT(view),
            listing_candidate_ids=listing_ids,
        )
    except CollectionAlreadyRunning as exc:
        running_scope = sorted(exc.job.get("listing_candidate_ids") or [])
        if running_scope != listing_ids:
            raise ValueError(
                "a different Event Preview collection is already running"
            ) from exc
        job = exc.job

    return _response_state(store, job)


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    payload = dict(_BASE_STATE_PAYLOAD(store))
    payload["event_collection_job"] = JOBS.snapshot()
    return payload


def apply() -> None:
    """Install non-blocking collection after the final diagnostic collector exists."""

    global _APPLIED, _BASE_COLLECT, _BASE_STATE_PAYLOAD, _BASE_SAVE
    if _APPLIED:
        return

    _BASE_COLLECT = _review.collect_event_candidates
    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_SAVE = _review.EventReviewStore.save

    _review.EventReviewStore.save = _locked_save
    _review.EventReviewStore.state_payload = state_payload
    _review.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = ["JOBS", "apply", "collect_event_candidates", "state_payload"]
