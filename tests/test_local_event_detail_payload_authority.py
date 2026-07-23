from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_payload_authority as authority  # noqa: E402
from local_events_runtime import extract  # noqa: E402


authority.apply()


def test_acm_detail_payload_produces_date_venue_and_description() -> None:
    source = {
        "id": "acm",
        "name": "Asian Civilisations Museum",
        "default_venue": "Asian Civilisations Museum",
    }
    card = {
        "url": "https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre",
        "headings": [
            "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre"
        ],
        "link_text": "Crosscurrents: Masterpieces of Mughal, Safavid, and Ottoman Art from the Musée du Louvre",
        "text": "Crosscurrents",
        "text_lines": ["Crosscurrents"],
        "extraction_mode": "detail_link",
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


def test_detail_dom_extractor_reads_structural_fields_and_rejects_metadata_cta() -> None:
    script = authority.ENRICHED_DETAIL_JS.lower()

    assert "itemprop='startdate'" in script
    assert "itemprop='enddate'" in script
    assert "event-location" in script
    assert "event-venue" in script
    assert "itemprop='description'" in script
    assert "summary_candidates" in script
    assert "structured_event" in script
    assert "book\\s+(?:your\\s+)?tickets" in script
    assert 'add(lines, "date")' in script
    assert 'add(lines, "location")' in script


def test_detail_payload_authority_is_applied_before_final_review_binding() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    payload = bootstrap.index("apply_detail_payload_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")
    diagnostics = bootstrap.index("apply_event_review_diagnostics()")

    assert payload < binding < diagnostics
