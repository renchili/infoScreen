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


def test_kallang_labeled_event_fields_override_unrelated_page_dates() -> None:
    source = {
        "id": "thekallang",
        "name": "The Kallang",
        "default_venue": "The Kallang",
    }
    detail_card = {
        "headings": ["EXO PLANET #6 – EXhOrizon in SINGAPORE"],
        "link_text": "EXO PLANET #6 – EXhOrizon in SINGAPORE",
        "text_lines": [
            "EXO PLANET #6 – EXhOrizon in SINGAPORE",
            "Event Information",
            "Date",
            "Fri & Sun, 24 & 26 Jul 2026",
            "Location",
            "Singapore Indoor Stadium",
            "Notice - Venue Closures for National Day Parade",
            "19 & 27 Jul 2026",
            "Weverse Presale",
            "Start: 20 Apr 2026 : 12PM",
        ],
    }

    when, when_line = authority._activity_pick_when(detail_card)
    where = authority._activity_pick_venue(source, detail_card, when, when_line)

    assert when == "Fri & Sun, 24 & 26 Jul 2026"
    assert extract.label_dates(when) == [date(2026, 7, 24), date(2026, 7, 26)]
    assert where == "Singapore Indoor Stadium"


def test_kallang_detail_fields_replace_polluted_listing_fields() -> None:
    source = {
        "id": "thekallang",
        "name": "The Kallang",
        "default_venue": "The Kallang",
    }
    polluted_listing_card = {
        "headings": ["EXO PLANET #6 – EXhOrizon in SINGAPORE"],
        "link_text": "EXO PLANET #6 – EXhOrizon in SINGAPORE",
        "text": (
            "EXO PLANET #6 – EXhOrizon in SINGAPORE\n"
            "27 July 2026\n"
            "OCBC Arena"
        ),
        "text_lines": [
            "EXO PLANET #6 – EXhOrizon in SINGAPORE",
            "27 July 2026",
            "OCBC Arena",
        ],
    }
    detail = {
        "detail_url": "https://www.thekallang.com.sg/en/things-to-do/events/ex-horizon-world-tour.html",
        "title": "EXO PLANET #6 – EXhOrizon in SINGAPORE",
        "when": "Fri & Sun, 24 & 26 Jul 2026",
        "where": "Singapore Indoor Stadium",
        "summary": "",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "EXO PLANET #6 – EXhOrizon in SINGAPORE",
    }

    merged = authority._merge_detail_fields(source, polluted_listing_card, detail)

    assert merged["when"] == "Fri & Sun, 24 & 26 Jul 2026"
    assert merged["where"] == "Singapore Indoor Stadium"


def test_historical_activity_date_wins_over_last_updated_metadata() -> None:
    card = {
        "text_lines": [
            "Batik Kita",
            "Date",
            "17 Jun 2022 – 2 Oct 2022",
            "Location",
            "Special Exhibitions Gallery, Level 2",
            "Last Updated",
            "30 Jun 2026",
        ]
    }

    when, _ = authority._activity_pick_when(card)

    assert when == "17 Jun 2022 – 2 Oct 2022"
    assert authority._candidate_expired(SimpleNamespace(when=when)) is True


def test_detail_activity_extractor_scopes_primary_event_and_rejects_metadata() -> None:
    script = authority.ACTIVITY_DETAIL_JS.lower()

    assert "primaryheading" in script
    assert "primaryevent" in script
    assert "you may also like" in script
    assert "last updated" in script
    assert "previous programme" in script
    assert "next programme" in script
    assert "copyright" in script
    assert 'script[type*="ld+json" i]' in script
