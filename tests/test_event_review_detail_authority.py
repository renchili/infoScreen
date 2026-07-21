from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime.review_detail_authority import (  # noqa: E402
    _authoritative_title,
    _official_detail_url,
)


def acm_source() -> dict:
    return {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "allowed_domains": ["acm.nhb.gov.sg"],
        "listing_urls": ["https://www.acm.nhb.gov.sg/whats-on/overview"],
        "public_detail_url_rewrites": [],
    }


def test_review_prefers_detail_title_over_listing_card_title() -> None:
    payload = {"title": "ACM & Me"}
    event = {"title": "ACM Online"}
    merged = {
        "headings": ["ACM Online"],
        "link_text": "ACM Online",
    }

    assert _authoritative_title(payload, event, merged) == "ACM & Me"


def test_review_prefers_official_canonical_detail_url() -> None:
    payload = {
        "canonical": "https://www.acm.nhb.gov.sg/whats-on/details/acm-and-me#programme",
    }

    assert _official_detail_url(
        acm_source(),
        "https://www.acm.nhb.gov.sg/whats-on/overview",
        payload,
        "https://www.acm.nhb.gov.sg/whats-on/details/acm-online",
    ) == "https://www.acm.nhb.gov.sg/whats-on/details/acm-and-me"
