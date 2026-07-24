from __future__ import annotations

import json
import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_summary_authority  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as navigation  # noqa: E402
from local_events_runtime import review_effective_fields_authority as authority  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ReviewState,
)


detail_summary_authority.apply()
authority.apply()

DETAIL_URL = (
    "https://www.acm.nhb.gov.sg/whats-on/exhibitions/"
    "crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-"
    "from-the-musee-du-louvre"
)
NARRATIVE = (
    "From the 16th to 18th century, three great empires – the Mughals, "
    "Safavids, and Ottomans – shaped a vast and interconnected world across Asia."
)
PLACEHOLDER = "Open the official page for details."


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


def candidate(summary: str = PLACEHOLDER) -> EventCandidate:
    return EventCandidate(
        candidate_id="acm-crosscurrents",
        source_id="acm",
        source_name="Asian Civilisations Museum",
        listing_url="https://www.acm.nhb.gov.sg/whats-on/overview",
        detail_url=DETAIL_URL,
        title="Crosscurrents",
        when="19 June 2026 – 24 January 2027",
        where="Design Gallery on Level 3",
        summary=summary,
        detail_status="collected",
        detail_page_title="Crosscurrents",
        evidence=EventEvidence(
            selector="div.a-listing-content__content",
            selector_index=2,
            selector_match_count=6,
            document_position={"x": 881, "y": 466, "width": 348, "height": 589},
            viewport_position={"x": 881, "y": 466, "width": 348, "height": 589},
            page_index=0,
            page_url="https://www.acm.nhb.gov.sg/whats-on/overview",
            text="EXHIBITIONS IN-MUSEUM",
        ),
        decision="pending",
        collected_at="2026-07-24T00:00:00+00:00",
    )


def write_kiosk_runtime(store: EventReviewStore) -> None:
    path = store.root.parent / authority.DISPLAY_RUNTIME_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "results": [
                    {
                        "url": DETAIL_URL,
                        "title": "Crosscurrents",
                        "when": "19 June 2026 – 24 January 2027",
                        "where": "Design Gallery on Level 3",
                        "summary": NARRATIVE,
                        "source_name": "Asian Civilisations Museum",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_detail_navigation_prefers_payload_narrative_over_parser_placeholder() -> None:
    summary = navigation._best_summary(
        {"summary_candidates": [NARRATIVE], "summary": NARRATIVE},
        {"detail_summary": NARRATIVE},
        {"summary": PLACEHOLDER},
    )

    assert summary == NARRATIVE


def test_review_state_get_uses_kiosk_narrative_for_existing_placeholder(tmp_path) -> None:
    store = store_at(tmp_path)
    store.save(ReviewState(events=[candidate()]))
    write_kiosk_runtime(store)

    payload = store.state_payload()

    assert payload["events"][0]["summary"] == NARRATIVE
    assert payload["events"][0]["decision"] == "pending"
    assert payload["events"][0]["detail_status"] == "collected"
    assert payload["events"][0]["evidence"]["selector"] == (
        "div.a-listing-content__content"
    )


def test_fresh_preview_persists_kiosk_narrative_instead_of_placeholder(tmp_path) -> None:
    store = store_at(tmp_path)
    write_kiosk_runtime(store)

    state = store.replace_events([candidate()], {"completed_at": "now"})

    assert state.events[0].summary == NARRATIVE
    persisted = store.load()
    assert persisted.events[0].summary == NARRATIVE


def test_valid_review_narrative_is_not_replaced_by_runtime(tmp_path) -> None:
    store = store_at(tmp_path)
    review_narrative = (
        "A newly reviewed activity description with more precise information from "
        "the official detail page."
    )
    store.save(ReviewState(events=[candidate(review_narrative)]))
    write_kiosk_runtime(store)

    assert store.state_payload()["events"][0]["summary"] == review_narrative


def test_effective_fields_authority_is_installed_before_review_publication() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    effective = bootstrap.index("apply_review_effective_fields_authority()")
    publisher = bootstrap.index("apply_review_publish_authority()")

    assert effective < publisher
