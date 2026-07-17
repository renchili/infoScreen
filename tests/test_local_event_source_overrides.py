from __future__ import annotations

import json
import sys
from datetime import date

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser, extract, official_feeds  # noqa: E402
from local_events_runtime.source_overrides import (  # noqa: E402
    LISTING_EVIDENCE,
    _listing_card,
    _merge_detail,
    _prefer_structured,
    apply,
)

apply()


def future_year() -> int:
    return date.today().year + 1


def source() -> dict:
    return {
        "id": "official-source",
        "name": "Official Source",
        "default_venue": "Official Venue",
        "allowed_domains": ["example.org"],
        "listing_urls": ["https://example.org/whats-on"],
    }


def dom_card(title: str, url: str, when: str) -> dict:
    return {
        "id": "listing-card-1",
        "url": url,
        "page_url": "https://example.org/whats-on",
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": f"{title}\n{when}\nOfficial Venue",
        "text_lines": [title, when, "Official Venue"],
        "detail_url_count": 1,
        "detail_urls": [url],
        "extraction_mode": "detail_link",
        "screenshot": "",
    }


def admitted_card(title: str, url: str, when: str) -> dict:
    card = _listing_card(source(), dom_card(title, url, when), "https://example.org/whats-on")
    assert card is not None
    return card


def test_browser_discovery_requires_an_isolated_dated_listing_card() -> None:
    assert 'el.matches && el.matches("a[href]")' in browser.CARD_JS
    assert "listingDetailUrls.length !== 1" in browser.CARD_JS
    assert 'hasDateText(textLines(card).join(" "))' in browser.CARD_JS
    assert "#nhb-" not in browser.CARD_JS.split('push(out, seen, el, url, "", "nhb_dom_card")', 1)[0].split("function pushNhbCards", 1)[-1]
    assert "plan-your-itinerary" not in browser.CARD_JS


def test_deep_scroll_waits_until_the_listing_stops_growing() -> None:
    assert "stableRounds >= 3" in browser.PREPARE_PAGE_JS
    assert "scrollTo(0, document.body.scrollHeight)" in browser.PREPARE_PAGE_JS
    assert "new Set(links).size" in browser.PREPARE_PAGE_JS


def test_real_listing_card_is_the_positive_admission_evidence() -> None:
    year = future_year()
    card = admitted_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        f"10 Aug {year}",
    )

    assert card["listing_evidence"] == LISTING_EVIDENCE
    assert card["listing_url"] == "https://example.org/whats-on"
    assert card["listing_card_id"] == "listing-card-1"


def test_card_without_a_date_is_not_an_activity_list_record() -> None:
    card = dom_card(
        "Visitor Information",
        "https://example.org/visitor-information",
        "Open daily",
    )

    assert _listing_card(source(), card, "https://example.org/whats-on") is None


def test_unmatched_structured_records_are_dropped_even_when_typed_event() -> None:
    year = future_year()
    unrelated = official_feeds.event_card(
        {
            "title": "Carpark",
            "when": f"1 Jan - 31 Dec {year}",
            "where": "Official Venue",
            "url": "https://example.org/amenities/carpark",
            "summary": "Carpark Rates",
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
        },
        "official-source",
        0,
    )
    listing = dom_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        f"10 Aug {year}",
    )
    _prefer_structured.source = source()
    _prefer_structured.listing_url = "https://example.org/whats-on"

    cards = _prefer_structured([unrelated], [listing], 10)

    assert len(cards) == 1
    assert cards[0]["link_text"] == "Family Sports Day"
    assert cards[0].get("structured_event") is None
    assert cards[0]["listing_evidence"] == LISTING_EVIDENCE


def test_matching_structured_data_only_enriches_the_listed_activity() -> None:
    year = future_year()
    url = "https://example.org/whats-on/family-sports-day"
    structured = official_feeds.event_card(
        {
            "title": "Family Sports Day",
            "when": f"10 Aug {year}",
            "where": "Sports Hall",
            "url": "https://example.org/api/items/123",
            "summary": "A day of family activities.",
            "start_date": f"{year}-08-10",
            "end_date": f"{year}-08-10",
        },
        "official-source",
        0,
    )
    listing = dom_card("Family Sports Day", url, f"10 Aug {year}")
    _prefer_structured.source = source()
    _prefer_structured.listing_url = "https://example.org/whats-on"

    cards = _prefer_structured([structured], [listing], 10)

    assert len(cards) == 1
    assert cards[0]["url"] == url
    assert cards[0]["structured_event"]["url"] == url
    assert cards[0]["structured_event"]["where"] == "Sports Hall"
    assert cards[0]["listing_evidence"] == LISTING_EVIDENCE


def test_listed_activity_is_not_rejected_by_title_keyword_enumeration() -> None:
    year = future_year()
    card = admitted_card(
        "Membership Workshop",
        "https://example.org/whats-on/membership-workshop",
        f"12 Aug {year}",
    )

    event, reason = extract.event_from_card(source(), card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Membership Workshop"
    assert event["candidate_policy"] == "official-listing-authority-v1"


def test_event_shaped_card_without_listing_evidence_is_rejected() -> None:
    year = future_year()
    card = dom_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        f"10 Aug {year}",
    )

    event, reason = extract.event_from_card(source(), card)

    assert event is None
    assert reason == "missing_official_listing_evidence"


def test_detail_page_enrichment_preserves_listing_membership() -> None:
    year = future_year()
    url = "https://example.org/whats-on/family-sports-day"
    card = admitted_card("Family Sports Day", url, f"10 Aug {year}")
    detail = {
        "canonical": url,
        "title": "Family Sports Day",
        "eventObjects": [],
        "dates": [f"10 Aug {year}"],
        "venues": ["Sports Hall"],
        "lines": ["A day of family activities."],
        "summary": "A day of family activities.",
    }

    enriched = _merge_detail(source(), card, detail, 0)

    assert enriched["listing_evidence"] == LISTING_EVIDENCE
    assert enriched["listing_card_id"] == "listing-card-1"
    assert enriched["detail_evidence"]["canonical_url"] == url


def test_source_configuration_contains_policy_not_per_record_exclusions() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    config_text = read_text("surface/conf/event_sources.json")
    implementation = read_text("surface/local_events_runtime/source_overrides.py")

    assert payload["version"] == 6
    assert payload["policy"]["listing_card_is_authoritative"] is True
    assert payload["policy"]["unmatched_structured_records_are_rejected"] is True
    assert "exclude_url_patterns" not in config_text
    assert "plan-your-itinerary" not in config_text
    assert "NON_EVENT_PATH_SEGMENTS" not in implementation
    assert "_known_non_event_url" not in implementation
    assert "exclude_url_patterns" not in implementation


def test_dynamic_sources_still_expand_and_enrich_their_official_lists() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in payload["sources"]}

    assert sources["nationalgallery"]["load_more_rounds"] >= 20
    assert sources["nationalgallery"]["detail_authoritative"] is True
    assert sources["nationalmuseum"]["detail_authoritative"] is True
    assert sources["gardensbythebay"]["detail_authoritative"] is True
    assert sources["sentosa"]["detail_authoritative"] is True
    assert sources["sciencecentre"]["max_cards"] >= 120
