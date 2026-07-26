from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_payload_authority as authority  # noqa: E402
from local_events_runtime import extract  # noqa: E402
from local_events_runtime import open_detail_fields_authority as acm_fields  # noqa: E402
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


authority.apply()


ACM_FACTS = {
    "date": "10–12 April 2026",
    "time": "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm",
    "venue": "Asian Civilisations Museum",
    "admission": "Free and ticketed activities available",
}


def test_acm_detail_payload_produces_date_venue_and_description() -> None:
    source = {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "default_venue": "Asian Civilisations Museum",
    }
    detail_url = "https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre"
    listing_url = "https://www.acm.nhb.gov.sg/whats-on/overview"
    card = {
        "id": "acm-crosscurrents",
        "url": detail_url,
        "headings": [
            "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre"
        ],
        "link_text": "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre",
        "text": "Crosscurrents",
        "text_lines": ["Crosscurrents"],
        "extraction_mode": "detail_link",
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": listing_url,
        "listing_card_id": "acm-crosscurrents",
    }
    summary = (
        "From the 16th to 18th century, three great empires – the Mughals, "
        "Safavids, and Ottomans – shaped a vast and interconnected world across Asia."
    )
    payload = {
        "title": "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre",
        "dates": ["19 Jun 2026 – 24 Jan 2027"],
        "venues": [
            "Islamic Art Gallery, Level 2 and Design Gallery, Level 3",
            "Asian Civilisations Museum, 1 Empress Place, Singapore 179555",
        ],
        "summary": summary,
        "summary_candidates": [summary],
        "lines": [
            "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre",
            "Last Updated",
            "30 Jun 2026",
        ],
        "headings": [
            "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre"
        ],
        "image_alts": [],
        "eventObjects": [],
        "canonical": card["url"],
    }

    merged = authority.merge_detail_payload(card, payload)
    event, reason = extract.event_from_card(source, merged)

    assert reason == "accepted"
    assert event is not None
    assert event["when"] == "19 Jun 2026 – 24 Jan 2027"
    assert extract.label_dates(event["when"]) == [
        date(2026, 6, 19),
        date(2027, 1, 24),
    ]
    assert event["where"] == "Islamic Art Gallery, Level 2 and Design Gallery, Level 3"
    assert event["summary"].startswith("From the 16th to 18th century")
    assert event["when"] != "30 Jun 2026"


def test_site_metadata_cta_is_not_an_event_summary() -> None:
    cta = "Visit Asian Civilisations Museum today BOOK YOUR TICKET NOW"
    narrative = (
        "From the 16th to 18th century, three great empires shaped a vast and "
        "interconnected world across Asia through art, trade, and diplomacy."
    )

    assert authority.useful_event_summary(cta) == ""
    assert authority.useful_event_summary(narrative) == narrative


def test_narrative_candidate_wins_when_payload_summary_is_cta() -> None:
    narrative = (
        "This exhibition presents one hundred masterpieces from the Louvre, drawn "
        "from royal collections and later acquisitions across several centuries."
    )
    merged = authority.merge_detail_payload(
        {"text": "Listing card", "extraction_mode": "detail_link"},
        {
            "title": "Crosscurrents",
            "summary": "Visit Asian Civilisations Museum today BOOK YOUR TICKET NOW",
            "summary_candidates": [narrative],
            "dates": [],
            "venues": [],
            "lines": [],
        },
    )

    assert merged["detail_summary"] == narrative
    assert merged["detail_summary_candidates"] == [narrative]


def test_separate_structured_start_and_end_dates_become_one_range() -> None:
    card = {
        "detail_dates": ["2026-06-19", "2027-01-24"],
    }

    assert authority._authoritative_when(card) == "19 Jun 2026 – 24 Jan 2027"


