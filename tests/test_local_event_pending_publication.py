from __future__ import annotations

import json
import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ReviewState,
)
from local_events_runtime.review_publish_authority import merge_review_state  # noqa: E402


ACM_LISTING = "https://www.acm.nhb.gov.sg/whats-on/overview"


def store_at(tmp_path) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "acm",
                        "name": "Asian Civilisations Museum",
                        "official_home": "https://www.acm.nhb.gov.sg/",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return EventReviewStore(tmp_path / "env" / "local_event_review", config)


def candidate(index: int, decision: str) -> EventCandidate:
    detail_url = f"https://www.acm.nhb.gov.sg/whats-on/exhibitions/acm-event-{index}"
    complete = index < 2
    return EventCandidate(
        candidate_id=f"acm-event-{index}",
        source_id="acm",
        source_name="Asian Civilisations Museum",
        listing_url=ACM_LISTING,
        detail_url=detail_url,
        title=f"ACM Event {index}",
        when="19 June 2026 – 24 January 2027" if complete else "",
        where="Design Gallery on Level 3" if complete else "",
        summary="Official activity description." if complete else "",
        detail_status="collected" if complete else "incomplete",
        detail_error="" if complete else "past_date",
        evidence=EventEvidence(
            selector="div.a-listing-content__content",
            selector_index=index,
            selector_match_count=6,
            document_position={"x": 0, "y": index * 100, "width": 348, "height": 589},
            viewport_position={"x": 0, "y": 0, "width": 348, "height": 589},
            page_index=0,
            page_url=ACM_LISTING,
            text=f"ACM Event {index}",
        ),
        decision=decision,
        collected_at="2026-07-23T00:00:00+00:00",
    )


def collector_row(index: int) -> dict:
    return {
        "title": f"ACM Event {index}",
        "when": "19 June 2026 – 24 January 2027",
        "where": "Design Gallery on Level 3",
        "source_name": "Asian Civilisations Museum",
        "url": f"https://www.acm.nhb.gov.sg/whats-on/exhibitions/acm-event-{index}",
        "summary": "Official activity description.",
        "candidate_policy": "official-listing-authority-v1",
    }


def test_two_confirmed_and_four_pending_acm_candidates_publish_six_rows(tmp_path) -> None:
    store = store_at(tmp_path)
    state = ReviewState(
        events=[
            candidate(index, "confirmed" if index < 2 else "pending")
            for index in range(6)
        ]
    )
    collector = {"ok": True, "results": [collector_row(0), collector_row(1)]}

    payload = merge_review_state(collector, store, state)

    assert payload["count"] == 6
    assert [row["title"] for row in payload["results"]] == [
        "ACM Event 0",
        "ACM Event 1",
        "ACM Event 2",
        "ACM Event 3",
        "ACM Event 4",
        "ACM Event 5",
    ]
    assert payload["review_publish"]["confirmed_count"] == 2
    assert payload["review_publish"]["pending_count"] == 4
    assert payload["review_publish"]["pending_added"] == 4
    assert all(
        row["operator_review_decision"] == "pending"
        for row in payload["results"][2:]
    )
    assert all(row["detail_status"] == "incomplete" for row in payload["results"][2:])


def test_pending_candidate_does_not_replace_existing_collector_fields(tmp_path) -> None:
    store = store_at(tmp_path)
    pending = candidate(2, "pending")
    collector = {"ok": True, "results": [collector_row(2)]}

    payload = merge_review_state(collector, store, ReviewState(events=[pending]))

    assert payload["results"] == collector["results"]
    assert payload["review_publish"]["pending_existing"] == 1


def test_not_related_still_suppresses_matching_collector_row(tmp_path) -> None:
    store = store_at(tmp_path)
    rejected = candidate(2, "rejected")
    collector = {"ok": True, "results": [collector_row(2)]}

    payload = merge_review_state(collector, store, ReviewState(events=[rejected]))

    assert payload["results"] == []
    assert payload["review_publish"]["suppressed"] == 1
