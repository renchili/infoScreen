from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import (  # noqa: E402
    browser,
    detail_date_authority,
    extract,
    listing_membership_authority,
    listing_provenance_authority,
    official_feeds,
    open_ended_date_authority,
    source_overrides,
)
from local_events_runtime.output import normalize_payload  # noqa: E402
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


source_overrides.apply()
detail_date_authority.apply()
open_ended_date_authority.apply()
listing_provenance_authority.apply()
listing_membership_authority.apply()


def _listing_card(source: dict, card: dict, listing_url: str):
    return source_overrides._listing_card(source, card, listing_url)


def _merge_detail(source: dict, card: dict, payload: dict, index: int):
    return source_overrides._merge_detail(source, card, payload, index)


def _prefer_structured(
    structured: list[dict],
    dom: list[dict],
    limit: int,
):
    return source_overrides._prefer_structured(structured, dom, limit)


def canonical_detail_url(source: dict, value: object) -> bool:
    return source_overrides.canonical_detail_url(source, value)


def source() -> dict:
    return {
        "id": "official-source",
        "name": "Official Source",
        "default_venue": "Official Venue",
        "allowed_domains": ["example.org"],
        "listing_urls": ["https://example.org/whats-on"],
    }


def future_label(days: int = 30) -> str:
    value = date.today() + timedelta(days=days)
    return f"{value.day} {value.strftime('%b')} {value.year}"


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


def prefer_with_context(
    policy_source: dict,
    listing_url: str,
    structured: list[dict],
    dom: list[dict],
    limit: int = 10,
) -> list[dict]:
    token = source_overrides._listing_context.set((policy_source, listing_url))
    try:
        return _prefer_structured(structured, dom, limit)
    finally:
        source_overrides._listing_context.reset(token)


def test_browser_discovers_isolated_listing_cards_without_a_date_gate() -> None:
    assert 'el.matches && el.matches("a[href]")' in browser.CARD_JS
    assert "listingDetailUrls.length !== 1" in browser.CARD_JS
    assert 'if (!hasDateText(textLines(card).join(" "))) continue;' not in browser.CARD_JS
    assert "#nhb-" not in browser.CARD_JS.split(
        'push(out, seen, el, url, "", "nhb_dom_card")', 1
    )[0].split("function pushNhbCards", 1)[-1]


def test_deep_scroll_stops_only_after_the_listing_is_stable() -> None:
    assert "stableRounds >= 3" in browser.PREPARE_PAGE_JS
    assert "scrollTo(0, document.body.scrollHeight)" in browser.PREPARE_PAGE_JS
    assert "new Set(links).size" in browser.PREPARE_PAGE_JS
    assert "Math.max(Number(args.maxRounds || 0), 24)" in browser.PREPARE_PAGE_JS


def test_detail_url_validation_uses_listing_provenance_not_target_domain() -> None:
    policy_source = source()
    assert canonical_detail_url(policy_source, "https://example.org/whats-on/family-sports-day")
    assert canonical_detail_url(policy_source, "https://example.org/whats-on/plan-your-itinerary")
    assert canonical_detail_url(policy_source, "https://tickets.example/events/family-sports-day")
    assert not canonical_detail_url(policy_source, "https://example.org/whats-on")
    assert not canonical_detail_url(policy_source, "https://example.org/#nhb-generated")
    assert not canonical_detail_url(policy_source, "https://example.org/media/card.jpg")


def test_official_listing_card_without_date_is_admitted_for_detail_enrichment() -> None:
    card = dom_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        "Details available on the official page",
    )

    admitted = _listing_card(source(), card, "https://example.org/whats-on")

    assert admitted is not None
    assert admitted["listing_evidence"] == LISTING_EVIDENCE
    assert admitted["url"] == "https://example.org/whats-on/family-sports-day"


def test_real_listing_card_is_positive_activity_membership_evidence() -> None:
    card = admitted_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        future_label(),
    )

    assert card["listing_evidence"] == LISTING_EVIDENCE
    assert card["listing_url"] == "https://example.org/whats-on"
    assert card["listing_card_id"] == "listing-card-1"


def test_unmatched_structured_records_are_dropped() -> None:
    unrelated = official_feeds.event_card(
        {
            "title": "Carpark",
            "when": future_label(),
            "where": "Official Venue",
            "url": "https://example.org/amenities/carpark",
            "summary": "Carpark rates",
            "start_date": (date.today() + timedelta(days=30)).isoformat(),
            "end_date": (date.today() + timedelta(days=30)).isoformat(),
        },
        "official-source",
        0,
    )
    listing = dom_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        future_label(),
    )

    cards = prefer_with_context(source(), "https://example.org/whats-on", [unrelated], [listing])

    assert len(cards) == 1
    assert cards[0]["link_text"] == "Family Sports Day"
    assert cards[0].get("structured_event") is None
    assert cards[0]["listing_evidence"] == LISTING_EVIDENCE


