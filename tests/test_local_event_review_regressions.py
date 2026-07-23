from __future__ import annotations

import json
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ReviewState,
)


def candidate(candidate_id: str, title: str) -> EventCandidate:
    return EventCandidate(
        candidate_id=candidate_id,
        source_id="gardensbythebay",
        source_name="Gardens by the Bay",
        listing_url="https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html",
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
            page_url="https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html",
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


def test_review_scroll_guard_restores_the_operated_card() -> None:
    script = read_text("surface/web/assets/js/local_event_review_scroll_guard.js")

    assert "function cardKey(card)" in script
    assert "viewportTop: card.getBoundingClientRect().top" in script
    assert "target.getBoundingClientRect().top - saved.viewportTop" in script
    assert '"#listing-pages button, #event-candidates button"' in script
    assert "visibleIndex" in script
