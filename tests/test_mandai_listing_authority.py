from __future__ import annotations

import json
import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime.mandai_listing_authority import (  # noqa: E402
    OfficialListingCardURL,
    mandai_event,
    review_detail,
)


LISTING_URL = "https://www.mandai.com/en/discover-mandai/events.html"
SOURCE = {
    "id": "mandai",
    "name": "Mandai Wildlife Group",
    "default_venue": "Mandai Wildlife Reserve",
}


def card() -> dict:
    lines = [
        "Keeper Talk",
        "Location",
        "Singapore Zoo",
        "Date",
        "Daily",
        "Time",
        "10:30am",
        "Meet the keepers and learn how the animals are cared for every day.",
    ]
    return {
        "id": "mandai-card-1",
        "url": LISTING_URL,
        "link_text": "",
        "headings": ["Keeper Talk"],
        "text": "\n".join(lines),
        "text_lines": lines,
        "detail_url_count": 0,
        "detail_urls": [],
        "page_url": LISTING_URL,
        "listing_url": LISTING_URL,
        "listing_only": True,
    }


def test_complete_mandai_card_without_detail_page_is_an_event() -> None:
    event = mandai_event(SOURCE, card())

    assert event is not None
    assert event["title"] == "Keeper Talk"
    assert event["when"] == "Daily · 10:30am"
    assert event["where"] == "Singapore Zoo"
    assert event["listing_only"] is True
    assert "Meet the keepers" in event["summary"]


def test_review_uses_listing_content_without_opening_a_detail_page() -> None:
    detail = review_detail(SOURCE, LISTING_URL, card())

    assert detail["detail_url"] == LISTING_URL
    assert detail["detail_status"] == "collected"
    assert detail["detail_page_title"] == ""
    assert detail["title"] == "Keeper Talk"


def test_listing_url_serializes_normally_but_card_identities_stay_distinct() -> None:
    first = OfficialListingCardURL(LISTING_URL, "card-one")
    second = OfficialListingCardURL(LISTING_URL, "card-two")

    assert str(first) == str(second) == LISTING_URL
    assert first != second
    assert len({first, second}) == 2
    assert json.dumps({"url": first}) == json.dumps({"url": LISTING_URL})
