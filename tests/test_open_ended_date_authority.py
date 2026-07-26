from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import extract  # noqa: E402
from local_events_runtime.open_ended_date_authority import apply  # noqa: E402
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


SOURCE = {
    "id": "nationalgallery",
    "name": "National Gallery Singapore",
    "default_venue": "National Gallery Singapore",
}


def test_ongoing_detail_page_is_not_rejected_for_missing_calendar_date() -> None:
    apply()
    detail_url = "https://www.nationalgallery.sg/sg/en/exhibitions/singapore-stories.html"
    listing_url = "https://www.nationalgallery.sg/sg/en/whats-on.html"
    lines = [
        "Singapore Stories",
        "When",
        "Ongoing",
        "Where",
        "City Hall Wing, Level 2, DBS Singapore Gallery",
        "Explore the evolving story of Singapore through the national collection.",
    ]
    card = {
        "id": "national-gallery-singapore-stories",
        "url": detail_url,
        "headings": ["Singapore Stories"],
        "link_text": "Singapore Stories",
        "text": "\n".join(lines),
        "text_lines": lines,
        "detail_url_count": 1,
        "detail_urls": [detail_url],
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": listing_url,
        "listing_card_id": "national-gallery-singapore-stories",
    }

    event, reason = extract.event_from_card(SOURCE, card)

    assert reason == "accepted"
    assert event is not None
    assert event["title"] == "Singapore Stories"
    assert event["when"] == "Ongoing"
    assert event["url"].endswith("/singapore-stories.html")
