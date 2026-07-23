from __future__ import annotations

import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import (  # noqa: E402
    detail_date_authority,
    listing_membership_authority,
    listing_provenance_authority,
    open_ended_date_authority,
    source_overrides,
)
from local_events_runtime.output import normalize_payload  # noqa: E402


source_overrides.apply()
detail_date_authority.apply()
open_ended_date_authority.apply()
listing_provenance_authority.apply()
listing_membership_authority.apply()

LISTING_URL = "https://www.acm.nhb.gov.sg/whats-on/overview"
DETAIL_URL = "https://www.acm.nhb.gov.sg/whats-on/exhibitions/example"


def source() -> dict:
    return {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "default_venue": "Asian Civilisations Museum",
        "allowed_domains": ["acm.nhb.gov.sg"],
        "listing_urls": [LISTING_URL],
    }


def listed_card(*lines: str) -> dict:
    title = "Official ACM Exhibition"
    rows = [title, *lines]
    return {
        "id": "acm-card-1",
        "url": DETAIL_URL,
        "page_url": DETAIL_URL,
        "listing_url": LISTING_URL,
        "listing_evidence": source_overrides.LISTING_EVIDENCE,
        "listing_card_id": "acm-card-1",
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": "\n".join(rows),
        "text_lines": rows,
        "detail_urls": [DETAIL_URL],
        "detail_url_count": 1,
        "detail_enriched": True,
        "detail_evidence": {
            "title": title,
            "date_candidates": [],
            "venue_candidates": [],
        },
        "extraction_mode": "detail_link",
    }


def test_missing_date_and_venue_do_not_remove_official_list_activity() -> None:
    card = listed_card(
        "This exhibition presents objects from connected artistic traditions."
    )

    event, reason = listing_membership_authority.event_from_card(source(), card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Official ACM Exhibition"
    assert event["when"] == ""
    assert event["where"] == "Asian Civilisations Museum"
    assert event["detail_status"] == "incomplete"
    assert event["detail_error"] == "detail_date_and_venue_not_found"
    assert event["candidate_policy"] == "official-listing-authority-v1"
    assert event["url"] == DETAIL_URL


def test_incomplete_verified_activity_survives_output_normalization() -> None:
    event, reason = listing_membership_authority.event_from_card(
        source(),
        listed_card("Official description remains available on the detail page."),
    )
    assert reason == "accepted"
    assert event is not None

    payload = normalize_payload({"results": [event]})

    assert payload["count"] == 1
    assert payload["results"][0]["detail_status"] == "incomplete"
    assert payload["expired_events_removed"] == 0
    assert payload["invalid_events_removed"] == 0


def test_explicit_future_date_and_venue_are_collected() -> None:
    future = date.today() + timedelta(days=30)
    label = future.isoformat()
    card = listed_card("Date", label, "Location", "Design Gallery, Level 3")
    card["detail_evidence"] = {
        "title": "Official ACM Exhibition",
        "date_candidates": [label],
        "venue_candidates": ["Design Gallery, Level 3"],
    }

    event, reason = listing_membership_authority.event_from_card(source(), card)

    assert reason == "accepted"
    assert event is not None
    assert event["when"] == label
    assert event["where"] == "Design Gallery, Level 3"
    assert event["detail_status"] == "collected"
    assert event["detail_error"] == ""


def test_only_a_concrete_past_date_removes_activity() -> None:
    past = (date.today() - timedelta(days=1)).isoformat()
    card = listed_card("Date", past, "Location", "Design Gallery, Level 3")
    card["detail_evidence"] = {
        "title": "Official ACM Exhibition",
        "date_candidates": [past],
        "venue_candidates": ["Design Gallery, Level 3"],
    }

    event, reason = listing_membership_authority.event_from_card(source(), card)

    assert event is None
    assert reason == "past_date"


def test_supported_browser_card_script_has_no_listing_date_gate() -> None:
    from local_events_runtime import browser

    assert 'if (!hasDateText(textLines(card).join(" "))) continue;' not in browser.CARD_JS
