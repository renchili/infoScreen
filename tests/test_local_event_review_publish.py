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
from local_events_runtime.review_publish_authority import (  # noqa: E402
    publish_review_state,
)


MANDAI_LISTING = "https://www.mandai.com/en/discover-mandai/events.html"


def candidate(
    candidate_id: str,
    title: str,
    when: str,
    decision: str,
    *,
    source_id: str = "mandai",
    source_name: str = "Mandai Wildlife Group",
    listing_url: str = MANDAI_LISTING,
    detail_url: str = MANDAI_LISTING,
    where: str = "Singapore Zoo",
    summary: str | None = None,
    evidence_text: str | None = None,
) -> EventCandidate:
    return EventCandidate(
        candidate_id=candidate_id,
        source_id=source_id,
        source_name=source_name,
        listing_url=listing_url,
        detail_url=detail_url,
        title=title,
        when=when,
        where=where,
        summary=(
            summary
            if summary is not None
            else f"Official listing description for {title}."
        ),
        detail_status="collected",
        evidence=EventEvidence(
            selector="article.event-card",
            selector_index=0,
            selector_match_count=12,
            document_position={"x": 100, "y": 500, "width": 800, "height": 300},
            viewport_position={"x": 100, "y": 200, "width": 800, "height": 300},
            page_index=0,
            page_url=listing_url,
            text=evidence_text if evidence_text is not None else title,
        ),
        decision=decision,
        collected_at="2026-07-22T00:00:00+00:00",
    )


def store_at(tmp_path) -> EventReviewStore:
    env_dir = tmp_path / "env"
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "childrensmuseum",
                        "name": "Children's Museum Singapore",
                        "official_home": "https://www.childrensmuseum.sg/",
                    },
                    {
                        "id": "nationalgallery",
                        "name": "National Gallery Singapore",
                        "official_home": "https://www.nationalgallery.sg/",
                    },
                    {
                        "id": "mandai",
                        "name": "Mandai Wildlife Group",
                        "official_home": "https://www.mandai.com/",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return EventReviewStore(env_dir / "local_event_review", config)


def test_two_confirmed_listing_only_cards_with_one_url_are_both_published(tmp_path) -> None:
    store = store_at(tmp_path)
    state = ReviewState(
        events=[
            candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed"),
            candidate("feeding-session", "Feeding Session", "Daily · 2:00pm", "confirmed"),
        ]
    )
    store.save(state)

    payload = publish_review_state(store, state)

    assert payload["count"] == 2
    assert [item["title"] for item in payload["results"]] == [
        "Keeper Talk",
        "Feeding Session",
    ]
    assert {item["url"] for item in payload["results"]} == {MANDAI_LISTING}
    assert all(item["listing_only"] is True for item in payload["results"])
    assert all(
        item["review_publish_origin"] == "review_state"
        for item in payload["results"]
    )


def test_rejected_decision_removes_only_that_confirmed_candidate(tmp_path) -> None:
    store = store_at(tmp_path)
    state = ReviewState(
        events=[
            candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed"),
            candidate("feeding-session", "Feeding Session", "Daily · 2:00pm", "confirmed"),
        ]
    )
    store.save(state)
    assert publish_review_state(store, state)["count"] == 2

    state.events[0].decision = "rejected"
    store.save(state)
    payload = publish_review_state(store, state)

    assert payload["count"] == 1
    assert payload["results"][0]["review_candidate_id"] == "feeding-session"


def test_confirmed_state_replaces_partial_crawler_results(tmp_path) -> None:
    store = store_at(tmp_path)
    runtime_path = store.root.parent / "local_event_search_results.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(
            {
                "ok": True,
                "count": 6,
                "partial": True,
                "results": [
                    {
                        "title": f"Children's Museum activity {index}",
                        "source_name": "Children's Museum Singapore",
                        "url": f"https://www.childrensmuseum.sg/activity-{index}",
                    }
                    for index in range(6)
                ],
            }
        ),
        encoding="utf-8",
    )
    state = ReviewState(
        events=[
            candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed"),
            candidate(
                "singapore-stories",
                "Singapore Stories",
                "Ongoing",
                "confirmed",
                source_id="nationalgallery",
                source_name="National Gallery Singapore",
                listing_url="https://www.nationalgallery.sg/sg/en/whats-on.html",
                detail_url="https://www.nationalgallery.sg/sg/en/exhibitions/singapore-stories.html",
                where="City Hall Wing, Level 2",
            ),
        ]
    )
    store.save(state)

    payload = publish_review_state(store, state)

    assert payload["write_policy"] == "review_state_authoritative"
    assert payload["partial"] is False
    assert payload["count"] == 2
    assert {item["source_name"] for item in payload["results"]} == {
        "Mandai Wildlife Group",
        "National Gallery Singapore",
    }
    assert all(
        item["source_name"] != "Children's Museum Singapore"
        for item in payload["results"]
    )


def test_confirmed_candidate_with_missing_detail_fields_is_still_published(tmp_path) -> None:
    store = store_at(tmp_path)
    state = ReviewState(
        events=[
            candidate(
                "listing-only",
                "",
                "",
                "confirmed",
                where="",
                summary="",
                evidence_text="Animal Feeding Session\nLocation\nSingapore Zoo",
            )
        ]
    )
    store.save(state)

    payload = publish_review_state(store, state)
    event = payload["results"][0]

    assert payload["count"] == 1
    assert event["title"] == "Animal Feeding Session"
    assert event["when"] == ""
    assert event["where"] == "Mandai Wildlife Group"
    assert event["url"] == MANDAI_LISTING
    assert event["listing_only"] is True


def test_http_bootstrap_installs_authoritative_review_publication() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    assert "review_publish_authority" in bootstrap
    assert "apply_review_publish_authority()" in bootstrap


def test_surface_refreshes_runtime_without_redrawing_unchanged_content() -> None:
    script = read_text("surface/web/assets/js/local_event_card.js")

    assert "var dataSignature = null" in script
    assert "if (nextSignature === dataSignature) return false" in script
    assert "apply(data, true)" in script
    assert "setInterval(load, 15000)" in script
    assert "var currentKey = preserveCurrent" in script
