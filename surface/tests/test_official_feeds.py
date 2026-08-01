from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_from_card  # noqa: E402
from local_events_runtime import source_overrides  # noqa: E402
from local_events_runtime.official_feeds import (  # noqa: E402
    event_card,
    extract_structured_events,
    prefer_structured_cards,
)
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


def future_year() -> int:
    return date.today().year + 2


def source(name: str = "Official Source") -> dict:
    return {
        "id": "official-source",
        "name": name,
        "default_venue": name,
        "allowed_domains": ["example.org"],
        "listing_urls": ["https://example.org/events"],
    }


def test_structured_feed_uses_start_and_end_dates() -> None:
    year = future_year()
    payload = {
        "items": [
            {
                "title": "Orchid Extravaganza",
                "startDate": f"{year}-07-03T00:00:00+08:00",
                "endDate": f"{year}-08-10T23:59:59+08:00",
                "location": "Flower Dome",
                "url": "/events/orchid-extravaganza.html",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://example.org/events",
        "Official Venue",
    )

    assert len(events) == 1
    assert events[0]["title"] == "Orchid Extravaganza"
    assert events[0]["when"] == f"3 Jul - 10 Aug {year}"
    assert events[0]["start_date"] == f"{year}-07-03"
    assert events[0]["end_date"] == f"{year}-08-10"
    assert events[0]["where"] == "Flower Dome"
    assert events[0]["url"] == "https://example.org/events/orchid-extravaganza.html"


def test_structured_feed_parses_display_range_without_separate_date_fields() -> None:
    year = future_year()
    payload = {
        "results": [
            {
                "@type": "Event",
                "note": "Orchid Extravaganza",
                "displayDate": f"Fri, 3 Jul - Mon, 10 Aug {year}",
                "location": "Flower Dome",
            }
        ]
    }

    events = extract_structured_events([payload], "https://example.org/events", "Official Venue")

    assert len(events) == 1
    assert events[0]["when"] == f"3 Jul - 10 Aug {year}"
    assert events[0]["start_date"] == f"{year}-07-03"
    assert events[0]["end_date"] == f"{year}-08-10"


def test_structured_data_enriches_matching_listing_card_and_keeps_other_cards() -> None:
    year = future_year()
    structured = event_card(
        {
            "title": "Orchid Extravaganza",
            "when": f"3 Jul - 10 Aug {year}",
            "where": "Flower Dome",
            "url": "https://example.org/events/orchid",
            "summary": "",
            "start_date": f"{year}-07-03",
            "end_date": f"{year}-08-10",
        },
        "source",
        0,
    )
    matching_dom = {
        "id": "orchid-card",
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "text": f"Orchid Extravaganza\n10 Aug {year}",
        "url": "https://example.org/events/orchid",
        "detail_urls": ["https://example.org/events/orchid"],
        "detail_url_count": 1,
        "extraction_mode": "detail_link",
    }
    other_dom = {
        "id": "another-card",
        "link_text": "Another Event",
        "headings": ["Another Event"],
        "text": f"Another Event\n20 Aug {year}",
        "url": "https://example.org/events/another",
        "detail_urls": ["https://example.org/events/another"],
        "detail_url_count": 1,
        "extraction_mode": "detail_link",
    }

    token = source_overrides._listing_context.set((source(), "https://example.org/events"))
    try:
        cards = prefer_structured_cards([structured], [matching_dom, other_dom], 10)
    finally:
        source_overrides._listing_context.reset(token)

    assert len(cards) == 2
    assert cards[0]["structured_event"]["title"] == "Orchid Extravaganza"
    assert cards[0]["listing_evidence"] == LISTING_EVIDENCE
    assert cards[0]["listing_card_id"] == "orchid-card"
    assert cards[1]["link_text"] == "Another Event"
    assert cards[1]["listing_evidence"] == LISTING_EVIDENCE


def test_structured_card_bypasses_dom_date_guessing_after_listing_admission() -> None:
    year = future_year()
    detail_url = "https://example.org/events/orchid"
    card = {
        "id": "orchid-card",
        "url": detail_url,
        "text": f"10 Aug {year}",
        "detail_urls": [detail_url],
        "detail_url_count": 1,
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": "https://example.org/events",
        "listing_card_id": "orchid-card",
        "structured_event": {
            "title": "Orchid Extravaganza",
            "when": f"3 Jul - 10 Aug {year}",
            "where": "Flower Dome",
            "url": detail_url,
            "summary": "",
            "start_date": f"{year}-07-03",
            "end_date": f"{year}-08-10",
        },
    }

    event, reason = event_from_card(source(), card)

    assert reason == "accepted"
    assert event is not None
    assert event["when"] == f"3 Jul - 10 Aug {year}"
    assert event["start_date"] == f"{year}-07-03"
    assert event["end_date"] == f"{year}-08-10"
    assert event["source_type"] == "official_structured_data_matched_to_listing"


def test_untyped_structured_record_outside_event_route_is_rejected() -> None:
    payload = {
        "items": [
            {
                "title": "Carpark",
                "startDate": "2024-03-18",
                "endDate": "2029-12-31",
                "location": "SAFRA Clubs",
                "url": "/amenities-offerings/carpark",
                "description": "Carpark Rates",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://www.safra.sg/whats-on",
        "SAFRA Clubs",
    )

    assert events == []


def test_untyped_structured_record_with_dates_is_not_automatically_an_event() -> None:
    payload = {
        "items": [
            {
                "title": "Membership Access",
                "startDate": "2026-01-01",
                "endDate": "2026-12-31",
                "url": "/memberships/access",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://example.org/events",
        "Official Venue",
    )

    assert events == []


def test_untyped_structured_record_inside_event_route_is_accepted() -> None:
    year = future_year()
    payload = {
        "items": [
            {
                "title": "Family Sports Day",
                "startDate": f"{year}-08-10",
                "endDate": f"{year}-08-10",
                "location": "SAFRA Punggol",
                "url": "/whats-on/family-sports-day",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://www.safra.sg/whats-on",
        "SAFRA Clubs",
    )

    assert len(events) == 1
    assert events[0]["title"] == "Family Sports Day"


def test_explicit_event_type_is_accepted_outside_event_route() -> None:
    year = future_year()
    payload = {
        "items": [
            {
                "@type": "Event",
                "name": "Orchid Night",
                "startDate": f"{year}-08-10",
                "endDate": f"{year}-08-10",
                "url": "/content/orchid-night",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://example.org/events",
        "Official Venue",
    )

    assert len(events) == 1
    assert events[0]["title"] == "Orchid Night"
