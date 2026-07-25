from __future__ import annotations

import sys
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_collection_scope_authority as authority  # noqa: E402


class FakeCandidate:
    def __init__(self, candidate_id: str, listing_url: str):
        self.candidate_id = candidate_id
        self.listing_url = listing_url


class FakeStore:
    def __init__(self):
        self.state = SimpleNamespace(
            listing_pages=[
                SimpleNamespace(url="https://acm/list", decision="confirmed"),
                SimpleNamespace(url="https://zoo/list", decision="pending"),
            ],
            events=[
                FakeCandidate("old-acm", "https://acm/list"),
                FakeCandidate("old-zoo", "https://zoo/list"),
            ],
        )

    def load(self):
        return self.state


def test_scoped_collection_replaces_active_page_and_preserves_other_sources(monkeypatch) -> None:
    store = FakeStore()
    captured = {}

    def base(active_store, candidates, collection):
        captured["store"] = active_store
        captured["candidates"] = candidates
        captured["collection"] = collection
        return "saved"

    monkeypatch.setattr(authority, "_BASE_REPLACE_EVENTS", base)
    result = authority.replace_events(
        store,
        [FakeCandidate("new-acm", "https://acm/list")],
        {"candidate_count": 1},
    )

    assert result == "saved"
    assert [row.candidate_id for row in captured["candidates"]] == [
        "old-zoo",
        "new-acm",
    ]
    assert captured["collection"]["collection_scope_listing_urls"] == [
        "https://acm/list"
    ]
    assert captured["collection"]["collected_scope_candidate_count"] == 1
    assert captured["collection"]["preserved_out_of_scope_candidate_count"] == 1
    assert captured["collection"]["candidate_count"] == 2


def test_scoped_zero_result_removes_stale_rows_only_for_active_page(monkeypatch) -> None:
    store = FakeStore()
    captured = {}

    def base(active_store, candidates, collection):
        captured["candidates"] = candidates
        return "saved"

    monkeypatch.setattr(authority, "_BASE_REPLACE_EVENTS", base)
    authority.replace_events(store, [], {"candidate_count": 0})

    assert [row.candidate_id for row in captured["candidates"]] == ["old-zoo"]


def test_scope_authority_is_installed_before_effective_field_wrapper() -> None:
    dynamic = read_text("surface/local_events_runtime/dynamic_listing_authority.py")
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    assert "apply_review_collection_scope()" in dynamic
    assert bootstrap.index("apply_dynamic_listing_authority()") < bootstrap.index(
        "apply_review_effective_fields_authority()"
    )