def test_matching_structured_data_only_enriches_a_listed_activity() -> None:
    url = "https://example.org/whats-on/family-sports-day"
    target = date.today() + timedelta(days=30)
    structured = official_feeds.event_card(
        {
            "title": "Family Sports Day",
            "when": future_label(),
            "where": "Sports Hall",
            "url": "https://example.org/api/items/123",
            "summary": "A day of family activities.",
            "start_date": target.isoformat(),
            "end_date": target.isoformat(),
        },
        "official-source",
        0,
    )
    listing = dom_card("Family Sports Day", url, future_label())

    cards = prefer_with_context(source(), "https://example.org/whats-on", [structured], [listing])

    assert len(cards) == 1
    assert cards[0]["url"] == url
    assert cards[0]["structured_event"]["url"] == url
    assert cards[0]["structured_event"]["where"] == "Sports Hall"
    assert cards[0]["listing_evidence"] == LISTING_EVIDENCE


def test_listing_context_is_isolated_per_worker() -> None:
    barrier = Barrier(2)

    def worker(host: str) -> tuple[str, str]:
        listing_url = f"https://{host}/whats-on"
        detail_url = f"https://{host}/whats-on/family-sports-day"
        policy_source = {
            "id": host,
            "name": host,
            "default_venue": host,
            "allowed_domains": [host],
            "listing_urls": [listing_url],
        }
        listing = dom_card("Family Sports Day", detail_url, future_label())
        listing["page_url"] = listing_url
        token = source_overrides._listing_context.set((policy_source, listing_url))
        try:
            barrier.wait()
            cards = _prefer_structured([], [listing], 10)
            assert len(cards) == 1
            return cards[0]["listing_url"], cards[0]["url"]
        finally:
            source_overrides._listing_context.reset(token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, "alpha.example")
        second = executor.submit(worker, "beta.example")
        results = {first.result(), second.result()}

    assert results == {
        (
            "https://alpha.example/whats-on",
            "https://alpha.example/whats-on/family-sports-day",
        ),
        (
            "https://beta.example/whats-on",
            "https://beta.example/whats-on/family-sports-day",
        ),
    }


def test_detail_page_corrects_title_date_and_venue_without_source_rules() -> None:
    target = date.today() + timedelta(days=30)
    url = "https://example.org/whats-on/magical-island-adventure"
    card = admitted_card("Meet and Greet", url, future_label())
    detail = {
        "canonical": url,
        "title": "Magical Island Adventure | Character Meet & Greet",
        "eventObjects": [
            {
                "@type": "Event",
                "name": "Magical Island Adventure | Character Meet & Greet",
                "startDate": target.isoformat(),
                "endDate": target.isoformat(),
                "location": "Palawan Beach",
                "url": url,
            }
        ],
        "dates": [future_label()],
        "venues": ["Palawan Beach"],
        "lines": ["Meet the characters on the island adventure."],
        "summary": "Meet the characters on the island adventure.",
    }

    event, reason = extract.event_from_card(source(), _merge_detail(source(), card, detail, 0))

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Magical Island Adventure | Character Meet & Greet"
    assert event["start_date"] == target.isoformat()
    assert event["end_date"] == target.isoformat()
    assert event["where"] == "Palawan Beach"
    assert event["url"] == url
    assert event["candidate_policy"] == "official-listing-authority-v1"


def test_event_shaped_card_without_listing_evidence_is_rejected() -> None:
    card = dom_card(
        "Family Sports Day",
        "https://example.org/whats-on/family-sports-day",
        future_label(),
    )

    event, reason = extract.event_from_card(source(), card)

    assert event is None
    assert reason == "missing_official_listing_evidence"


def test_output_keeps_verified_current_and_incomplete_events() -> None:
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
                    "url": "https://example.org/events/expired",
                    "candidate_policy": "official-listing-authority-v1",
                },
                {
                    "title": "Unverified Event",
                    "when": tomorrow.isoformat(),
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                    "url": "https://example.org/events/unverified",
                },
                {
                    "title": "Current Event",
                    "when": tomorrow.isoformat(),
                    "start_date": tomorrow.isoformat(),
                    "end_date": tomorrow.isoformat(),
                    "url": "https://example.org/events/current",
                    "candidate_policy": "official-listing-authority-v1",
                },
                {
                    "title": "Incomplete Official Event",
                    "when": "",
                    "where": "Official Venue",
                    "url": "https://example.org/events/incomplete",
                    "candidate_policy": "official-listing-authority-v1",
                    "detail_status": "incomplete",
                },
            ]
        }
    )

    assert [item["title"] for item in payload["results"]] == [
        "Current Event",
        "Incomplete Official Event",
    ]
    assert payload["expired_events_removed"] == 1
    assert payload["invalid_events_removed"] == 1


def test_configuration_has_entrypoints_but_no_per_record_exclusions() -> None:
    payload = json.loads((SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8"))
    config_text = read_text("surface/conf/event_sources.json")
    implementation = read_text("surface/local_events_runtime/source_overrides.py")

    assert payload["version"] == 6
    assert payload["policy"]["source_specific_exclusion_lists"] is False
    assert "exclude_url_patterns" not in config_text
    assert "plan-your-itinerary" not in config_text
    assert "NON_EVENT_PATH_SEGMENTS" not in implementation
    assert "_known_non_event_url" not in implementation
    assert 'source_id == "gardensbythebay"' not in implementation
    assert 'source_id == "nationalmuseum"' not in implementation

    sources = {item["id"]: item for item in payload["sources"]}
    assert {
        "https://www.science.edu.sg/whats-on/workshops-activities",
        "https://www.science.edu.sg/whats-on/exhibitions",
        "https://www.science.edu.sg/whats-on/shows-demonstrations",
    } <= set(sources["sciencecentre"]["listing_urls"])
