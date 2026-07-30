from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import http1_browser as _http1
from . import preview_detail_enrichment_authority as _enrichment
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


def _wrap_current_collector() -> None:
    base_collect = _review.collect_event_candidates
    if getattr(base_collect, "_infoscreen_preview_final_detail_handoff", False):
        return

    def collect_event_candidates(store: _review.EventReviewStore):
        if not _preview_store(store):
            return base_collect(store)

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


__all__ = ["apply", "_enrich_final_preview", "_wrap_current_collector"]