def test_acm_parent_payload_keeps_combined_when_and_parent_venue() -> None:
    expected_when = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )
    merged = authority.merge_detail_payload(
        {
            "text": "Weekend of Curiosities\nDaily\nRiver Room",
            "text_lines": ["Weekend of Curiosities", "Daily", "River Room"],
            "extraction_mode": "detail_link",
        },
        {
            "title": "Weekend of Curiosities",
            "dates": [expected_when],
            "venues": ["Asian Civilisations Museum"],
            "summary": "A weekend programme of activities presented throughout the museum.",
            "summary_candidates": [],
            "lines": [
                "Weekend of Curiosities",
                "Date",
                expected_when,
                "Location",
                "Asian Civilisations Museum",
                "River Room",
            ],
        },
    )

    assert authority._authoritative_when(merged) == expected_when
    assert authority._authoritative_venue(merged) == "Asian Civilisations Museum"
    assert merged["detail_dates"] == [expected_when]
    assert merged["detail_venues"] == ["Asian Civilisations Museum"]


def test_acm_parent_wrapper_preserves_structured_parent_facts() -> None:
    source = read_text("surface/local_events_runtime/open_detail_fields_authority.py")

    assert "infoscreen_acm_parent_fields_v2" in source
    assert 'add("Date")' in source
    assert 'add("Time")' in source
    assert 'add("Location")' in source
    assert 'add("Admission")' in source
    assert "primary_facts: facts" in source
    assert "dates: [when]" in source
    assert "venues: [facts.venue]" in source


def test_final_acm_when_and_where_prefer_structured_parent_facts(monkeypatch) -> None:
    monkeypatch.setattr(
        acm_fields,
        "_BASE_PICK_WHEN",
        lambda card: ("Daily - Friday, 5–9.30pm", "listing fallback"),
    )
    monkeypatch.setattr(
        acm_fields,
        "_BASE_PICK_VENUE",
        lambda source, card, when, when_line: "River Room",
    )
    card = {"detail_primary_facts": ACM_FACTS}

    when, source_line = acm_fields.pick_when(card)
    venue = acm_fields.pick_venue(
        {"id": "acm", "name": "Asian Civilisations Museum"},
        card,
        when,
        source_line,
    )

    expected_when = (
        "10–12 April 2026 · "
        "Daily - Friday, 5–9.30pm / Sat & Sun, 2–9.30pm"
    )
    assert when == expected_when
    assert source_line == expected_when
    assert venue == "Asian Civilisations Museum"
    assert when != "Daily - Friday, 5–9.30pm"
    assert venue != "River Room"


def test_review_lifecycle_rejection_uses_final_detail_field_authorities() -> None:
    source = read_text(
        "surface/local_events_runtime/review_detail_navigation_authority.py"
    )
    event_none = source[
        source.index("        if event is None:"):
        source.index("        return {", source.index("        if event is None:") + 1)
    ]

    assert "_extract.pick_when(merged)" in event_none
    assert "_extract.pick_venue(" in event_none
    assert "_detail_dates._activity_pick_when(merged)" not in event_none
    assert "_detail_dates._activity_pick_venue(" not in event_none


def test_detail_dom_extractor_reads_structural_fields_and_rejects_metadata_cta() -> None:
    script = authority.ENRICHED_DETAIL_JS.lower()

    assert "itemprop='startdate'" in script
    assert "itemprop='enddate'" in script
    assert "event-location" in script
    assert "event-venue" in script
    assert "itemprop='description'" in script
    assert "summary_candidates" in script
    assert "structured_event" in script
    assert "visit\\s+.{0,100}?\\s+today" in script
    assert "(0, 100)" not in script
    assert 'add(lines, "date")' in script
    assert 'add(lines, "location")' in script


def test_detail_payload_authority_is_applied_before_final_review_binding() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    payload = bootstrap.index("apply_detail_payload_authority()")
    binding = bootstrap.index("    _bind_final_browser_runtime_to_review()")
    diagnostics = bootstrap.index("apply_event_review_diagnostics()")

    assert payload < binding < diagnostics
