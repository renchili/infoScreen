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
    merge_review_state,
    publish_review_state,
)

MANDAI_LISTING = "https://www.mandai.com/en/discover-mandai/events.html"
VERIFIED_POLICY = "official-listing-authority-v1"


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


def system_event(index: int = 1) -> dict:
    return {
        "title": f"Children's Museum activity {index}",
        "when": "Ongoing",
        "where": "Children's Museum Singapore",
        "host": "Children's Museum Singapore",
        "source_name": "Children's Museum Singapore",
        "url": f"https://www.childrensmuseum.sg/activity-{index}",
        "summary": "System-collected activity.",
        "candidate_policy": VERIFIED_POLICY,
        "source_type": "official_listing_card",
    }


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


def test_confirmed_events_are_added_without_replacing_collector_rows(tmp_path) -> None:
    store = store_at(tmp_path)
    runtime_path = store.root.parent / "local_event_search_results.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps({"ok": True, "partial": True, "results": [system_event(i) for i in range(6)]}),
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

    assert payload["count"] == 8
    assert payload["results"][:6] == [system_event(i) for i in range(6)]
    assert {item["source_name"] for item in payload["results"][6:]} == {
        "Mandai Wildlife Group",
        "National Gallery Singapore",
    }
    assert payload["review_publish"]["mode"] == "overlay_on_collector_results"


def test_rejected_decision_removes_only_review_row(tmp_path) -> None:
    store = store_at(tmp_path)
    runtime_path = store.root.parent / "local_event_search_results.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps({"ok": True, "results": [system_event()]}),
        encoding="utf-8",
    )
    state = ReviewState(
        events=[candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed")]
    )
    store.save(state)
    assert publish_review_state(store, state)["count"] == 2

    state.events[0].decision = "rejected"
    store.save(state)
    payload = publish_review_state(store, state)

    assert payload["count"] == 1
    assert payload["results"] == [system_event()]


def test_system_event_with_same_detail_url_is_not_duplicated(tmp_path) -> None:
    store = store_at(tmp_path)
    detail_url = "https://www.nationalgallery.sg/sg/en/exhibitions/singapore-stories.html"
    system = {
        "title": "Singapore Stories",
        "when": "Ongoing",
        "where": "City Hall Wing, Level 2",
        "source_name": "National Gallery Singapore",
        "url": detail_url,
        "candidate_policy": VERIFIED_POLICY,
    }
    state = ReviewState(
        events=[
            candidate(
                "singapore-stories",
                "Singapore Stories",
                "Ongoing",
                "confirmed",
                source_id="nationalgallery",
                source_name="National Gallery Singapore",
                listing_url="https://www.nationalgallery.sg/sg/en/whats-on.html",
                detail_url=detail_url,
                where="City Hall Wing, Level 2",
            )
        ]
    )

    payload = merge_review_state({"results": [system]}, store, state)

    assert payload["results"] == [system]
    assert payload["review_publish"]["already_present"] == 1


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

    event = publish_review_state(store, state)["results"][0]

    assert event["title"] == "Animal Feeding Session"
    assert event["when"] == ""
    assert event["where"] == "Mandai Wildlife Group"
    assert event["url"] == MANDAI_LISTING
    assert event["listing_only"] is True


def test_http_bootstrap_installs_coverage_and_review_authorities() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    assert "complete_collection_authority" in bootstrap
    assert "apply_complete_collection()" in bootstrap
    assert "review_publish_authority" in bootstrap
    assert "apply_review_publish_authority()" in bootstrap


def test_surface_refreshes_runtime_without_redrawing_unchanged_content() -> None:
    script = read_text("surface/web/assets/js/local_event_card.js")

    assert "var dataSignature = null" in script
    assert "if (nextSignature === dataSignature) return false" in script
    assert "apply(data, true)" in script
    assert "setInterval(load, 15000)" in script
    assert "var currentKey = preserveCurrent" in script
