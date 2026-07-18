from __future__ import annotations

import json
import sys
from pathlib import Path

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import extract  # noqa: E402
from local_events_runtime.detail_authority import (  # noqa: E402
    apply as apply_detail_authority,
    detail_labeled_venue,
    public_detail_url,
)
from local_events_runtime.source_overrides import (  # noqa: E402
    LISTING_EVIDENCE,
    apply as apply_source_overrides,
)

apply_source_overrides()
apply_detail_authority()


def national_gallery_source() -> dict:
    return {
        "id": "nationalgallery",
        "name": "National Gallery Singapore",
        "allowed_domains": ["nationalgallery.sg"],
        "default_venue": "National Gallery Singapore",
        "listing_urls": ["https://www.nationalgallery.sg/sg/en/whats-on.html"],
        "public_detail_url_rewrites": [
            {"from": "/content/nationalgallerysg", "to": ""},
        ],
    }


def test_national_gallery_detail_page_supplies_specific_venue_and_public_url() -> None:
    cms_url = (
        "https://www.nationalgallery.sg/content/nationalgallerysg/sg/en/exhibitions/"
        "He-Xiangning-Ink-Intent.html"
    )
    public_url = (
        "https://www.nationalgallery.sg/sg/en/exhibitions/"
        "He-Xiangning-Ink-Intent.html"
    )
    card = {
        "id": "national-gallery-he-xiangning",
        "url": cms_url,
        "page_url": cms_url,
        "detail_urls": [cms_url],
        "detail_url_count": 1,
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": "https://www.nationalgallery.sg/sg/en/whats-on.html",
        "listing_card_id": "national-gallery-he-xiangning",
        "listing_extraction_mode": "detail_link",
        "extraction_mode": "detail_link",
        "link_text": "He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意",
        "headings": ["He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意"],
        "text_lines": [
            "He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意",
            "When:",
            "1 Apr – 23 Aug 2099",
            "Suitable For: All",
            "Where:",
            "City Hall Wing, Level 4, Wu Guanzhong Gallery",
            "Ticket Information: General Admission ticket required",
        ],
        "text": (
            "He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意\n"
            "When:\n1 Apr – 23 Aug 2099\nSuitable For: All\nWhere:\n"
            "City Hall Wing, Level 4, Wu Guanzhong Gallery\n"
            "Ticket Information: General Admission ticket required"
        ),
        "structured_event": {
            "title": "He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意",
            "when": "1 Apr – 23 Aug 2099",
            "where": "National Gallery Singapore",
            "url": cms_url,
            "summary": "A major travelling exhibition of He Xiangning's ink works.",
            "start_date": "2099-04-01",
            "end_date": "2099-08-23",
        },
        "detail_evidence": {
            "canonical_url": cms_url,
            "title": "He Xiangning: Ink & Intent | 何香凝：画就丹青凭寄意",
            "date_candidates": ["1 Apr – 23 Aug 2099"],
            "venue_candidates": [],
        },
        "detail_enriched": True,
        "screenshot": "",
    }

    event, reason = extract.event_from_card(national_gallery_source(), card)

    assert reason == "accepted"
    assert event is not None
    assert event["where"] == "City Hall Wing, Level 4, Wu Guanzhong Gallery"
    assert event["venue_authority"] == "official_detail_label"
    assert event["url"] == public_url
    assert event["url"] != card["listing_url"]


def test_detail_labeled_venue_supports_inline_and_separate_values() -> None:
    assert detail_labeled_venue(
        {"text_lines": ["Where: City Hall Wing, Level 4, Wu Guanzhong Gallery"]}
    ) == "City Hall Wing, Level 4, Wu Guanzhong Gallery"
    assert detail_labeled_venue(
        {"text_lines": ["Where:", "City Hall Wing, Level 4, Wu Guanzhong Gallery", "Get directions"]}
    ) == "City Hall Wing, Level 4, Wu Guanzhong Gallery"


def test_public_url_rewrite_is_source_configured_not_event_enumeration() -> None:
    source = national_gallery_source()
    assert public_detail_url(
        source,
        "https://www.nationalgallery.sg/content/nationalgallerysg/sg/en/exhibitions/example.html",
    ) == "https://www.nationalgallery.sg/sg/en/exhibitions/example.html"
    assert public_detail_url(
        {"public_detail_url_rewrites": []},
        "https://example.org/events/example.html#details",
    ) == "https://example.org/events/example.html"

    config_path = Path(SURFACE) / "conf" / "event_sources.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    gallery = next(item for item in config["sources"] if item["id"] == "nationalgallery")
    assert gallery["public_detail_url_rewrites"] == [
        {"from": "/content/nationalgallerysg", "to": ""}
    ]
    assert "He-Xiangning-Ink-Intent" not in config_path.read_text(encoding="utf-8")
