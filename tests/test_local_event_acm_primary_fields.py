from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import open_detail_fields_authority as authority  # noqa: E402


def test_parent_activity_date_wins_over_larger_child_schedule(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_WHEN",
        lambda card: (
            "22–23 Feb 2025; 25–26 Feb 2025; 28 Feb 2025",
            "child schedule",
        ),
    )
    card = {
        "detail_dates": [
            "7–9 Mar 2025",
            "22–23 Feb 2025 (Saturday & Sunday); "
            "25–26 Feb 2025 (Tuesday & Wednesday); 28 Feb 2025 (Friday)",
        ]
    }

    when, source_line = authority.pick_when(card)

    assert when == "7–9 Mar 2025"
    assert source_line == "7–9 Mar 2025"


def test_pagoda_parent_date_wins_over_daily_time_only(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_WHEN",
        lambda card: ("Daily – 11am–6pm", "Daily – 11am–6pm"),
    )
    card = {
        "detail_dates": [
            "22–23 February 2025",
            "Sat and Sun, 22–23 Feb",
            "Sun, 23 Feb",
        ]
    }

    assert authority.pick_when(card)[0] == "22–23 February 2025"


def test_in_gallery_taxonomy_is_not_a_venue(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_VENUE",
        lambda source, card, when, when_line: "In-gallery",
    )

    venue = authority.pick_venue(
        {
            "name": "Asian Civilisations Museum",
            "default_venue": "Asian Civilisations Museum",
        },
        {},
        "22–23 February 2025",
        "22–23 February 2025",
    )

    assert venue == "Asian Civilisations Museum"


def test_explicit_venue_skips_category_and_finds_physical_place(monkeypatch) -> None:
    monkeypatch.setattr(authority, "_BASE_EXPLICIT_VENUE", lambda card: "In-gallery")
    card = {
        "text_lines": [
            "In-gallery",
            "Special Exhibitions Gallery, Level 2",
        ]
    }

    assert authority.explicit_venue(card) == "Special Exhibitions Gallery, Level 2"


def test_equal_score_summary_order_keeps_first_detail_paragraph() -> None:
    assert authority._SUMMARY_SORT_NEW in authority._browser.DETAIL_CARD_JS
    assert authority._SUMMARY_SORT_OLD not in authority._browser.DETAIL_CARD_JS
