from __future__ import annotations

import json
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))
import serve_infoscreen  # noqa: E402
from local_events_runtime import browser as browser_runtime  # noqa: E402
from local_events_runtime import detail_date_authority as detail_dates  # noqa: E402
from local_events_runtime import event_review as event_review_module  # noqa: E402
from local_events_runtime import event_review_diagnostics as diagnostics  # noqa: E402
from local_events_runtime import http1_browser  # noqa: E402
from local_events_runtime import review_effective_fields_authority as effective  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventFeedback,
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
)


LISTING_URL = "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html"


def candidate(candidate_id: str, title: str) -> EventCandidate:
    return EventCandidate(
        candidate_id=candidate_id,
        source_id="gardensbythebay",
        source_name="Gardens by the Bay",
        listing_url=LISTING_URL,
        detail_url=(
            "https://www.gardensbythebay.com.sg/en/things-to-do/"
            f"calendar-of-events/{candidate_id}.html"
        ),
        title=title,
        when="3 Jul - 10 Aug 2026",
        where="Flower Dome",
        summary="Official activity description.",
        detail_status="collected",
        evidence=EventEvidence(
            selector="a.programme-title.row-listing-title",
            selector_index=0,
            selector_match_count=12,
            document_position={"x": 180, "y": 926, "width": 1080, "height": 325},
            viewport_position={"x": 180, "y": 226, "width": 1080, "height": 325},
            page_index=0,
            page_url=LISTING_URL,
            text=title,
        ),
        collected_at="2026-07-22T00:00:00+00:00",
    )


def test_event_decision_updates_only_the_requested_candidate(tmp_path) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)
    store.save(
        ReviewState(
            events=[
                candidate("orchid-extravaganza-2026", "Orchid Extravaganza"),
                candidate("another-activity", "Another Activity"),
            ]
        )
    )

    updated = store.set_event_decision("orchid-extravaganza-2026", "rejected")
    decisions = {item.candidate_id: item.decision for item in updated.events}

    assert decisions == {
        "orchid-extravaganza-2026": "rejected",
        "another-activity": "pending",
    }


def test_pending_listing_preview_uses_isolated_confirmed_copy(
    monkeypatch,
    tmp_path,
) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)

    original = ReviewState(
        listing_pages=[
            ListingPageCandidate(
                candidate_id="pending-listing",
                source_id="gardensbythebay",
                source_name="Gardens by the Bay",
                url=LISTING_URL,
                origin="configured",
                decision="pending",
                discovered_at="2026-07-28T00:00:00+00:00",
            )
        ],
        events=[candidate("persisted-event", "Persisted Event")],
        feedback=[
            EventFeedback(
                feedback_id="persisted-feedback",
                source_id="gardensbythebay",
                source_name="Gardens by the Bay",
                listing_url=LISTING_URL,
                page_url=LISTING_URL,
                selector="article.event-card",
                selector_index=0,
                selector_match_count=1,
                document_position={"x": 1, "y": 2, "width": 3, "height": 4},
                text="Persisted feedback",
                created_at="2026-07-28T00:00:00+00:00",
            )
        ],
        listing_collection={"preserve": "listing"},
        event_collection={"preserve": "events"},
    )
    store.save(original)

    def fake_collect(temporary_store: EventReviewStore) -> ReviewState:
        copied = temporary_store.load()
        assert len(copied.listing_pages) == 1
        assert copied.listing_pages[0].decision == "confirmed"
        assert copied.events == []
        assert copied.feedback == []
        assert copied.event_collection == {}
        copied.events = [candidate("preview-event", "Preview Event")]
        copied.event_collection = {"preview": True}
        return temporary_store.save(copied)

    monkeypatch.setattr(serve_infoscreen, "collect_event_candidates", fake_collect)

    preview = serve_infoscreen.preview_event_candidates(store, LISTING_URL)
    persisted = store.load()

    assert preview.listing_pages[0].decision == "confirmed"
    assert [item.candidate_id for item in preview.events] == ["preview-event"]
    assert preview.event_collection == {"preview": True}
    assert persisted.model_dump(mode="json") == original.model_dump(mode="json")


