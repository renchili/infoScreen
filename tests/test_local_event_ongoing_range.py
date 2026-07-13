from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

import local_events_runtime as runtime  # noqa: E402


def test_ongoing_weekday_range_keeps_full_interval(monkeypatch) -> None:
    monkeypatch.setattr(runtime._extract, "TODAY", date(2026, 7, 14))

    card = {
        "url": "https://www.gardensbythebay.com.sg#nhb-cb0737f3",
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "image_alts": [],
        "text": (
            "Orchid Extravaganza\n"
            "Fri, 3 Jul - Mon, 10 Aug 2026\n"
            "9.00am - 9.00pm\n"
            "Flower Dome"
        ),
    }
    source = {
        "id": "gardensbythebay",
        "name": "Gardens by the Bay",
        "default_venue": "Gardens by the Bay",
    }

    event, reason = runtime.event_from_card(source, card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Orchid Extravaganza"
    assert event["when"] == "3 Jul - 10 Aug 2026"
    assert event["start_date"] == "2026-07-03"
    assert event["end_date"] == "2026-08-10"
    assert event["where"] == "Flower Dome"
