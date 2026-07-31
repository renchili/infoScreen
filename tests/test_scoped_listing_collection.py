from __future__ import annotations

import inspect
import json
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

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