def test_pending_preview_uses_scoped_listing_runtime_without_detail_pages(
    monkeypatch,
    tmp_path,
) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)
    store.save(
        ReviewState(
            listing_pages=[
                ListingPageCandidate(
                    candidate_id="pending-listing",
                    source_id="gardensbythebay",
                    source_name="Gardens by the Bay",
                    url=LISTING_URL,
                    origin="configured",
                    decision="pending",
                    discovered_at="2026-07-28T00:00:00+00:00",
                )
            ]
        )
    )

    detail_url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/"
        "calendar-of-events/preview-only.html"
    )
    observed: dict[str, str] = {}
    runtime_names = (
        "CARD_JS",
        "MAX_LISTING_PAGES",
        "LOAD_MORE_ROUNDS",
        "NAV_TIMEOUT_MS",
        "DOM_TIMEOUT_MS",
        "PREPARE_PAGE_JS",
    )
    original_runtime = {
        name: getattr(browser_runtime, name)
        for name in runtime_names
    }

    class NoDetailBrowserContext:
        def new_page(self):
            raise AssertionError("pending preview must not open a detail page")

    monkeypatch.setattr(
        detail_dates,
        "_listing_fields",
        lambda source, card: {
            "title": "Listing Preview Event",
            "when": "3 Jul - 10 Aug 2026",
            "where": "Flower Dome",
            "summary": "Listing card summary.",
        },
    )

    def fake_diagnostic_collect(temporary_store: EventReviewStore) -> ReviewState:
        assert browser_runtime.CARD_JS == http1_browser.PREVIEW_CARD_JS
        assert browser_runtime.MAX_LISTING_PAGES == 1
        assert browser_runtime.LOAD_MORE_ROUNDS == 0
        assert browser_runtime.NAV_TIMEOUT_MS == http1_browser.PREVIEW_NAV_TIMEOUT_MS
        assert browser_runtime.DOM_TIMEOUT_MS == http1_browser.PREVIEW_DOM_TIMEOUT_MS
        assert browser_runtime.PREPARE_PAGE_JS == http1_browser.PREVIEW_PREPARE_PAGE_JS

        result = event_review_module._detail_candidate(
            NoDetailBrowserContext(),
            {
                "id": "gardensbythebay",
                "name": "Gardens by the Bay",
                "allowed_domains": ["gardensbythebay.com.sg"],
            },
            LISTING_URL,
            detail_url,
            {},
        )
        observed.update(result)
        return temporary_store.load()

    monkeypatch.setattr(diagnostics, "collect_event_candidates", fake_diagnostic_collect)

    preview = serve_infoscreen.preview_event_candidates(store, LISTING_URL)

    assert observed == {
        "detail_url": detail_url,
        "title": "Listing Preview Event",
        "when": "3 Jul - 10 Aug 2026",
        "where": "Flower Dome",
        "summary": "Listing card summary.",
        "detail_status": "incomplete",
        "detail_error": "preview_listing_evidence_only",
        "detail_page_title": "",
    }
    assert preview.event_collection["preview_detail_mode"] == "listing_evidence_only"
    assert preview.event_collection["preview_listing_mode"] == "single_page_linear_main_dom"
    assert preview.event_collection["preview_card_mode"] == "cached_linear_main_content"
    assert event_review_module._detail_candidate is effective.detail_candidate
    assert {
        name: getattr(browser_runtime, name)
        for name in runtime_names
    } == original_runtime


def test_preview_card_extractor_avoids_document_wide_rescoring() -> None:
    script = http1_browser.PREVIEW_CARD_JS

    assert 'document.querySelector("main")' in script
    assert 'root.querySelectorAll("a[href]")' in script
    assert 'document.querySelectorAll("a[href]")' not in script
    assert "new WeakMap()" in script
    assert "candidates.sort" not in script
    assert "JSON.parse" not in script


def test_review_scroll_guard_restores_the_operated_card() -> None:
    script = read_text("surface/web/assets/js/local_event_review_scroll_guard.js")

    assert "function cardKey(card)" in script
    assert "viewportTop: card.getBoundingClientRect().top" in script
    assert "target.getBoundingClientRect().top - saved.viewportTop" in script
    assert '"#listing-pages button, #event-candidates button"' in script
    assert "visibleIndex" in script
