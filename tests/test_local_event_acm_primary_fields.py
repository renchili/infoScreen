from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_payload_authority  # noqa: E402
from local_events_runtime import open_detail_fields_authority as authority  # noqa: E402
from local_events_runtime import open_ended_date_authority as open_dates  # noqa: E402


detail_payload_authority.apply()
authority.apply()


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


def test_explicit_short_venue_is_preserved(monkeypatch) -> None:
    monkeypatch.setattr(
        authority,
        "_BASE_PICK_VENUE",
        lambda source, card, when, when_line: "ACM Green",
    )

    venue = authority.pick_venue(
        {
            "name": "Asian Civilisations Museum",
            "default_venue": "Asian Civilisations Museum",
        },
        {},
        "7–9 March 2025",
        "7–9 March 2025",
    )

    assert venue == "ACM Green"


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


def dia_de_los_muertos_card() -> dict:
    return {
        "text_lines": [
            "Dia De Los Muertos (Day of the Dead)",
            "Now till 5 November 2023",
            "Daily - 10am - 7pm",
            "Fridays - 10am - 9pm",
            "Contemporary Gallery, Level 1",
        ],
        "text": "\n".join(
            [
                "Dia De Los Muertos (Day of the Dead)",
                "Now till 5 November 2023",
                "Daily - 10am - 7pm",
                "Fridays - 10am - 9pm",
                "Contemporary Gallery, Level 1",
            ]
        ),
    }


def test_now_till_is_end_bounded_not_open_ended() -> None:
    label = "Now till 5 November 2023"

    assert open_dates.closed_end_value(label) == label
    assert open_dates.open_ended_value(label) == ""
    assert open_dates.open_ended_value("Daily - 10am - 7pm") == (
        "Daily - 10am - 7pm"
    )


def test_now_till_date_wins_over_daily_recurrence(monkeypatch) -> None:
    monkeypatch.setattr(
        open_dates,
        "_BASE_PICK_WHEN",
        lambda card: ("Daily - 10am - 7pm", "Daily - 10am - 7pm"),
    )

    when, source_line = open_dates.pick_when(dia_de_los_muertos_card())

    assert when == "Now till 5 November 2023"
    assert source_line == "Now till 5 November 2023"


def test_now_till_past_candidate_expires(monkeypatch) -> None:
    today = date(2026, 7, 25)

    def base_current(label: str) -> bool:
        dates = open_dates._extract.label_dates(label)
        return bool(dates and max(dates) >= today)

    def base_expired(candidate: SimpleNamespace) -> bool:
        dates = authority._extract.label_dates(candidate.when)
        return bool(dates and max(dates) < today)

    monkeypatch.setattr(open_dates, "_BASE_CURRENT_DATE_LABEL", base_current)
    monkeypatch.setattr(
        authority._extract,
        "current_date_label",
        open_dates.current_date_label,
    )
    monkeypatch.setattr(authority, "_BASE_CANDIDATE_EXPIRED", base_expired)

    candidate = SimpleNamespace(when="Now till 5 November 2023")

    assert open_dates.current_date_label(candidate.when) is False
    assert authority.candidate_expired(candidate) is True


def test_acm_parent_fact_component_wraps_every_detail_extractor() -> None:
    scripts = (
        authority._detail_dates.ACTIVITY_DETAIL_JS,
        authority._browser.DETAIL_CARD_JS,
        authority._source_overrides.AUTHORITATIVE_DETAIL_JS,
    )

    for script in scripts:
        assert authority._ACM_PRIMARY_FACTS_MARKER in script
        assert "facts.dateRow.text" in script
        assert "facts.timeRow.text" in script
        assert "facts.venueRow.text" in script
        assert "dates: when ? [when] : []" in script
        assert "venues: venue ? [venue] : []" in script
        assert "drop-in activities" in script


def test_acm_parent_date_and_time_stay_in_one_when_value() -> None:
    value = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )

    assert authority._primary_detail_date({"detail_dates": [value]}) == value


def test_acm_parent_venue_is_not_selected_from_a_global_venue_list() -> None:
    assert not hasattr(authority, "_primary_detail_venue")
