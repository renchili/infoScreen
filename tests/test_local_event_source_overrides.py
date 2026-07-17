from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser, extract  # noqa: E402
from local_events_runtime.source_overrides import (  # noqa: E402
    DOM_ONLY_SOURCES,
    apply,
)


def test_dynamic_sources_use_rendered_dom_collection() -> None:
    assert {
        "gardensbythebay",
        "nationalgallery",
        "nationalmuseum",
        "sciencecentre",
        "sentosa",
    } <= DOM_ONLY_SOURCES


def test_card_anchor_itself_is_included_in_detail_url_discovery() -> None:
    apply()

    assert 'el.matches("a[href]") ? [el] : []' in browser.CARD_JS


def test_national_museum_itinerary_page_is_rejected(monkeypatch) -> None:
    apply()
    future = date.today() + timedelta(days=30)

    monkeypatch.setattr(
        extract,
        "event_from_card",
        extract.event_from_card,
    )
    event, reason = extract.event_from_card(
        {"id": "nationalmuseum", "name": "National Museum Singapore"},
        {
            "url": "https://www.nationalmuseum.nhb.gov.sg/whats-on/plan-your-itinerary",
            "headings": ["Plan Your Itinerary"],
            "link_text": "Plan Your Itinerary",
            "text": f"Plan Your Itinerary\n{future.day} {future.strftime('%b')} {future.year}",
        },
    )

    assert event is None
    assert reason == "non_event_itinerary_page"


def test_gardens_synthetic_link_is_rejected(monkeypatch) -> None:
    apply()
    future = date.today() + timedelta(days=30)
    event, reason = extract.event_from_card(
        {"id": "gardensbythebay", "name": "Gardens by the Bay"},
        {
            "url": "https://www.gardensbythebay.com.sg/#nhb-deadbeef",
            "headings": ["JuJu World by Cj Hendry"],
            "link_text": "JuJu World by Cj Hendry",
            "text": f"JuJu World by Cj Hendry\n{future.day} {future.strftime('%b')} {future.year}\nIMBA Theatre",
        },
    )

    assert event is None
    assert reason == "gardens_noncanonical_event_url"


def test_dynamic_source_config_scrolls_and_expands_science_categories() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in payload["sources"]}

    assert sources["nationalgallery"]["load_more_rounds"] >= 20
    assert sources["gardensbythebay"]["load_more_rounds"] >= 10
    assert sources["sciencecentre"]["load_more_rounds"] >= 10
    assert {
        "https://www.science.edu.sg/whats-on/workshops-activities",
        "https://www.science.edu.sg/whats-on/exhibitions",
        "https://www.science.edu.sg/whats-on/shows-demonstrations",
    } <= set(sources["sciencecentre"]["listing_urls"])
