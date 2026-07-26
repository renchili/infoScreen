from __future__ import annotations

import sys
from datetime import date
from urllib.parse import urlparse

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

import local_events_runtime as runtime  # noqa: E402
from local_events_runtime import (  # noqa: E402
    card_has_date,
    event_from_card as runtime_event_from_card,
    label_dates,
)
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


def source(source_id: str = "test", venue: str = "Test Venue") -> dict:
    return {"id": source_id, "name": "Test Source", "default_venue": venue}


def event_from_card(source_value: dict, raw_card: dict):
    """Adapt parser fixtures to the current official-list membership contract."""

    card = dict(raw_card)
    detail_url = str(card.get("url") or "")
    parsed = urlparse(detail_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    listing_url = str(
        card.get("listing_url")
        or card.get("page_url")
        or (f"{origin}/events" if origin else "")
    )
    if listing_url.rstrip("/") == detail_url.split("#", 1)[0].rstrip("/"):
        listing_url = f"{origin}/events" if origin else listing_url

    card.setdefault("listing_evidence", LISTING_EVIDENCE)
    card["listing_url"] = listing_url
    card.setdefault("listing_card_id", str(card.get("id") or "fixture-listing-card"))

    configured_source = dict(source_value)
    if parsed.hostname:
        configured_source.setdefault("allowed_domains", [parsed.hostname])
    if listing_url:
        configured_source.setdefault("listing_urls", [listing_url])
    return runtime_event_from_card(configured_source, card)


def future_year() -> int:
    return date.today().year + 2


def test_month_first_dates_are_recognised() -> None:
    year = future_year()
    dates = label_dates(f"Thursday, July 10, {year}, 2:00 PM")
    assert any(item.isoformat() == f"{year}-07-10" for item in dates)


def test_weekday_prefixed_range_is_preserved() -> None:
    year = future_year()
    card = {
        "id": "orchid",
        "url": "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/orchid-extravaganza.html",
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "image_alts": [],
        "text": f"Orchid Extravaganza\nFri, 3 Jul - Mon, 10 Aug {year}\n9.00am - 9.00pm\nFlower Dome",
    }
    event, reason = event_from_card(source("gardensbythebay", "Gardens by the Bay"), card)
    assert reason == "accepted"
    assert event is not None
    assert event["when"] == f"3 Jul - 10 Aug {year}"
    assert event["start_date"] == f"{year}-07-03"
    assert event["end_date"] == f"{year}-08-10"
    assert event["where"] == "Flower Dome"
    assert [item.isoformat() for item in label_dates(event["when"])] == [
        f"{year}-07-03",
        f"{year}-08-10",
    ]


def test_weekday_prefixed_range_split_across_dom_lines_is_preserved() -> None:
    year = future_year()
    card = {
        "id": "orchid-split",
        "url": "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/orchid-extravaganza-split.html",
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "image_alts": [],
        "text": f"Orchid Extravaganza\nFri, 3 Jul -\nMon, 10 Aug {year}\n9.00am - 9.00pm\nFlower Dome",
    }
    event, reason = event_from_card(source("gardensbythebay", "Gardens by the Bay"), card)
    assert reason == "accepted"
    assert event is not None
    assert event["when"] == f"3 Jul - 10 Aug {year}"
    assert event["start_date"] == f"{year}-07-03"
    assert event["end_date"] == f"{year}-08-10"
    assert event["where"] == "Flower Dome"


def test_gardens_ongoing_range_remains_in_output(monkeypatch) -> None:
    monkeypatch.setattr(runtime._extract, "TODAY", date(2026, 7, 14))
    card = {
        "id": "orchid-current",
        "url": "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/orchid-extravaganza-current.html",
        "link_text": "Orchid Extravaganza",
        "headings": ["Orchid Extravaganza"],
        "image_alts": [],
        "text": "Orchid Extravaganza\nFri, 3 Jul - Mon, 10 Aug 2026\n9.00am - 9.00pm\nFlower Dome",
    }
    event, reason = event_from_card(source("gardensbythebay", "Gardens by the Bay"), card)
    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Orchid Extravaganza"
    assert event["when"] == "3 Jul - 10 Aug 2026"
    assert event["start_date"] == "2026-07-03"
    assert event["end_date"] == "2026-08-10"
    assert event["where"] == "Flower Dome"


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
    assert reason in {"current_date_not_found_in_card", "past_date"}


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
    assert reason in {"media_asset_url", "official_detail_url_not_found"}


def test_fake_date_location_titles_are_rejected() -> None:
    for title in ("Date:", "Location:", "box"):
        assert runtime._extract.normalise_title(title) == ""


def test_mandai_synthetic_location_card_is_rejected() -> None:
    year = future_year()
    title = "Beside Bird Bakery, Bird Paradise"
    card = {
        "id": "mandai-location",
        "url": "https://www.mandai.com#nhb-1c7a60a2",
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": f"{title}\n9 Aug {year}",
    }
    reason = runtime._extract.event_looks_wrong(
        source("mandai", "Mandai Wildlife Reserve"),
        card,
        title,
        f"9 Aug {year}",
    )
    assert reason in {"synthetic_venue_title", "synthetic_mandai_location_card"}


def test_synthetic_summary_titles_are_rejected() -> None:
    year = future_year()
    title = "Step up alongside family and friends for a meaningful cause at Resorts World Sentosa's inaugural RWS Cares Festival."
    card = {
        "id": "rws-summary",
        "url": "https://www.rwsentosa.com#nhb-aa2aecf8",
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": f"{title}\n22 - 23 August {year}\nResorts World Sentosa",
    }
    reason = runtime._extract.event_looks_wrong(
        source("rws", "Resorts World Sentosa"),
        card,
        title,
        f"22 - 23 August {year}",
    )
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
