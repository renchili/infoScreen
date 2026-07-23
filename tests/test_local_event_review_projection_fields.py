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


def candidate(detail_url: str) -> EventCandidate:
    return EventCandidate(
        candidate_id="acm-event",
        source_id="acm",
        source_name="Asian Civilisations Museum",
        listing_url="https://www.acm.nhb.gov.sg/whats-on/overview",
        detail_url=detail_url,
        title="Reviewed title",
        when="",
        where="",
        summary="",
        detail_status="incomplete",
        evidence=EventEvidence(
            selector="a.a-listing-content__anchor-card",
            selector_index=0,
            selector_match_count=6,
            document_position={"x": 0, "y": 0, "width": 300, "height": 400},
            viewport_position={"x": 0, "y": 0, "width": 300, "height": 400},
            page_index=0,
            page_url="https://www.acm.nhb.gov.sg/whats-on/overview",
            text="Reviewed title",
        ),
        decision="confirmed",
        collected_at="2026-07-23T00:00:00+00:00",
    )


def test_empty_review_fields_do_not_replace_specific_collector_fields(tmp_path) -> None:
    store = store_at(tmp_path)
    detail_url = "https://www.acm.nhb.gov.sg/whats-on/exhibitions/example"
    collector = {
        "results": [
            {
                "title": "Collector title",
                "when": "19 June 2026 – 24 January 2027",
                "start_date": "2026-06-19",
                "end_date": "2027-01-24",
                "where": "Design Gallery on Level 3",
                "summary": "Specific collector description.",
                "source_name": "Asian Civilisations Museum",
                "url": detail_url,
                "candidate_policy": "official-listing-authority-v1",
            }
        ]
    }
    state = ReviewState(events=[candidate(detail_url)])

    payload = merge_review_state(collector, store, state)
    event = payload["results"][0]

    assert event["title"] == "Reviewed title"
    assert event["when"] == "19 June 2026 – 24 January 2027"
    assert event["start_date"] == "2026-06-19"
    assert event["end_date"] == "2027-01-24"
    assert event["where"] == "Design Gallery on Level 3"
    assert event["summary"] == "Specific collector description."


def test_non_empty_review_date_replaces_complete_collector_date_tuple(tmp_path) -> None:
    store = store_at(tmp_path)
    detail_url = "https://www.acm.nhb.gov.sg/whats-on/exhibitions/example"
    reviewed = candidate(detail_url).model_copy(
        update={"when": "1 July 2026", "decision": "confirmed"}
    )
    collector = {
        "results": [
            {
                "title": "Collector title",
                "when": "19 June 2026 – 24 January 2027",
                "start_date": "2026-06-19",
                "end_date": "2027-01-24",
                "where": "Design Gallery on Level 3",
                "summary": "Specific collector description.",
                "source_name": "Asian Civilisations Museum",
                "url": detail_url,
                "candidate_policy": "official-listing-authority-v1",
            }
        ]
    }

    payload = merge_review_state(collector, store, ReviewState(events=[reviewed]))
    event = payload["results"][0]

    assert event["when"] == "1 July 2026"
    assert event["start_date"] == "2026-07-01"
    assert event["end_date"] == ""
