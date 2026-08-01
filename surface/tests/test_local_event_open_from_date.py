from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import listing_membership_authority as membership  # noqa: E402
from local_events_runtime import open_detail_fields_authority as open_fields  # noqa: E402
from local_events_runtime import open_ended_date_authority as open_dates  # noqa: E402


DETAIL_URL = "https://www.nhb.gov.sg/acm/whats-on/exhibitions/elegant-sounds"
NARRATIVE = (
    "Elegant Sounds explores the evolution, symbolism, and role of the qin in "
    "Chinese literati culture through instruments, paintings, ceramics, and rare books."
)


def card() -> dict:
    return {
        "listing_evidence": membership._source_overrides.LISTING_EVIDENCE,
        "listing_url": "https://www.acm.nhb.gov.sg/whats-on/overview",
        "listing_card_id": "acm-elegant-sounds",
        "url": DETAIL_URL,
        "text_lines": [
            "Elegant Sounds: Music, Craft, and the Literati",
            "From 23 May 2025",
            "Asian Civilisations Museum",
            "Admission to Permanent Galleries",
            NARRATIVE,
        ],
        "text": "\n".join(
            [
                "Elegant Sounds: Music, Craft, and the Literati",
                "From 23 May 2025",
                "Asian Civilisations Museum",
                "Admission to Permanent Galleries",
                NARRATIVE,
            ]
        ),
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
        "summary": NARRATIVE,
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
    monkeypatch.setattr(membership._extract, "TODAY", date(2026, 7, 24))


def test_from_date_is_an_open_ended_current_label() -> None:
    assert open_dates.open_ended_value("From 23 May 2025") == "From 23 May 2025"
    assert open_dates.open_ended_value("from May 23, 2025") == "from May 23, 2025"


def test_complete_from_label_wins_before_generic_date_fragment(monkeypatch) -> None:
    monkeypatch.setattr(
        open_dates,
        "_BASE_PICK_WHEN",
        lambda raw: ("23 May 2025", "From 23 May 2025"),
    )

    when, source_line = open_dates.pick_when(card())

    assert when == "From 23 May 2025"
    assert source_line == "From 23 May 2025"


def test_review_lifecycle_does_not_expire_start_only_exhibition(monkeypatch) -> None:
    monkeypatch.setattr(open_fields, "_BASE_CANDIDATE_EXPIRED", lambda candidate: True)
    monkeypatch.setattr(
        open_fields._extract,
        "current_date_label",
        lambda value: bool(open_dates.open_ended_value(value)),
    )

    assert open_fields.candidate_expired(
        SimpleNamespace(when="From 23 May 2025")
    ) is False


def test_unlabelled_nhb_museum_line_is_an_explicit_venue(monkeypatch) -> None:
    monkeypatch.setattr(open_fields, "_BASE_EXPLICIT_VENUE", lambda raw: "")

    assert open_fields.explicit_venue(card()) == "Asian Civilisations Museum"


def test_admission_taxonomy_is_not_mistaken_for_venue(monkeypatch) -> None:
    monkeypatch.setattr(open_fields, "_BASE_EXPLICIT_VENUE", lambda raw: "")
    raw = {"text_lines": ["Admission to Permanent Galleries"]}

    assert open_fields.explicit_venue(raw) == ""


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


def test_open_detail_repair_is_installed_in_http_and_job_paths() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")
    job = read_text("surface/jobs/local_event_search.py")

    assert bootstrap.index("apply_open_ended_date_authority()") < bootstrap.index(
        "apply_open_detail_fields_authority()"
    ) < bootstrap.index("apply_listing_membership_authority()")
    assert job.index("open_ended_date_authority.apply()") < job.index(
        "open_detail_fields_authority.apply()"
    ) < job.index("listing_membership_authority.apply()")
