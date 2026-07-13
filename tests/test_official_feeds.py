from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import event_from_card  # noqa: E402
from local_events_runtime.official_feeds import extract_structured_events  # noqa: E402


def future_year() -> int:
    return date.today().year + 2


def source() -> dict:
    return {
        "id": "gardensbythebay",
        "name": "Gardens by the Bay",
        "default_venue": "Gardens by the Bay",
    }


def test_official_feed_uses_start_and_end_dates() -> None:
    year = future_year()
    payload = {
        "items": [
            {
                "title": "Orchid Extravaganza",
                "startDate": f"{year}-07-03T00:00:00+08:00",
                "endDate": f"{year}-08-10T23:59:59+08:00",
                "location": "Flower Dome",
                "url": "/en/things-to-do/calendar-of-events/orchid-extravaganza.html",
            }
        ]
    }

    events = extract_structured_events(
        [payload],
        "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html",
        "Gardens by the Bay",
    )

    assert len(events) == 1
    assert events[0]["title"] == "Orchid Extravaganza"
    assert events[0]["when"] == f"3 Jul - 10 Aug {year}"
    assert events[0]["start_date"] == f"{year}-07-03"
    assert events[0]["end_date"] == f"{year}-08-10"
    assert events[0]["where"] == "Flower Dome"
    assert events[0]["url"].endswith("/orchid-extravaganza.html")


def test_structured_card_bypasses_dom_date_guessing() -> None:
    year = future_year()
    card = {
        "url": "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/orchid-extravaganza.html",
        "text": "10 Aug 2026",
        "structured_event": {
            "title": "Orchid Extravaganza",
            "when": f"3 Jul - 10 Aug {year}",
            "where": "Flower Dome",
            "url": "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/orchid-extravaganza.html",
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
    assert event["source_type"] == "official_network_json"
