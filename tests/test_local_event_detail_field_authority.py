from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_date_authority as authority  # noqa: E402
from local_events_runtime import extract  # noqa: E402


authority.apply()


def test_esplanade_ampersand_dates_preserve_both_days() -> None:
    label = "12 & 13 Jun 2099"

    assert extract.date_fragments(f"FREE Music\n{label}\nEsplanade Theatre") == [label]
    assert extract.label_dates(label) == [date(2099, 6, 12), date(2099, 6, 13)]


def test_listing_fields_survive_incomplete_detail_read() -> None:
    source = {
        "id": "esplanade",
        "name": "Esplanade",
        "default_venue": "Esplanade",
    }
    card = {
        "headings": ["Example Performance"],
        "link_text": "Example Performance",
        "text": (
            "FREE Music\n"
            "12 & 13 Jun 2099\n"
            "Example Performance\n"
            "Esplanade Theatre"
        ),
        "text_lines": [
            "FREE Music",
            "12 & 13 Jun 2099",
            "Example Performance",
            "Esplanade Theatre",
        ],
    }
    detail = {
        "detail_url": "https://www.esplanade.com/whats-on/2099/example-performance",
        "title": "Example Performance",
        "when": "",
        "where": "",
        "summary": "",
        "detail_status": "incomplete",
        "detail_error": "listing_card_fields_incomplete",
        "detail_page_title": "Example Performance",
    }

    merged = authority._merge_detail_fields(source, card, detail)

    assert merged["when"] == "12 & 13 Jun 2099"
    assert merged["where"] == "Esplanade Theatre"
    assert merged["title"] == "Example Performance"


def test_listing_activity_date_cannot_be_replaced_by_last_updated_date() -> None:
    source = {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "default_venue": "Asian Civilisations Museum",
    }
    card = {
        "headings": ["Batik Kita"],
        "link_text": "Batik Kita",
        "text": (
            "Batik Kita\n"
            "17 Jun 2022 – 2 Oct 2022\n"
            "Special Exhibitions Gallery, Level 2"
        ),
        "text_lines": [
            "Batik Kita",
            "17 Jun 2022 – 2 Oct 2022",
            "Special Exhibitions Gallery, Level 2",
        ],
    }
    detail = {
        "detail_url": "https://www.acm.nhb.gov.sg/whats-on/exhibitions/batik-kita",
        "title": "Batik Kita",
        "when": "30 Jun 2026",
        "where": "",
        "summary": "",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "Batik Kita",
    }

    merged = authority._merge_detail_fields(source, card, detail)

    assert merged["when"] == "17 Jun 2022 – 2 Oct 2022"
    assert merged["where"] == "Special Exhibitions Gallery"
    assert authority._candidate_expired(SimpleNamespace(when=merged["when"])) is True


def test_detail_activity_extractor_rejects_page_metadata_dates() -> None:
    script = authority.ACTIVITY_DETAIL_JS.lower()

    assert "last updated" in script
    assert "previous programme" in script
    assert "next programme" in script
    assert "copyright" in script
    assert 'script[type*="ld+json" i]' in script
