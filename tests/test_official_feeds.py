from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_from_card  # noqa: E402
from local_events_runtime.official_feeds import (  # noqa: E402
    event_card,
    extract_structured_events,
    prefer_structured_cards,
)


def future_year() -> int:
    return date.today().year + 2


def source(name: str = "Official Source") -> dict:
    return {
        "id": "official-source",
        "name": name,
        "default_venue": name,
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


def test_structured_cards_replace_same_title_dom_guess_but_keep_other_dom_cards() -> None:
    year = future_year()
    structured = event_card(
        {
            "title": "Orchid Extravaganza",
            "when": f"3 Jul - 10 Aug {year}",
            "where": "Flower Dome",
            "url": "https://example.org/orchid",
            "summary": "",
            "start_date": f"{year}-07-03",
            "end_date": f"{year}-08-10",
        },
        "source",
        0,
    )
    bad_dom = {
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "text": f"Orchid Extravaganza\n10 Aug {year}",
        "url": "https://example.org/orchid",
    }
    other_dom = {
        "link_text": "Another Event",
        "headings": ["Another Event"],
        "text": f"Another Event\n20 Aug {year}",
        "url": "https://example.org/another",
    }

    cards = prefer_structured_cards([structured], [bad_dom, other_dom], 10)

    assert cards == [structured, other_dom]


def test_structured_card_bypasses_dom_date_guessing_for_any_source() -> None:
    year = future_year()
    card = {
        "url": "https://example.org/events/orchid",
        "text": f"10 Aug {year}",
        "structured_event": {
            "title": "Orchid Extravaganza",
            "when": f"3 Jul - 10 Aug {year}",
            "where": "Flower Dome",
            "url": "https://example.org/events/orchid",
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
    assert event["source_type"] == "official_structured_data"


def test_safra_structured_carpark_facility_is_rejected() -> None:
    card = {
        "url": "https://www.safra.sg/amenities-offerings/carpark",
        "text": (
            "Carpark\n"
            "18 Mar 2024 - 31 Dec 2029\n"
            "SAFRA Mount Faber, SAFRA Punggol, SAFRA Toa Payoh, "
            "SAFRA Choa Chu Kang, SAFRA Tampines\n"
            "Carpark Rates"
        ),
        "structured_event": {
            "title": "Carpark",
            "when": "18 Mar 2024 - 31 Dec 2029",
            "where": (
                "SAFRA Mount Faber, SAFRA Punggol, SAFRA Toa Payoh, "
                "SAFRA Choa Chu Kang, SAFRA Tampines"
            ),
            "url": "https://www.safra.sg/amenities-offerings/carpark",
            "summary": "Carpark Rates",
            "start_date": "2024-03-18",
            "end_date": "2029-12-31",
        },
    }
    safra = {
        "id": "safra",
        "name": "SAFRA",
        "default_venue": "SAFRA Clubs",
    }

    event, reason = event_from_card(safra, card)

    assert event is None
    assert reason == "non_event_carpark_facility"


def test_real_safra_event_can_mention_carpark_in_summary() -> None:
    year = future_year()
    card = {
        "url": "https://www.safra.sg/whats-on/family-sports-day",
        "text": (
            f"Family Sports Day\n10 Aug {year}\nSAFRA Punggol\n"
            "Carpark access remains available during the event."
        ),
        "structured_event": {
            "title": "Family Sports Day",
            "when": f"10 Aug {year}",
            "where": "SAFRA Punggol",
            "url": "https://www.safra.sg/whats-on/family-sports-day",
            "summary": "Carpark access remains available during the event.",
            "start_date": f"{year}-08-10",
            "end_date": f"{year}-08-10",
        },
    }
    safra = {
        "id": "safra",
        "name": "SAFRA",
        "default_venue": "SAFRA Clubs",
    }

    event, reason = event_from_card(safra, card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Family Sports Day"
