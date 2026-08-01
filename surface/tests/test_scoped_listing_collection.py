from __future__ import annotations

import inspect
import json
import sys

import pytest

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_event_selection_authority as selection  # noqa: E402
from local_events_runtime import scoped_listing_collection as scoped  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
    stable_id,
)
from local_events_runtime.manual_listing import MANUAL_LINK_TEXT  # noqa: E402


def _store(tmp_path) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "alpha",
                        "name": "Alpha Museum",
                        "official_home": "https://alpha.example/",
                        "allowed_domains": ["alpha.example"],
                        "listing_urls": ["https://alpha.example/events"],
                    },
                    {
                        "id": "beta",
                        "name": "Beta Museum",
                        "official_home": "https://beta.example/",
                        "allowed_domains": ["beta.example"],
                        "listing_urls": ["https://beta.example/whats-on"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return EventReviewStore(tmp_path / "review", config)


def _listing(
    source_id: str,
    source_name: str,
    url: str,
    *,
    decision: str = "pending",
    origin: str = "configured",
    link_text: str = "",
) -> ListingPageCandidate:
    return ListingPageCandidate(
        candidate_id=stable_id(source_id, url),
        source_id=source_id,
        source_name=source_name,
        url=url,
        origin=origin,
        link_text=link_text,
        decision=decision,
        discovered_at="2026-07-29T00:00:00+00:00",
    )


def _saved_selection(listing: ListingPageCandidate) -> dict:
    detail_url = listing.url.rstrip("/") + "/event-one"
    return {
        "listing_candidate_id": listing.candidate_id,
        "listing_url": listing.url,
        "reviewed_at": "2026-07-29T01:00:00+00:00",
        "decisions": [
            {
                "candidate_id": stable_id(
                    listing.source_id,
                    listing.url,
                    detail_url,
                ),
                "listing_detail_url": detail_url,
                "detail_url": detail_url,
                "decision": "confirmed",
            }
        ],
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 21_600),
        ("", 21_600),
        ("invalid", 21_600),
        ("-1", 60),
        ("59", 60),
        ("60", 60),
        ("3600", 3600),
    ],
)
def test_preview_manifest_ttl_parser_is_safe(raw, expected) -> None:
    assert selection._preview_manifest_ttl_seconds(raw) == expected


def test_collection_discovers_only_selected_institution_before_confirmation(
    monkeypatch,
    tmp_path,
) -> None:
    store = _store(tmp_path)
    alpha_configured = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/events",
        decision="rejected",
    )
    alpha_manual = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/operator-list",
        origin="discovered",
        link_text=MANUAL_LINK_TEXT,
    )
    beta_confirmed = _listing(
        "beta",
        "Beta Museum",
        "https://beta.example/whats-on",
        decision="confirmed",
    )
    store.save(
        ReviewState(
            listing_pages=[alpha_configured, alpha_manual, beta_confirmed]
        )
    )

    visited: list[str] = []

    def discover(source, candidates, discovered_at, errors):
        visited.append(str(source.get("id")))
        url = "https://alpha.example/programmes"
        candidate_id = stable_id("alpha", url)
        candidates[candidate_id] = _listing(
            "alpha",
            "Alpha Museum",
            url,
            origin="discovered",
        )

    monkeypatch.setattr(scoped, "_discover_home_links", discover)

    state = scoped.collect_listing_pages_for_source(store, "alpha")

    assert visited == ["alpha"]
    assert next(
        row for row in state.listing_pages if row.url == alpha_configured.url
    ).decision == "rejected"
    assert any(row.url == alpha_manual.url for row in state.listing_pages)
    assert next(
        row for row in state.listing_pages if row.url == beta_confirmed.url
    ).decision == "confirmed"
    assert any(
        row.url == "https://alpha.example/programmes"
        for row in state.listing_pages
    )
    assert state.listing_collection["scope"] == (
        "single_institution_before_confirmation"
    )
    assert state.listing_collection["source_id"] == "alpha"


