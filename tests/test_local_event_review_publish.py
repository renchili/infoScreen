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
) -> EventCandidate:
    return EventCandidate(
        candidate_id=candidate_id,
        source_id="mandai",
        source_name="Mandai Wildlife Group",
        listing_url=MANDAI_LISTING,
        detail_url=MANDAI_LISTING,
        title=title,
        when=when,
        where="Singapore Zoo",
        summary=f"Official listing description for {title}.",
        detail_status="collected",
        evidence=EventEvidence(
            selector="article.event-card",
            selector_index=0,
            selector_match_count=12,
            document_position={"x": 100, "y": 500, "width": 800, "height": 300},
            viewport_position={"x": 100, "y": 200, "width": 800, "height": 300},
            page_index=0,
            page_url=MANDAI_LISTING,
            text=title,
        ),
        decision=decision,
        collected_at="2026-07-22T00:00:00+00:00",
    )


def store_at(tmp_path) -> EventReviewStore:
    env_dir = tmp_path / "env"
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
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


def test_rejected_decision_removes_only_previously_published_review_row(tmp_path) -> None:
    store = store_at(tmp_path)
    confirmed = ReviewState(
        events=[candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed")]
    )
    store.save(confirmed)
    first = publish_review_state(store, confirmed)
    assert first["count"] == 1
    assert first["results"][0]["review_publish_origin"] == "review_state"

    rejected = ReviewState(
        events=[candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "rejected")]
    )
    store.save(rejected)
    second = publish_review_state(store, rejected)

    assert second["count"] == 0
    persisted = json.loads(
        (store.root.parent / "local_event_search_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["results"] == []
    assert persisted["review_publish"]["confirmed_count"] == 0


def test_publish_does_not_revalidate_or_delete_unrelated_runtime_rows(tmp_path) -> None:
    store = store_at(tmp_path)
    runtime_path = store.root.parent / "local_event_search_results.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    unrelated = {
        "title": "Existing correct activity",
        "when": "Ongoing",
        "where": "Gallery 2",
        "host": "Existing source",
        "source_name": "Existing source",
        "url": "https://example.org/events.html",
        "summary": "<strong>Preserve this exact system row.</strong>",
        "operator_review_decision": "confirmed",
        "source_type": "official_listing_card",
    }
    runtime_path.write_text(
        json.dumps({"ok": True, "results": [unrelated]}),
        encoding="utf-8",
    )
    state = ReviewState(
        events=[candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed")]
    )
    store.save(state)

    payload = publish_review_state(store, state)

    assert payload["count"] == 2
    assert payload["results"][0] == unrelated
    assert payload["results"][1]["title"] == "Keeper Talk"


def test_existing_system_event_is_not_overwritten_or_removed(tmp_path) -> None:
    store = store_at(tmp_path)
    runtime_path = store.root.parent / "local_event_search_results.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(
            {
                "ok": True,
                "results": [
                    {
                        "title": "Keeper Talk",
                        "when": "Daily · 10:30am",
                        "where": "Singapore Zoo",
                        "host": "Mandai Wildlife Group",
                        "source_name": "Mandai Wildlife Group",
                        "url": MANDAI_LISTING,
                        "summary": "System-collected description.",
                        "start_date": "2026-07-22",
                        "kind": "event",
                        "source_type": "official_listing_card_without_detail",
                        "candidate_policy": "official-listing-authority-v1",
                        "listing_url": MANDAI_LISTING,
                        "listing_only": True,
                        "detail_available": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state = ReviewState(
        events=[candidate("keeper-talk", "Keeper Talk", "Daily · 10:30am", "confirmed")]
    )
    store.save(state)

    confirmed = publish_review_state(store, state)
    assert confirmed["count"] == 1
    assert confirmed["results"][0]["summary"] == "System-collected description."
    assert confirmed["review_publish"]["already_present"] == 1

    state.events[0].decision = "rejected"
    store.save(state)
    rejected = publish_review_state(store, state)
    assert rejected["count"] == 1
    assert rejected["results"][0]["source_type"] == "official_listing_card_without_detail"


def test_http_bootstrap_installs_immediate_review_publication() -> None:
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
