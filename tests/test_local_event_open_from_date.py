from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import listing_membership_authority as membership  # noqa: E402
from local_events_runtime import open_ended_date_authority as open_dates  # noqa: E402


DETAIL_URL = "https://www.nhb.gov.sg/acm/whats-on/exhibitions/elegant-sounds"


def card() -> dict:
    return {
        "listing_evidence": membership._source_overrides.LISTING_EVIDENCE,
        "listing_url": "https://www.acm.nhb.gov.sg/whats-on/overview",
        "listing_card_id": "acm-elegant-sounds",
        "detail_evidence": {
            "title": "Elegant Sounds: Music, Craft, and the Literati",
            "venue_candidates": ["Asian Civilisations Museum"],
        },
    }


def event(when: str) -> dict:
    return {
        "title": "Elegant Sounds: Music, Craft, and the Literati",
        "when": when,
        "where": "Asian Civilisations Museum",
        "host": "Asian Civilisations Museum",
        "source_name": "Asian Civilisations Museum",
        "url": DETAIL_URL,
        "summary": "Music, craft, and Chinese literati culture converge in this exhibition.",
        "start_date": "2025-05-23",
        "end_date": "",
        "kind": "event",
    }


def install_common_stubs(monkeypatch, row: dict, end: date) -> None:
    monkeypatch.setattr(
        membership._source_overrides,
        "_candidate_url",
        lambda source, raw: DETAIL_URL,
    )
    monkeypatch.setattr(
        membership._source_overrides,
        "_structured_event",
        lambda source, raw: dict(row),
    )
    monkeypatch.setattr(
        membership._source_overrides,
        "_event_end",
        lambda raw: end,
    )
    monkeypatch.setattr(
        membership._source_overrides,
        "_valid_title",
        lambda value: str(value or ""),
    )
    monkeypatch.setattr(
        membership._source_overrides,
        "_venue",
        lambda source, raw, evidence: evidence["venue_candidates"][0],
    )
    monkeypatch.setattr(membership._extract, "TODAY", date(2026, 7, 23))


def test_from_date_is_an_open_ended_current_label() -> None:
    assert open_dates.open_ended_value("From 23 May 2025") == "From 23 May 2025"
    assert open_dates.open_ended_value("from May 23, 2025") == "from May 23, 2025"


def test_elegant_sounds_is_not_rejected_as_past_date(monkeypatch) -> None:
    row = event("From 23 May 2025")
    install_common_stubs(monkeypatch, row, date(2025, 5, 23))
    monkeypatch.setattr(
        membership._extract,
        "current_date_label",
        lambda value: bool(open_dates.open_ended_value(value)),
    )

    result, reason = membership.event_from_card(
        {"id": "acm", "name": "Asian Civilisations Museum"},
        card(),
    )

    assert reason == "accepted"
    assert result is not None
    assert result["when"] == "From 23 May 2025"
    assert result["where"] == "Asian Civilisations Museum"


def test_real_ended_range_is_still_rejected(monkeypatch) -> None:
    row = event("10–12 April 2026")
    row["start_date"] = "2026-04-10"
    row["end_date"] = "2026-04-12"
    install_common_stubs(monkeypatch, row, date(2026, 4, 12))
    monkeypatch.setattr(
        membership._extract,
        "current_date_label",
        lambda value: False,
    )

    result, reason = membership.event_from_card(
        {"id": "acm", "name": "Asian Civilisations Museum"},
        card(),
    )

    assert result is None
    assert reason == "past_date"