def test_retired_discovery_page_clears_selection_and_requires_new_preview(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(selection, "_PREVIEW_MANIFESTS", {})
    store = _store(tmp_path)
    configured = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/events",
    )
    retired = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/retired-programmes",
        decision="confirmed",
        origin="discovered",
    )
    manual = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/operator-list",
        origin="discovered",
        link_text=MANUAL_LINK_TEXT,
    )
    store.save(ReviewState(listing_pages=[configured, retired, manual]))
    selection._save(
        store,
        {
            "schema_version": 1,
            "listings": {
                retired.url: _saved_selection(retired),
                manual.url: _saved_selection(manual),
            },
        },
    )
    selection._PREVIEW_MANIFESTS[retired.url] = {"candidate": "stale"}

    state = scoped._merge_selected_source(
        store,
        "alpha",
        {configured.candidate_id: configured},
        {"scope": "test"},
    )

    assert retired.url not in {row.url for row in state.listing_pages}
    assert manual.url in {row.url for row in state.listing_pages}
    saved = selection._load(store)["listings"]
    assert retired.url not in saved
    assert manual.url in saved
    assert retired.url not in selection._PREVIEW_MANIFESTS

    reappeared = retired.model_copy(
        update={"decision": "pending", "reviewed_at": None}
    )
    scoped._merge_selected_source(
        store,
        "alpha",
        {
            configured.candidate_id: configured,
            reappeared.candidate_id: reappeared,
        },
        {"scope": "test-reappeared"},
    )
    with pytest.raises(ValueError, match="REAL EVENT / NOT EVENT"):
        selection._set_listing_decision(
            store,
            reappeared.candidate_id,
            "confirmed",
        )


def test_retired_selection_is_restored_when_review_state_save_fails(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(selection, "_PREVIEW_MANIFESTS", {})
    store = _store(tmp_path)
    configured = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/events",
    )
    retired = _listing(
        "alpha",
        "Alpha Museum",
        "https://alpha.example/retired-programmes",
        decision="confirmed",
        origin="discovered",
    )
    store.save(ReviewState(listing_pages=[configured, retired]))
    selection._save(
        store,
        {
            "schema_version": 1,
            "listings": {retired.url: _saved_selection(retired)},
        },
    )
    snapshot = selection._selection_path(store).read_bytes()
    selection._PREVIEW_MANIFESTS[retired.url] = {"candidate": "retryable"}

    def fail_save(state):
        raise RuntimeError("state write failed")

    monkeypatch.setattr(store, "save", fail_save)

    with pytest.raises(RuntimeError, match="state write failed"):
        scoped._merge_selected_source(
            store,
            "alpha",
            {configured.candidate_id: configured},
            {"scope": "test"},
        )

    assert selection._selection_path(store).read_bytes() == snapshot
    assert retired.url in selection._PREVIEW_MANIFESTS
    assert retired.url in {row.url for row in store.load().listing_pages}


def test_retired_discovery_pages_clear_preview_selection_with_rollback() -> None:
    source = inspect.getsource(scoped._merge_selected_source)

    assert "removed_urls = sorted(" in source
    assert "item.link_text != MANUAL_LINK_TEXT" in source
    assert "selection_snapshot = selection._selection_snapshot(store)" in source
    assert "del listings[url]" in source
    assert "selection._save(store, selections)" in source
    assert "selection._restore_selection_snapshot(store, selection_snapshot)" in source
    assert "selection.invalidate_preview_manifest(url)" in source
    assert source.index("selection._save(store, selections)") < source.index(
        "saved = store.save(state)"
    ) < source.index("selection.invalidate_preview_manifest(url)")


def test_scoped_discovery_never_waits_for_network_idle() -> None:
    source = inspect.getsource(scoped._discover_home_links)

    assert 'wait_until="domcontentloaded"' in source
    assert 'wait_until="networkidle"' not in source
    assert "DISCOVERY_TIMEOUT_MS = 20_000" in inspect.getsource(scoped)


def test_studio_and_http_endpoint_require_selected_source_id() -> None:
    frontend = read_text(
        "surface/web/assets/js/local_event_review_scoped_listing_collection.js"
    )
    server = read_text("surface/serve_infoscreen.py")
    html = read_text("surface/web/local-events/studio/index.html")

    assert "selectedSourceId" in frontend
    assert 'body: JSON.stringify({source_id: sourceId})' in frontend
    assert "SELECT ONE INSTITUTION BEFORE COLLECTING LIST PAGES" in frontend
    assert 'source_id = str(body.get("source_id") or "").strip()' in server
    assert "collect_listing_pages_for_source" in server
    assert "state = collect_listing_pages_for_source(" in server
    assert "state = collect_listing_pages(review_store())" not in server
    assert (
        '<script src="/assets/js/local_event_review_scoped_listing_collection.js" defer></script>'
        in html
    )
