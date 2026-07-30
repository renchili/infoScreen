from __future__ import annotations

import base64
import inspect
import json
import sys

import pytest

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_event_selection_authority as authority  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
    stable_id,
    utc_now,
)


def _store(tmp_path) -> tuple[EventReviewStore, ListingPageCandidate]:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "artscience",
                        "name": "ArtScience Museum",
                        "official_home": "https://www.marinabaysands.com/museum.html",
                        "allowed_domains": ["marinabaysands.com"],
                        "listing_urls": [
                            "https://www.marinabaysands.com/museum/whats-on.html"
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = EventReviewStore(tmp_path / "review", config)
    listing_url = "https://www.marinabaysands.com/museum/whats-on.html"
    listing = ListingPageCandidate(
        candidate_id=stable_id("artscience", listing_url),
        source_id="artscience",
        source_name="ArtScience Museum",
        url=listing_url,
        origin="configured",
        discovered_at=utc_now(),
    )
    store.save(ReviewState(listing_pages=[listing]))
    return store, listing


def _protocol(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return "preview-review-v1:" + token


def _review_payload(listing: ListingPageCandidate) -> dict:
    real_listing_url = (
        "https://www.marinabaysands.com/museum/exhibitions/"
        "into-the-ocean-redirect.html"
    )
    real_url = "https://www.marinabaysands.com/museum/exhibitions/into-the-ocean.html"
    rejected_url = "https://www.marinabaysands.com/museum/events/example.html"
    return {
        "listing_candidate_id": listing.candidate_id,
        "listing_url": listing.url,
        "decisions": [
            {
                "candidate_id": stable_id(
                    "artscience",
                    listing.url,
                    real_listing_url,
                ),
                "listing_detail_url": real_listing_url,
                "detail_url": real_url,
                "decision": "confirmed",
            },
            {
                "candidate_id": stable_id("artscience", listing.url, rejected_url),
                "detail_url": rejected_url,
                "decision": "rejected",
            },
        ],
    }


def test_preview_decisions_are_committed_atomically_with_list_page_confirmation(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    payload = _review_payload(listing)
    monkeypatch.setattr(
        authority,
        "_BASE_SET_LISTING_DECISION",
        EventReviewStore.set_listing_decision,
    )

    state = authority._set_listing_decision(
        store,
        _protocol(payload),
        "confirmed",
    )

    assert state.listing_pages[0].decision == "confirmed"
    saved = authority._load(store)["listings"][listing.url]
    assert [row["decision"] for row in saved["decisions"]] == [
        "confirmed",
        "rejected",
    ]
    assert saved["decisions"][0]["listing_detail_url"] == (
        payload["decisions"][0]["listing_detail_url"]
    )
    assert saved["decisions"][0]["detail_url"] == payload["decisions"][0]["detail_url"]

    selected_ids, selected_urls, skipped = authority._confirmed_selections(store)
    assert skipped == []
    assert payload["decisions"][0]["candidate_id"] in selected_ids[listing.url]
    assert payload["decisions"][0]["listing_detail_url"] in selected_urls[listing.url]
    assert payload["decisions"][0]["detail_url"] in selected_urls[listing.url]


def test_failed_list_page_write_rolls_back_preview_selection(monkeypatch, tmp_path) -> None:
    store, listing = _store(tmp_path)

    def fail_decision(*args, **kwargs):
        raise RuntimeError("state write failed")

    monkeypatch.setattr(authority, "_BASE_SET_LISTING_DECISION", fail_decision)

    with pytest.raises(RuntimeError, match="state write failed"):
        authority._set_listing_decision(
            store,
            _protocol(_review_payload(listing)),
            "confirmed",
        )

    assert authority._selection_path(store).exists() is False
    assert store.load().listing_pages[0].decision == "pending"


def test_direct_list_page_confirmation_is_rejected_without_real_event_selection(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    monkeypatch.setattr(
        authority,
        "_BASE_SET_LISTING_DECISION",
        EventReviewStore.set_listing_decision,
    )

    with pytest.raises(ValueError, match="REAL EVENT / NOT EVENT"):
        authority._set_listing_decision(store, listing.candidate_id, "confirmed")


def test_formal_collection_filters_cards_before_detail_navigation() -> None:
    source = inspect.getsource(authority.collect_event_candidates)

    assert "selected_listing_card" in source
    assert "_source_overrides._listing_card = selected_listing_card" in source
    assert "candidate_id in selected_ids" in source
    assert "canonical_detail in selected_urls" in source
    assert 'item.decision = "confirmed"' in source
    assert '"preview_selection_policy": "confirmed_preview_events_only"' in source
