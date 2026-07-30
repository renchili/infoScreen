from __future__ import annotations

from typing import Any

from . import event_review as _review
from . import http1_browser as _http1

_APPLIED = False
_BASE_BIND = None


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _keep_preview_candidates(state: Any, effective: Any):
    """Preview is classification evidence, so do not hide expired real Events.

    Formal collection still applies the normal active-event lifecycle filter. Preview must
    show the actual official detail facts first so the operator can decide whether a List
    Page contains real Events, including when reviewing an explicit archive page.
    """

    return state


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

        # http1_browser's historical final wrapper labels every Preview as listing-only
        # after the composed collector returns. Correct the final persisted metadata to
        # match the official detail requests that preview_detail_enrichment_authority ran.
        state.event_collection = {
            **state.event_collection,
            "preview_detail_mode": "official_detail_pages",
            "detail_page_requests_skipped": 0,
            "preview_expiry_policy": "retain_for_operator_review",
        }
        return store.save(state)

    collect_event_candidates._infoscreen_preview_final_detail_handoff = True
    collect_event_candidates._infoscreen_base_collect = base_collect
    _review.collect_event_candidates = collect_event_candidates


def _bind_final_event_collector() -> None:
    _BASE_BIND()
    _wrap_current_collector()


def apply() -> None:
    """Patch the final HTTP handoff before http1_browser exports its collector.

    review_summary_authority calls this while http1_browser.apply() is still composing the
    runtime. The original final binder is retained, then its exported collector is wrapped
    once so Preview detail enrichment and archive evidence survive the final handoff.
    """

    global _APPLIED, _BASE_BIND
    if not _APPLIED:
        _BASE_BIND = _http1._bind_final_event_collector
        _http1._bind_final_event_collector = _bind_final_event_collector
        _APPLIED = True

    # Re-application can happen after bootstrap in tests or authority refreshes.
    if _http1._APPLIED:
        _wrap_current_collector()


__all__ = ["apply"]
