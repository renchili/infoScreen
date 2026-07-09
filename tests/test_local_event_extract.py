from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime.extract import event_from_card, label_dates  # noqa: E402


def source(source_id: str = "test") -> dict:
    return {"id": source_id, "name": "Test Source", "default_venue": "Test Venue"}


def test_month_first_dates_are_recognised() -> None:
    dates = label_dates("Thursday, July 10, 2026, 2:00 PM")

    assert any(item.isoformat() == "2026-07-10" for item in dates)


def test_event_box_title_falls_back_to_detail_text_title() -> None:
    card = {
        "url": "https://nlb.libcal.com/event/5910490",
        "link_text": "Event box",
        "headings": ["Event box"],
        "image_alts": [],
        "text": "Learn Digital - Gen AI: Basics, Risks, and Misinformation\nThursday, July 10, 2026\nCentral Public Library",
    }

    event, reason = event_from_card(source("nlb"), card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Learn Digital - Gen AI: Basics, Risks, and Misinformation"
    assert event["when"] == "July 10, 2026"


def test_media_asset_urls_are_rejected() -> None:
    card = {
        "url": "https://www.sentosa.com.sg/-/media/sentosa/event.jpg?revision=1",
        "link_text": "Minions Summer",
        "headings": ["Minions Summer"],
        "image_alts": [],
        "text": "Minions Summer\n29 May to 11 Aug 2026\nSentosa",
    }

    event, reason = event_from_card(source("sentosa"), card)

    assert event is None
    assert reason == "media_asset_url"


def test_fake_date_location_titles_are_rejected() -> None:
    for title in ("Date:", "Location:", "box"):
        card = {
            "url": "https://www.mandai.com#nhb-test",
            "link_text": title,
            "headings": [title],
            "image_alts": [],
            "text": f"{title}\n1 Apr – 31 Jul 2026\nNight Safari",
        }

        event, reason = event_from_card(source("mandai"), card)

        assert event is None
        assert reason == "title_not_found"


def test_synthetic_summary_titles_are_rejected() -> None:
    card = {
        "url": "https://www.rwsentosa.com#nhb-aa2aecf8",
        "link_text": "Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival.",
        "headings": ["Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival."],
        "image_alts": [],
        "text": "Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival.\n22 - 23 August 2026\nResorts World Sentosa",
    }

    event, reason = event_from_card(source("rws"), card)

    assert event is None
    assert reason == "synthetic_summary_title"
