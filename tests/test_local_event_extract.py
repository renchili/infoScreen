from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import card_has_date, event_from_card, label_dates  # noqa: E402


def source(source_id: str = "test", venue: str = "Test Venue") -> dict:
    return {"id": source_id, "name": "Test Source", "default_venue": venue}


def future_year() -> int:
    return date.today().year + 2


def test_month_first_dates_are_recognised() -> None:
    year = future_year()
    dates = label_dates(f"Thursday, July 10, {year}, 2:00 PM")

    assert any(item.isoformat() == f"{year}-07-10" for item in dates)


def test_detail_enrichment_requires_a_complete_date() -> None:
    year = future_year()

    assert card_has_date({"text": f"May {year}"}) is False
    assert card_has_date({"text": f"10 July {year}"}) is True
    assert card_has_date({"text": f"July 10, {year}"}) is True


def test_event_box_title_falls_back_to_detail_text_title() -> None:
    year = future_year()
    card = {
        "url": "https://nlb.libcal.com/event/5910490",
        "link_text": "Event box",
        "headings": ["Event box"],
        "image_alts": [],
        "text": f"Learn Digital - Gen AI: Basics, Risks, and Misinformation\nThursday, July 10, {year}\nCentral Public Library",
    }

    event, reason = event_from_card(source("nlb"), card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Learn Digital - Gen AI: Basics, Risks, and Misinformation"
    assert event["when"] == f"July 10, {year}"


def test_closed_past_range_is_not_treated_as_open_ended() -> None:
    card = {
        "url": "https://www.peranakanmuseum.nhb.gov.sg/whatson/lectures-and-seminars",
        "link_text": "LECTURES AND SEMINAR",
        "headings": ["LECTURES AND SEMINAR"],
        "image_alts": [],
        "text": "This talk is organised in conjunction with an exhibition, from 11 October 2024 to 31 August 2025.",
    }

    event, reason = event_from_card(source("peranakanmuseum", "Peranakan Museum"), card)

    assert event is None
    assert reason == "current_date_not_found_in_card"


def test_url_title_is_preferred_over_image_asset_label() -> None:
    year = future_year()
    card = {
        "url": "https://www.nationalmuseum.nhb.gov.sg/whats-on/exhibition/tails-from-the-coasts",
        "link_text": "",
        "headings": [],
        "image_alts": ["tails-from-the-coasts-no-text"],
        "text": f"26 Jun {year} – 01 Nov {year}\nNational Museum Singapore",
    }

    event, reason = event_from_card(source("nationalmuseum", "National Museum Singapore"), card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Tails From The Coasts"


def test_media_asset_urls_are_rejected() -> None:
    year = future_year()
    card = {
        "url": "https://www.sentosa.com.sg/-/media/sentosa/event.jpg?revision=1",
        "link_text": "Minions Summer",
        "headings": ["Minions Summer"],
        "image_alts": [],
        "text": f"Minions Summer\n29 May to 11 Aug {year}\nSentosa",
    }

    event, reason = event_from_card(source("sentosa"), card)

    assert event is None
    assert reason == "media_asset_url"


def test_fake_date_location_titles_are_rejected() -> None:
    year = future_year()
    for title in ("Date:", "Location:", "box"):
        card = {
            "url": "https://www.mandai.com#nhb-test",
            "link_text": title,
            "headings": [title],
            "image_alts": [],
            "text": f"{title}\n1 Apr – 31 Jul {year}\nNight Safari",
        }

        event, reason = event_from_card(source("mandai", "Mandai Wildlife Reserve"), card)

        assert event is None
        assert reason in {
            "title_not_found",
            "synthetic_venue_title",
            "synthetic_mandai_location_card",
        }


def test_mandai_synthetic_location_card_is_rejected() -> None:
    year = future_year()
    card = {
        "url": "https://www.mandai.com#nhb-1c7a60a2",
        "link_text": "Beside Bird Bakery, Bird Paradise",
        "headings": ["Beside Bird Bakery, Bird Paradise"],
        "image_alts": [],
        "text": f"Beside Bird Bakery, Bird Paradise\n9 Aug {year}",
    }

    event, reason = event_from_card(source("mandai", "Mandai Wildlife Reserve"), card)

    assert event is None
    assert reason == "synthetic_mandai_location_card"


def test_synthetic_summary_titles_are_rejected() -> None:
    year = future_year()
    card = {
        "url": "https://www.rwsentosa.com#nhb-aa2aecf8",
        "link_text": "Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival.",
        "headings": ["Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival."],
        "image_alts": [],
        "text": f"Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival.\n22 - 23 August {year}\nResorts World Sentosa",
    }

    event, reason = event_from_card(source("rws", "Resorts World Sentosa"), card)

    assert event is None
    assert reason == "synthetic_summary_title"


def test_narrative_venue_falls_back_to_source_default() -> None:
    year = future_year()
    card = {
        "url": "https://www.nationalgallery.sg/sg/en/exhibitions/when-art-meets-nature.html",
        "link_text": "When Art Meets Nature",
        "headings": ["When Art Meets Nature"],
        "image_alts": [],
        "text": f"When Art Meets Nature\n1 Nov {year}\nIn When Art Meets Nature, a children's art exhibition co-curated by the museum and partner institutions",
    }

    event, reason = event_from_card(source("nationalgallery", "National Gallery Singapore"), card)

    assert reason == "accepted"
    assert event is not None
    assert event["where"] == "National Gallery Singapore"
