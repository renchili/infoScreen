from __future__ import annotations

import inspect
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_review as review  # noqa: E402
from local_events_runtime import preview_final_detail_handoff_authority as authority  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    ReviewState,
)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.saved = []
        self.listing = SimpleNamespace(
            candidate_id="preview-listing",
            source_id="museum",
            source_name="Museum",
            url="https://example.com/whats-on",
            decision="confirmed",
            discovered_at="2026-07-31T00:00:00+00:00",
            reviewed_at=None,
        )

    def load(self):
        return SimpleNamespace(listing_pages=[self.listing])

    def save(self, state):
        self.saved.append(state)
        return state


def _candidate(title: str, when: str) -> EventCandidate:
    slug = title.casefold().replace(" ", "-")
    return EventCandidate(
        candidate_id=f"candidate-{slug}",
        source_id="museum",
        source_name="Museum",
        listing_url="https://example.com/whats-on",
        detail_url=f"https://example.com/activities/{slug}",
        title=title,
        when=when,
        where="Museum",
        summary="Official activity details.",
        detail_status="collected",
        evidence=EventEvidence(
            selector="article.activity",
            selector_index=0,
            selector_match_count=1,
            document_position={"x": 0, "y": 0, "width": 100, "height": 100},
            viewport_position={"x": 0, "y": 0, "width": 100, "height": 100},
            page_index=0,
            page_url="https://example.com/whats-on",
            text=title,
        ),
        decision="pending",
        collected_at="2026-01-01T00:00:00+00:00",
    )


def _label(day: date) -> str:
    return day.strftime("%-d %b %Y")


def test_final_preview_retains_ended_events_for_operator_review() -> None:
    expired_end = date.today() - timedelta(days=10)
    future_end = date.today() + timedelta(days=10)
    state = ReviewState(
        events=[
            _candidate("Expired activity", _label(expired_end)),
            _candidate("Current activity", _label(future_end)),
        ],
        event_collection={
            "candidate_count": 1,
            "expired_candidate_count": 1,
        },
    )

    result = authority._retain_expired_preview_events(state)

    assert [row.title for row in result.events] == [
        "Expired activity",
        "Current activity",
    ]
    assert result.event_collection["candidate_count"] == 2
    assert "expired_candidate_count" not in result.event_collection
    assert result.event_collection["preview_expiry_policy"] == (
        "retain_for_operator_review"
    )


def test_preview_retains_expiry_before_issuing_manifest(monkeypatch, tmp_path) -> None:
    expired = _candidate(
        "Stamping the Coast",
        "1 - 24 May 2026 (except Mondays)",
    )
    state = ReviewState(events=[expired], event_collection={"candidate_count": 1})
    calls: list[object] = []

    monkeypatch.setattr(
        authority,
        "_bind_preview_store_replace_events",
        lambda: None,
    )
    monkeypatch.setattr(
        authority,
        "_collect_preview_before_final_expiry",
        lambda store: state,
    )
    monkeypatch.setattr(
        authority,
        "_enrich_final_preview",
        lambda store, actual: calls.append("enrich") or actual,
    )

    def retain_expired(actual):
        calls.append("retain")
        actual.event_collection = {
            **actual.event_collection,
            "candidate_count": len(actual.events),
            "preview_expiry_policy": "retain_for_operator_review",
        }
        return actual

    def issue_manifest(listing, actual):
        calls.append(("manifest", len(actual.events)))
        return actual

    monkeypatch.setattr(
        authority,
        "_retain_expired_preview_events",
        retain_expired,
    )
    monkeypatch.setattr(
        authority._selection,
        "invalidate_preview_manifest",
        lambda url: calls.append(("invalidate", url)),
    )
    monkeypatch.setattr(
        authority._selection,
        "issue_preview_manifest",
        issue_manifest,
    )
    monkeypatch.setattr(review, "collect_event_candidates", lambda store: object())

    authority._wrap_current_collector()
    store = Store(tmp_path / "infoscreen-event-preview-childrens-museum")
    result = review.collect_event_candidates(store)

    assert calls == [
        ("invalidate", store.listing.url),
        "enrich",
        "retain",
        ("manifest", 1),
    ]
    assert result.events == [expired]
    assert result.event_collection["candidate_count"] == 1
    assert "expired_candidate_count" not in result.event_collection
    assert result.event_collection["preview_expiry_policy"] == (
        "retain_for_operator_review"
    )
    assert store.saved == [result]


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


def test_formal_collection_keeps_normal_collector(monkeypatch, tmp_path) -> None:
    expected = object()
    calls = []

    def final_http_collector(store):
        calls.append(store)
        return expected

    monkeypatch.setattr(
        authority,
        "_bind_preview_store_replace_events",
        lambda: None,
    )
    monkeypatch.setattr(review, "collect_event_candidates", final_http_collector)
    authority._wrap_current_collector()
    store = Store(tmp_path / "local_event_review")

    assert review.collect_event_candidates(store) is expected
    assert calls == [store]
    assert store.saved == []


def test_review_bootstrap_retains_expiry_before_preview_manifest() -> None:
    summary = read_text("surface/local_events_runtime/review_summary_authority.py")
    handoff = read_text(
        "surface/local_events_runtime/preview_final_detail_handoff_authority.py"
    )

    assert "apply_preview_pipeline()" in summary
    assert "_retain_expired_preview_events" in handoff
    assert '"preview_expiry_policy": "retain_for_operator_review"' in handoff
    assert "exclude_ended_events" not in handoff

    invalidate_call = "_selection.invalidate_preview_manifest(listing.url)"
    enrich_call = "state = _enrich_final_preview(store, state)"
    retain_call = "state = _retain_expired_preview_events(state)"
    issue_call = "state = _selection.issue_preview_manifest(listing, state)"

    assert invalidate_call in handoff
    assert enrich_call in handoff
    assert retain_call in handoff
    assert issue_call in handoff
    assert handoff.index(invalidate_call) < handoff.index(enrich_call)
    assert handoff.index(enrich_call) < handoff.index(retain_call)
    assert handoff.index(retain_call) < handoff.index(issue_call)
