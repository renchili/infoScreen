from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_review as review  # noqa: E402
from local_events_runtime import http1_browser as http1  # noqa: E402
from local_events_runtime import preview_final_detail_handoff_authority as authority  # noqa: E402


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.saved = []

    def save(self, state):
        self.saved.append(state)
        return state


def test_preview_handoff_keeps_enriched_archive_event_and_corrects_metadata(
    monkeypatch,
    tmp_path,
) -> None:
    state = SimpleNamespace(
        events=[SimpleNamespace(when="13 Sep 2025 – 22 Feb 2026")],
        event_collection={
            "preview_detail_mode": "listing_evidence_only",
            "detail_page_request_count": 1,
            "detail_page_requests_skipped": 1,
        },
    )
    filter_calls = []

    def expiring_filter(actual, effective):
        filter_calls.append(actual)
        actual.events = []
        return actual

    def final_http_collector(store):
        result = http1._filter_final_expired_events(state, object())
        result.event_collection["preview_detail_mode"] = "listing_evidence_only"
        result.event_collection["detail_page_requests_skipped"] = len(result.events)
        return result

    monkeypatch.setattr(http1, "_filter_final_expired_events", expiring_filter)
    monkeypatch.setattr(review, "collect_event_candidates", final_http_collector)

    authority._wrap_current_collector()
    store = Store(tmp_path / "infoscreen-event-preview-archive")
    result = review.collect_event_candidates(store)

    assert filter_calls == []
    assert len(result.events) == 1
    assert result.event_collection["preview_detail_mode"] == "official_detail_pages"
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_requests_skipped"] == 0
    assert result.event_collection["preview_expiry_policy"] == "retain_for_operator_review"
    assert store.saved == [result]
    assert http1._filter_final_expired_events is expiring_filter


def test_formal_collection_keeps_normal_expiry_handoff(monkeypatch, tmp_path) -> None:
    expected = object()
    calls = []

    def final_http_collector(store):
        calls.append(store)
        return expected

    monkeypatch.setattr(review, "collect_event_candidates", final_http_collector)
    authority._wrap_current_collector()
    store = Store(tmp_path / "local_event_review")

    assert review.collect_event_candidates(store) is expected
    assert calls == [store]
    assert store.saved == []


def test_review_bootstrap_patches_final_handoff_after_detail_transport() -> None:
    summary = read_text("surface/local_events_runtime/review_summary_authority.py")
    handoff = read_text(
        "surface/local_events_runtime/preview_final_detail_handoff_authority.py"
    )

    assert "apply_preview_detail_enrichment()" in summary
    assert "apply_preview_transport()" in summary
    assert "apply_preview_final_detail_handoff()" in summary
    assert summary.index("apply_preview_detail_enrichment()") < summary.index(
        "apply_preview_transport()"
    ) < summary.index("apply_preview_final_detail_handoff()")
    assert "_BASE_BIND()" in handoff
    assert "_http1._filter_final_expired_events = _keep_preview_candidates" in handoff
    assert '"preview_detail_mode": "official_detail_pages"' in handoff
