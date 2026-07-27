from __future__ import annotations

import json
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_review  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as detail_navigation  # noqa: E402
from local_events_runtime import review_effective_fields_authority as authority  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ReviewState,
)


authority.apply()


DETAIL_URL = "https://www.acm.nhb.gov.sg/whats-on/programmes/2026-ltn"


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
                        "default_venue": "Asian Civilisations Museum",
                        "allowed_domains": ["acm.nhb.gov.sg"],
                        "listing_urls": [
                            "https://www.acm.nhb.gov.sg/whats-on/overview"
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return EventReviewStore(tmp_path / "env" / "local_event_review", config)


def evidence() -> EventEvidence:
    return EventEvidence(
        selector="div.a-listing-content__content",
        selector_index=2,
        selector_match_count=6,
        document_position={"x": 881, "y": 466, "width": 348, "height": 589},
        viewport_position={"x": 881, "y": 466, "width": 348, "height": 589},
        page_index=0,
        page_url="https://www.acm.nhb.gov.sg/whats-on/overview",
        text="Light to Night at ACM: Power of Play",
    )


def candidate(
    *,
    when: str = "23, 24, 30, 31 Jan 2027 · 6pm–10pm",
    where: str = "Asian Civilisations Museum, 1 Empress Place, Singapore 179555",
    summary: str = "Experience ACM after dark through the Power of Play.",
    detail_error: str = "",
) -> EventCandidate:
    return EventCandidate(
        candidate_id="acm-2026-ltn",
        source_id="acm",
        source_name="Asian Civilisations Museum",
        listing_url="https://www.acm.nhb.gov.sg/whats-on/overview",
        detail_url=DETAIL_URL,
        title="Light to Night at ACM: Power of Play",
        when=when,
        where=where,
        summary=summary,
        detail_status="collected" if not detail_error else "incomplete",
        detail_error=detail_error,
        detail_page_title="Light to Night at ACM: Power of Play",
        evidence=evidence(),
        decision="pending",
        collected_at="2026-01-20T00:00:00+00:00",
    )


def test_repair_fields_is_exact_passthrough() -> None:
    raw = {
        "title": "Light to Night at ACM: Power of Play",
        "when": "23, 24, 30, 31 Jan 2026 · 6pm–10pm",
        "where": "Asian Civilisations Museum, 1 Empress Place, Singapore 179555",
        "summary": "Collected detail summary",
    }
    runtime = {
        "title": "Different title",
        "when": "Daily - 10am - 7pm",
        "where": "Asian Civilisations Museum",
        "summary": "Different runtime summary",
    }

    assert authority._repair_fields(
        raw,
        runtime_row=runtime,
        source={"default_venue": "Asian Civilisations Museum"},
    ) == raw


def test_state_payload_does_not_backfill_empty_fields(tmp_path) -> None:
    store = store_at(tmp_path)
    exact = candidate(when="", where="", summary="")
    exact.detail_status = "incomplete"
    exact.detail_error = "missing_detail_when_and_where"
    store.save(ReviewState(events=[exact]))

    event = store.state_payload()["events"][0]

    assert event["when"] == ""
    assert event["where"] == ""
    assert event["summary"] == ""
    assert event["detail_status"] == "incomplete"
    assert event["detail_error"] == "missing_detail_when_and_where"


def test_replace_events_persists_exact_collected_fields(tmp_path) -> None:
    store = store_at(tmp_path)
    exact = candidate()

    state = store.replace_events(
        [exact],
        {"completed_at": "now", "candidate_count": 1},
    )

    assert len(state.events) == 1
    assert state.events[0].when == exact.when
    assert state.events[0].where == exact.where
    assert state.events[0].summary == exact.summary

    persisted = store.load().events[0]
    assert persisted.when == exact.when
    assert persisted.where == exact.where
    assert persisted.summary == exact.summary


def test_past_exact_date_is_removed_without_field_rewrite(tmp_path) -> None:
    store = store_at(tmp_path)
    past = candidate(
        when="23, 24, 30, 31 Jan 2026 · 6pm–10pm",
        where="Asian Civilisations Museum, 1 Empress Place, Singapore 179555",
    )
    store.save(ReviewState(events=[past]))

    payload = store.state_payload()

    assert payload["events"] == []
    assert payload["event_collection"]["candidate_count"] == 0
    assert payload["event_collection"]["expired_candidate_count"] >= 1


def test_explicit_past_date_error_is_removed_even_when_when_is_empty(tmp_path) -> None:
    store = store_at(tmp_path)
    past = candidate(
        when="",
        where="",
        summary="CHILDREN’S SEASON AT ACM: PLAY ON!",
        detail_error="past_date",
    )

    replaced = store.replace_events(
        [past],
        {"completed_at": "now", "candidate_count": 1},
    )
    assert replaced.events == []
    assert replaced.event_collection["candidate_count"] == 0
    assert replaced.event_collection["expired_candidate_count"] >= 1

    store.save(ReviewState(events=[past]))
    assert store.load().events == []
    assert store.state_payload()["events"] == []


def test_fallback_date_and_detail_time_are_preserved_and_expire(tmp_path) -> None:
    payload = {
        "dates": ["25 November 2022 - 26 March 2023"],
        "venues": [],
        "lines": [
            "BODY AND SPIRIT: THE HUMAN BODY IN THOUGHT AND PRACTICE",
            "Daily - 10am - 7pm",
            "Fridays - 10am - 9pm",
            "Shaw Foyer",
        ],
    }

    when = detail_navigation._raw_when(payload)

    assert when == "25 November 2022 - 26 March 2023 · Daily - 10am - 7pm"

    store = store_at(tmp_path)
    past = candidate(when=when, where="Shaw Foyer")
    store.save(ReviewState(events=[past]))
    assert store.state_payload()["events"] == []


def test_final_owner_installs_primary_document_fact_collection() -> None:
    assert detail_navigation.DETAIL_READY_JS == authority.DETAIL_STABLE_READY_JS
    assert (
        detail_navigation.FALLBACK_DETAIL_FIELDS_JS
        == authority.DETAIL_DOCUMENT_FACTS_JS
    )

    script = authority.DETAIL_DOCUMENT_FACTS_JS.lower()
    assert "root.innertext" in script
    assert "you might also like" in script
    assert "img[alt]" in script
    assert "last updated" in script
    assert "date-start-date" not in script
    assert "data-start-date" in script


def test_web_and_navigation_use_the_same_final_detail_owner() -> None:
    authority.apply()

    assert event_review._detail_candidate is authority.detail_candidate
    assert detail_navigation._detail_candidate is authority.detail_candidate
    assert detail_navigation._read_detail_page is authority._read_detail_page


def test_effective_owner_contains_no_runtime_or_parser_backfill() -> None:
    source = read_text(
        "surface/local_events_runtime/review_effective_fields_authority.py"
    )

    assert "local_event_search_results.json" not in source
    assert "local_event_collector_results.json" not in source
    assert "pick_when" not in source
    assert "pick_venue" not in source
    assert "default_venue" not in source
    assert "return dict(raw)" in source


def test_effective_fields_authority_is_installed_before_review_publication() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    effective = bootstrap.index("apply_review_effective_fields_authority()")
    publisher = bootstrap.index("apply_review_publish_authority()")

    assert effective < publisher
