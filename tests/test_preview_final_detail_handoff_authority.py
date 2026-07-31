from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_review as review  # noqa: E402
from local_events_runtime import http1_browser as http1  # noqa: E402
from local_events_runtime import preview_final_detail_handoff_authority as authority  # noqa: E402


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.saved = []
        self.listing = SimpleNamespace(
            candidate_id="preview-listing",
            source_id="artscience",
            source_name="ArtScience Museum",
            url="https://www.marinabaysands.com/museum/whats-on.html",
            decision="confirmed",
            discovered_at="2026-07-31T00:00:00+00:00",
            reviewed_at=None,
        )

    def load(self):
        return SimpleNamespace(listing_pages=[self.listing])

    def save(self, state):
        self.saved.append(state)
        return state


def test_preview_handoff_preserves_archive_detail_result_before_return(
    monkeypatch,
    tmp_path,
) -> None:
    event = SimpleNamespace(
        when="",
        detail_error="preview_listing_evidence_only_missing_when",
        detail_page_title="",
    )
    state = SimpleNamespace(
        events=[event],
        event_collection={
            "preview_detail_mode": "listing_evidence_only",
            "detail_page_request_count": 0,
            "detail_page_requests_skipped": 1,
        },
    )
    filter_calls = []
    verification_calls = []
    manifest_calls = []

    def expiring_filter(actual, effective):
        filter_calls.append(actual)
        actual.events = []
        return actual

    def final_http_collector(store):
        result = http1._filter_final_expired_events(state, object())
        result.event_collection["preview_detail_mode"] = "listing_evidence_only"
        result.event_collection["detail_page_requests_skipped"] = len(result.events)
        return result

    def verify(store, actual):
        verification_calls.append((store, actual))
        event.when = "13 Sep 2025 – 22 Feb 2026"
        event.detail_error = ""
        event.detail_page_title = "Another World Is Possible | ArtScience Museum"
        actual.event_collection["detail_page_request_count"] = 1
        return actual

    def issue_manifest(listing, actual):
        manifest_calls.append(("issue", listing, actual))
        actual.event_collection["preview_selection_manifest_policy"] = (
            "latest_server_preview_exact_set"
        )
        return actual

    monkeypatch.setattr(http1, "_filter_final_expired_events", expiring_filter)
    monkeypatch.setattr(review, "collect_event_candidates", final_http_collector)
    monkeypatch.setattr(authority, "_enrich_final_preview", verify)
    monkeypatch.setattr(
        authority._selection,
        "invalidate_preview_manifest",
        lambda url: manifest_calls.append(("invalidate", url)),
    )
    monkeypatch.setattr(
        authority._selection,
        "issue_preview_manifest",
        issue_manifest,
    )

    authority._wrap_current_collector()
    store = Store(tmp_path / "infoscreen-event-preview-archive")
    result = review.collect_event_candidates(store)

    assert filter_calls == []
    assert verification_calls == [(store, state)]
    assert manifest_calls == [
        ("invalidate", store.listing.url),
        ("issue", store.listing, state),
    ]
    assert len(result.events) == 1
    assert result.events[0].when == "13 Sep 2025 – 22 Feb 2026"
    assert result.events[0].detail_error == ""
    assert result.events[0].detail_page_title.startswith("Another World Is Possible")
    assert result.event_collection["preview_detail_mode"] == "official_detail_pages"
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_requests_skipped"] == 0
    assert result.event_collection["listing_only_candidates_remaining"] == 0
    assert result.event_collection["preview_expiry_policy"] == "retain_for_operator_review"
    assert result.event_collection["preview_selection_manifest_policy"] == (
        "latest_server_preview_exact_set"
    )
    assert store.saved == [result]
    assert http1._filter_final_expired_events is expiring_filter


def test_final_handoff_rejects_listing_only_rows_without_opening_a_browser(
    tmp_path,
) -> None:
    pending = SimpleNamespace(
        detail_error="preview_listing_evidence_only_missing_when"
    )
    state = SimpleNamespace(events=[pending], event_collection={})
    store = Store(tmp_path / "infoscreen-event-preview-incomplete")

    with pytest.raises(RuntimeError, match="direct collector"):
        authority._enrich_final_preview(store, state)

    source = inspect.getsource(authority._enrich_final_preview)
    assert "launch_chromium" not in source
    assert "_launch_preview_chromium" not in source
    assert "direct collector" in source


def test_final_handoff_accepts_fully_collected_rows(tmp_path) -> None:
    complete = SimpleNamespace(detail_error="")
    state = SimpleNamespace(events=[complete], event_collection={})
    store = Store(tmp_path / "infoscreen-event-preview-complete")

    assert authority._enrich_final_preview(store, state) is state


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


def test_review_bootstrap_uses_direct_preview_detail_collector() -> None:
    summary = read_text("surface/local_events_runtime/review_summary_authority.py")
    handoff = read_text(
        "surface/local_events_runtime/preview_final_detail_handoff_authority.py"
    )
    direct = read_text(
        "surface/local_events_runtime/preview_direct_detail_collector_authority.py"
    )

    assert "apply_preview_pipeline()" in summary
    assert "apply_preview_event_selection()" not in summary
    assert "apply_preview_collector()" not in summary
    assert "apply_artscience_preview()" not in summary
    assert "apply_preview_direct_details()" not in summary
    assert "apply_preview_transport()" not in summary

    assert "install_transport_apply_hook" not in handoff
    assert "preview_browser_session_authority" not in handoff
    assert "apply_preview_event_selection()" in handoff
    assert "apply_preview_collector()" in handoff
    assert "apply_artscience_preview()" in handoff
    assert "apply_preview_direct_details()" in handoff
    assert "apply_preview_detail_enrichment()" not in handoff
    assert "apply_preview_transport()" in handoff
    assert handoff.index("apply_preview_event_selection()") < handoff.index(
        "apply_preview_collector()"
    ) < handoff.index("apply_artscience_preview()") < handoff.index(
        "apply_preview_direct_details()"
    ) < handoff.index("apply_preview_transport()")

    assert "_BASE_BIND()" in handoff
    assert "_http1._filter_final_expired_events = _keep_preview_candidates" in handoff
    invalidate_call = "_selection.invalidate_preview_manifest(listing.url)"
    verify_call = "state = _enrich_final_preview(store, state)"
    issue_call = "state = _selection.issue_preview_manifest(listing, state)"
    assert invalidate_call in handoff
    assert verify_call in handoff
    assert issue_call in handoff
    assert handoff.index(invalidate_call) < handoff.index(verify_call) < handoff.index(
        issue_call
    )
    assert '"listing_only_candidates_remaining"' in handoff

    assert "def collect_preview(" in direct
    assert "with sync_playwright() as playwright:" in direct
    assert "browser = _browser.launch_chromium(playwright)" in direct
    assert "context = browser.new_context(" in direct
    assert "listing_page = context.new_page()" in direct
    assert "detail = _collect_detail(context, source, listing, raw)" in direct
    assert direct.index("listing_page.goto(") < direct.index(
        "detail = _collect_detail(context, source, listing, raw)"
    ) < direct.index("context.close()") < direct.index("browser.close()")
    assert "_preview._collect_preview = collect_preview" in direct
    assert "--disable-http2" not in direct
    assert "ContextVar" not in direct
    assert "launch_or_borrow" not in direct
