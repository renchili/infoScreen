from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser  # noqa: E402
from local_events_runtime.source_overrides import (  # noqa: E402
    _listing_card,
    _merge_detail,
    apply,
)

apply()


def source(
    source_id: str,
    name: str,
    domain: str,
    listing_url: str,
    default_venue: str,
) -> dict:
    return {
        "id": source_id,
        "name": name,
        "allowed_domains": [domain],
        "listing_urls": [listing_url],
        "default_venue": default_venue,
    }


def listing_card(title: str, when: str, url: str, listing_url: str) -> dict:
    return {
        "id": "reported-listing-card",
        "url": url,
        "page_url": listing_url,
        "link_text": title,
        "headings": [title],
        "image_alts": [],
        "text": f"{title}\n{when}",
        "text_lines": [title, when],
        "detail_url_count": 1,
        "detail_urls": [url],
        "extraction_mode": "detail_link",
        "screenshot": "",
    }


def test_national_museum_itinerary_page_has_no_positive_event_membership() -> None:
    listing_url = "https://www.nationalmuseum.nhb.gov.sg/whats-on/view-all"
    museum = source(
        "nationalmuseum",
        "National Museum Singapore",
        "nationalmuseum.nhb.gov.sg",
        listing_url,
        "National Museum Singapore",
    )
    card = listing_card(
        "Plan Your Itinerary",
        "Open daily",
        "https://www.nationalmuseum.nhb.gov.sg/whats-on/plan-your-itinerary",
        listing_url,
    )

    assert _listing_card(museum, card, listing_url) is None


def test_national_gallery_listing_uses_stable_deep_scroll() -> None:
    assert "Math.max(Number(args.maxRounds || 0), 24)" in browser.PREPARE_PAGE_JS
    assert "scrollTo(0, document.body.scrollHeight)" in browser.PREPARE_PAGE_JS
    assert "new Set(links).size" in browser.PREPARE_PAGE_JS
    assert "stableRounds >= 3" in browser.PREPARE_PAGE_JS


def test_science_centre_uses_all_official_whats_on_categories() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    science = next(item for item in payload["sources"] if item["id"] == "sciencecentre")

    assert payload["policy"]["listing_card_is_authoritative"] is True
    assert payload["policy"]["unmatched_structured_records_are_rejected"] is True
    assert {
        "https://www.science.edu.sg/whats-on/workshops-activities",
        "https://www.science.edu.sg/whats-on/exhibitions",
        "https://www.science.edu.sg/whats-on/shows-demonstrations",
        "https://www.science.edu.sg/whats-on",
    } <= set(science["listing_urls"])


def test_sentosa_detail_supplies_official_title_date_and_venue() -> None:
    listing_url = "https://www.sentosa.com.sg/en/things-to-do/events/"
    url = (
        "https://www.sentosa.com.sg/en/things-to-do/events/"
        "magical-island-adventure-meet-and-greet/"
    )
    sentosa = source("sentosa", "Sentosa", "sentosa.com.sg", listing_url, "Sentosa")
    admitted = _listing_card(
        sentosa,
        listing_card("Meet and Greet", "16 Aug 2026", url, listing_url),
        listing_url,
    )
    assert admitted is not None

    enriched = _merge_detail(
        sentosa,
        admitted,
        {
            "canonical": url,
            "title": "Magical Island Adventure | Character Meet & Greet",
            "eventObjects": [
                {
                    "@type": "Event",
                    "name": "Magical Island Adventure | Character Meet & Greet",
                    "startDate": "2026-06-27",
                    "endDate": "2026-08-16",
                    "location": "Palawan Beach",
                    "url": url,
                }
            ],
            "dates": ["27 Jun 2026 - 16 Aug 2026"],
            "venues": ["Palawan Beach"],
            "lines": [],
            "summary": "",
        },
        0,
    )

    event = enriched["structured_event"]
    assert event["title"] == "Magical Island Adventure | Character Meet & Greet"
    assert event["when"] == "27 Jun - 16 Aug 2026"
    assert event["start_date"] == "2026-06-27"
    assert event["end_date"] == "2026-08-16"
    assert event["where"] == "Palawan Beach"
    assert event["url"] == url


def test_gardens_detail_keeps_canonical_url_and_real_location() -> None:
    listing_url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/"
        "calendar-of-events.html"
    )
    url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/"
        "calendar-of-events/juju-world-by-cj-hendry.html"
    )
    gardens = source(
        "gardensbythebay",
        "Gardens by the Bay",
        "gardensbythebay.com.sg",
        listing_url,
        "Gardens by the Bay",
    )
    admitted = _listing_card(
        gardens,
        listing_card("JuJu World by Cj Hendry", "18 Jul 2026", url, listing_url),
        listing_url,
    )
    assert admitted is not None

    enriched = _merge_detail(
        gardens,
        admitted,
        {
            "canonical": url,
            "title": "JuJu World by Cj Hendry",
            "eventObjects": [
                {
                    "@type": "Event",
                    "name": "JuJu World by Cj Hendry",
                    "startDate": "2026-06-20",
                    "endDate": "2026-07-18",
                    "location": "IMBA Theatre (West Lawn, beside Bayfront Plaza)",
                    "url": url,
                }
            ],
            "dates": ["20 Jun 2026 - 18 Jul 2026"],
            "venues": ["IMBA Theatre (West Lawn, beside Bayfront Plaza)"],
            "lines": [],
            "summary": "",
        },
        0,
    )

    event = enriched["structured_event"]
    assert enriched["url"] == url
    assert enriched["detail_evidence"]["canonical_url"] == url
    assert event["url"] == url
    assert event["when"] == "20 Jun - 18 Jul 2026"
    assert event["where"] == "IMBA Theatre (West Lawn, beside Bayfront Plaza)"


def test_expired_rows_are_removed_but_active_ranges_are_retained() -> None:
    from local_events_runtime.output import normalize_payload

    yesterday = date.today() - timedelta(days=1)
    start = date.today() - timedelta(days=10)
    end = date.today() + timedelta(days=10)
    active_when = f"{start.day} {start.strftime('%b')} - {end.day} {end.strftime('%b')} {end.year}"
    payload = normalize_payload(
        {
            "results": [
                {
                    "title": "Expired Event",
                    "when": yesterday.isoformat(),
                    "start_date": yesterday.isoformat(),
                    "end_date": yesterday.isoformat(),
                    "url": "https://example.org/events/expired-event",
                    "candidate_policy": "official-listing-authority-v1",
                },
                {
                    "title": "Active Exhibition",
                    "when": active_when,
                    "start_date": start.isoformat(),
                    "end_date": "",
                    "url": "https://example.org/events/active-exhibition",
                    "candidate_policy": "official-listing-authority-v1",
                },
            ]
        }
    )

    assert [item["title"] for item in payload["results"]] == ["Active Exhibition"]
    assert payload["expired_events_removed"] == 1
