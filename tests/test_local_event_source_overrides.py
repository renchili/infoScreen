from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser, extract, official_feeds  # noqa: E402
from local_events_runtime.output import normalize_payload  # noqa: E402
from local_events_runtime.source_overrides import (  # noqa: E402
    _merge_detail,
    apply,
)

apply()


def future_year() -> int:
    return date.today().year + 1


def test_card_anchor_itself_is_included_in_detail_url_discovery() -> None:
    assert 'el.matches && el.matches("a[href]")' in browser.CARD_JS
    assert '"guided-tours", "plan-your-itinerary"' in browser.CARD_JS


def test_infinite_scroll_waits_for_two_stable_rounds() -> None:
    assert "stableRounds >= 2" in browser.PREPARE_PAGE_JS
    assert "window.scrollTo(0, document.body.scrollHeight)" in browser.PREPARE_PAGE_JS
    assert "current.cards > previous.cards" in browser.PREPARE_PAGE_JS


def test_national_museum_itinerary_page_is_rejected() -> None:
    year = future_year()
    event, reason = extract.event_from_card(
        {
            "id": "nationalmuseum",
            "name": "National Museum Singapore",
            "default_venue": "National Museum Singapore",
            "exclude_url_patterns": ["/whats-on/plan-your-itinerary"],
        },
        {
            "url": "https://www.nationalmuseum.nhb.gov.sg/whats-on/plan-your-itinerary",
            "headings": ["Plan Your Itinerary"],
            "link_text": "Plan Your Itinerary",
            "text": f"Plan Your Itinerary\n1 Aug {year}\nNational Museum Singapore",
        },
    )

    assert event is None
    assert reason == "non_event_information_page"


def test_gardens_structured_card_uses_canonical_dom_detail_url() -> None:
    synthetic = {
        "url": "https://www.gardensbythebay.com.sg/#structured-deadbeef",
        "page_url": "https://www.gardensbythebay.com.sg/#structured-deadbeef",
        "link_text": "JuJu World by Cj Hendry",
        "headings": ["JuJu World by Cj Hendry"],
        "structured_event": {
            "title": "JuJu World by Cj Hendry",
            "url": "https://www.gardensbythebay.com.sg/#structured-deadbeef",
        },
    }
    canonical_url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/"
        "calendar-of-events/juju-world-by-cj-hendry.html"
    )
    dom = {
        "url": canonical_url,
        "link_text": "JuJu World by Cj Hendry",
        "headings": ["JuJu World by Cj Hendry"],
    }

    merged = official_feeds.prefer_structured_cards([synthetic], [dom], 10)

    assert merged[0]["url"] == canonical_url
    assert merged[0]["structured_event"]["url"] == canonical_url


def test_sentosa_authoritative_detail_replaces_wrong_title_date_and_place() -> None:
    year = future_year()
    url = (
        "https://www.sentosa.com.sg/en/things-to-do/events/"
        "magical-island-adventure-meet-and-greet/"
    )
    card = {
        "url": url,
        "text": f"Meet and Greet\n31 Dec {year}\nSentosa",
        "structured_event": {
            "title": "Meet and Greet",
            "when": f"31 Dec {year}",
            "where": "Sentosa",
            "url": url,
            "summary": "",
            "start_date": f"{year}-12-31",
            "end_date": f"{year}-12-31",
        },
    }
    detail = {
        "title": "Magical Island Adventure | Character Meet & Greet",
        "date_text": f"27 Jun {year} - 16 Aug {year}",
        "start_date": f"{year}-06-27",
        "end_date": f"{year}-08-16",
        "location": "Palawan Beach",
        "summary": "Meet the characters on the island adventure.",
        "text": "detail page",
        "text_lines": ["detail page"],
    }

    event, reason = extract.event_from_card(
        {"id": "sentosa", "name": "Sentosa", "default_venue": "Sentosa"},
        _merge_detail(card, detail),
    )

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Magical Island Adventure | Character Meet & Greet"
    assert event["when"] == f"27 Jun - 16 Aug {year}"
    assert event["start_date"] == f"{year}-06-27"
    assert event["end_date"] == f"{year}-08-16"
    assert event["where"] == "Palawan Beach"


def test_gardens_authoritative_detail_location_replaces_default_venue() -> None:
    year = future_year()
    url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/"
        "calendar-of-events/juju-world-by-cj-hendry.html"
    )
    card = {
        "url": url,
        "text": f"JuJu World by Cj Hendry\n18 Jul {year}\nGardens by the Bay",
        "structured_event": {
            "title": "JuJu World by Cj Hendry",
            "when": f"18 Jul {year}",
            "where": "Gardens by the Bay",
            "url": url,
            "summary": "",
            "start_date": f"{year}-07-18",
            "end_date": f"{year}-07-18",
        },
    }
    detail = {
        "title": "JuJu World by Cj Hendry",
        "date_text": f"20 Jun {year} - 18 Jul {year}",
        "start_date": f"{year}-06-20",
        "end_date": f"{year}-07-18",
        "location": "IMBA Theatre (West Lawn, beside Bayfront Plaza)",
        "text": "detail page",
        "text_lines": ["detail page"],
    }

    event, reason = extract.event_from_card(
        {
            "id": "gardensbythebay",
            "name": "Gardens by the Bay",
            "default_venue": "Gardens by the Bay",
        },
        _merge_detail(card, detail),
    )

    assert reason == "accepted"
    assert event is not None
    assert event["where"] == "IMBA Theatre (West Lawn, beside Bayfront Plaza)"
    assert event["url"] == url


def test_runtime_output_removes_expired_and_information_rows() -> None:
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    payload = normalize_payload(
        {
            "results": [
                {
                    "title": "Expired Event",
                    "when": yesterday.isoformat(),
                    "start_date": yesterday.isoformat(),
                    "end_date": yesterday.isoformat(),
                    "url": "https://example.test/events/expired",
                },
                {
                    "title": "Plan Your Itinerary",
                    "when": tomorrow.isoformat(),
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                    "url": "https://www.nationalmuseum.nhb.gov.sg/whats-on/plan-your-itinerary",
                },
                {
                    "title": "Current Event",
                    "when": tomorrow.isoformat(),
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                    "url": "https://example.test/events/current",
                },
            ]
        }
    )

    assert [item["title"] for item in payload["results"]] == ["Current Event"]
    assert payload["expired_events_removed"] == 1
    assert payload["invalid_events_removed"] == 1


def test_dynamic_source_config_expands_and_enriches_affected_sources() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in payload["sources"]}

    assert sources["nationalgallery"]["load_more_rounds"] >= 20
    assert sources["nationalgallery"]["detail_authoritative"] is True
    assert sources["nationalmuseum"]["detail_authoritative"] is True
    assert sources["gardensbythebay"]["detail_authoritative"] is True
    assert sources["sentosa"]["detail_authoritative"] is True
    assert sources["sciencecentre"]["max_cards"] >= 120
    assert {
        "https://www.science.edu.sg/whats-on/workshops-activities",
        "https://www.science.edu.sg/whats-on/exhibitions",
        "https://www.science.edu.sg/whats-on/shows-demonstrations",
    } <= set(sources["sciencecentre"]["listing_urls"])
