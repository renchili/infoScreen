from __future__ import annotations

import base64
import copy
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
from local_events_runtime.manual_listing import (  # noqa: E402
    ManualListingRequest,
    add_manual_listing,
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


def _install_base_decision(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_SET_LISTING_DECISION",
        EventReviewStore.set_listing_decision,
    )


def test_preview_decisions_are_committed_with_same_request_rollback(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    payload = _review_payload(listing)
    _install_base_decision(monkeypatch)

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


def test_failed_list_page_write_rolls_back_new_preview_selection(
    monkeypatch,
    tmp_path,
) -> None:
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


def test_failed_plain_reset_restores_existing_preview_selection(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    _install_base_decision(monkeypatch)
    authority._set_listing_decision(
        store,
        _protocol(_review_payload(listing)),
        "confirmed",
    )
    snapshot = authority._selection_path(store).read_bytes()

    def fail_decision(*args, **kwargs):
        raise RuntimeError("state write failed")

    monkeypatch.setattr(authority, "_BASE_SET_LISTING_DECISION", fail_decision)
    with pytest.raises(RuntimeError, match="state write failed"):
        authority._set_listing_decision(store, listing.candidate_id, "pending")

    assert authority._selection_path(store).read_bytes() == snapshot
    assert store.load().listing_pages[0].decision == "confirmed"


@pytest.mark.parametrize("decision", ["pending", "rejected"])
def test_plain_reset_or_reject_discards_stale_real_event_selection(
    monkeypatch,
    tmp_path,
    decision,
) -> None:
    store, listing = _store(tmp_path)
    _install_base_decision(monkeypatch)
    authority._set_listing_decision(
        store,
        _protocol(_review_payload(listing)),
        "confirmed",
    )

    state = authority._set_listing_decision(store, listing.candidate_id, decision)

    assert state.listing_pages[0].decision == decision
    assert listing.url not in authority._load(store)["listings"]
    with pytest.raises(ValueError, match="REAL EVENT / NOT EVENT"):
        authority._set_listing_decision(store, listing.candidate_id, "confirmed")


def test_readding_same_page_starts_fresh_review_without_stale_selection(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    _install_base_decision(monkeypatch)
    authority._set_listing_decision(
        store,
        _protocol(_review_payload(listing)),
        "confirmed",
    )

    state = add_manual_listing(
        store,
        ManualListingRequest(source_id="artscience", url=listing.url),
    )

    assert state.listing_pages[0].decision == "pending"
    assert listing.url not in authority._load(store)["listings"]
    with pytest.raises(ValueError, match="REAL EVENT / NOT EVENT"):
        authority._set_listing_decision(store, listing.candidate_id, "confirmed")


def test_direct_list_page_confirmation_is_rejected_without_real_event_selection(
    monkeypatch,
    tmp_path,
) -> None:
    store, listing = _store(tmp_path)
    _install_base_decision(monkeypatch)

    with pytest.raises(ValueError, match="REAL EVENT / NOT EVENT"):
        authority._set_listing_decision(store, listing.candidate_id, "confirmed")


def test_preview_review_rejects_unclassified_candidate(tmp_path) -> None:
    store, listing = _store(tmp_path)
    payload = _review_payload(listing)
    payload["decisions"][0]["decision"] = "pending"

    with pytest.raises(ValueError, match="every Preview candidate"):
        authority._validated_review(store, payload, "confirmed")


def test_preview_review_rejects_duplicate_candidate_identity(tmp_path) -> None:
    store, listing = _store(tmp_path)
    payload = _review_payload(listing)
    payload["decisions"].append(copy.deepcopy(payload["decisions"][0]))

    with pytest.raises(ValueError, match="duplicate or missing"):
        authority._validated_review(store, payload, "confirmed")


def test_preview_review_rejects_mismatched_candidate_identity(tmp_path) -> None:
    store, listing = _store(tmp_path)
    payload = _review_payload(listing)
    payload["decisions"][0]["candidate_id"] = "wrong-candidate"

    with pytest.raises(ValueError, match="does not match"):
        authority._validated_review(store, payload, "confirmed")


def test_preview_review_rejects_original_or_final_url_outside_allow_list(tmp_path) -> None:
    store, listing = _store(tmp_path)

    original = _review_payload(listing)
    original["decisions"][0]["listing_detail_url"] = "https://example.com/original"
    with pytest.raises(ValueError, match="listing URL is outside"):
        authority._validated_review(store, original, "confirmed")

    final = _review_payload(listing)
    final["decisions"][0]["detail_url"] = "https://example.com/final"
    with pytest.raises(ValueError, match="detail URL is outside"):
        authority._validated_review(store, final, "confirmed")


def test_list_page_decision_must_agree_with_real_event_count(tmp_path) -> None:
    store, listing = _store(tmp_path)

    no_real = _review_payload(listing)
    no_real["decisions"][0]["decision"] = "rejected"
    with pytest.raises(ValueError, match="without a REAL EVENT"):
        authority._validated_review(store, no_real, "confirmed")

    has_real = _review_payload(listing)
    with pytest.raises(ValueError, match="rejected List Page"):
        authority._validated_review(store, has_real, "rejected")


def test_legacy_selected_row_without_listing_detail_url_uses_final_url(tmp_path) -> None:
    store, listing = _store(tmp_path)
    detail_url = "https://www.marinabaysands.com/museum/events/legacy.html"
    payload = {
        "listing_candidate_id": listing.candidate_id,
        "listing_url": listing.url,
        "decisions": [
            {
                "candidate_id": stable_id("artscience", listing.url, detail_url),
                "detail_url": detail_url,
                "decision": "confirmed",
            }
        ],
    }

    _, _, rows = authority._validated_review(store, payload, "confirmed")

    assert rows[0]["listing_detail_url"] == detail_url
    assert rows[0]["detail_url"] == detail_url


def test_formal_collection_filters_cards_before_detail_navigation() -> None:
    source = inspect.getsource(authority.collect_event_candidates)

    assert "selected_listing_card" in source
    assert "_source_overrides._listing_card = selected_listing_card" in source
    assert "candidate_id in selected_ids" in source
    assert "canonical_detail in selected_urls" in source
    assert 'item.decision = "confirmed"' in source
    assert '"preview_selection_policy": "confirmed_preview_events_only"' in source
