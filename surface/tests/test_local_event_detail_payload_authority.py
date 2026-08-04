from __future__ import annotations

import sys
from datetime import date

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import detail_payload_authority as authority  # noqa: E402
from local_events_runtime import extract  # noqa: E402
from local_events_runtime import review_detail_navigation_authority as navigation  # noqa: E402
from local_events_runtime.source_overrides import LISTING_EVIDENCE  # noqa: E402


authority.apply()


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


def test_gardens_labeled_fields_outrank_promotion_and_advisory() -> None:
    source = {
        "id": "gardensbythebay",
        "name": "Gardens by the Bay",
        "default_venue": "Gardens by the Bay",
    }
    detail_url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/"
        "orchid-extravaganza-2026.html"
    )
    listing_url = (
        "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events.html"
    )
    card = {
        "id": "gardens-orchid-extravaganza",
        "url": detail_url,
        "headings": ["Orchid Extravaganza"],
        "link_text": "Orchid Extravaganza",
        "text": "Orchid Extravaganza",
        "text_lines": ["Orchid Extravaganza"],
        "extraction_mode": "detail_link",
        "listing_evidence": LISTING_EVIDENCE,
        "listing_url": listing_url,
        "listing_card_id": "gardens-orchid-extravaganza",
    }
    activity_date = "Fri, 3 Jul - Mon, 10 Aug 2026"
    activity_time = "9.00am - 9.00pm"
    promotion = (
        "Visit Flower Dome from 3 Jul to 10 Aug 2026, scan the QR code and "
        "answer a simple question for a chance to win."
    )
    advisory = "Advisory for use of tripods at Disney Garden of Wonder"
    summary = (
        "Discover orchids presented through the rich cultures and landscapes "
        "of Indonesia in this special floral display."
    )
    payload = {
        "title": "Orchid Extravaganza",
        "dates": [activity_date, promotion],
        "times": [activity_time],
        "venues": ["Flower Dome", advisory],
        "summary": summary,
        "summary_candidates": [summary],
        "lines": [
            "Orchid Extravaganza",
            "Opening Hours",
            activity_date,
            activity_time,
            "Location",
            "Flower Dome",
            promotion,
            advisory,
        ],
        "headings": ["Orchid Extravaganza"],
        "image_alts": [],
        "eventObjects": [],
        "canonical": detail_url,
    }

    merged = authority.merge_detail_payload(card, payload)
    event, reason = extract.event_from_card(source, merged)

    assert reason == "accepted"
    assert event is not None
    assert event["when"] == f"{activity_date} · {activity_time}"
    assert event["where"] == "Flower Dome"
    assert promotion not in event["when"]
    assert advisory not in event["where"]


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
    card = {"detail_dates": ["2026-06-19", "2027-01-24"]}
    assert authority._authoritative_when(card) == "19 Jun 2026 – 24 Jan 2027"


def test_review_uses_exact_ltn_date_time_and_venue_rows() -> None:
    payload = {
        "title": "Light to Night at ACM: Power of Play",
        "dates": ["23, 24, 30, 31 Jan 2026"],
        "venues": ["Asian Civilisations Museum, 1 Empress Place, Singapore 179555"],
        "lines": [
            "Light to Night at ACM: Power of Play",
            "Date",
            "23, 24, 30, 31 Jan 2026",
            "Time",
            "6pm–10pm",
            "Venue",
            "Asian Civilisations Museum, 1 Empress Place, Singapore 179555",
        ],
    }

    assert navigation._raw_when(payload) == (
        "23, 24, 30, 31 Jan 2026 · 6pm–10pm"
    )
    assert navigation._raw_where(payload) == (
        "Asian Civilisations Museum, 1 Empress Place, Singapore 179555"
    )


def test_review_does_not_invent_location_when_page_has_none() -> None:
    payload = {
        "title": "Programme without a location row",
        "dates": ["30–31 May 2026"],
        "venues": [],
        "lines": [
            "Programme without a location row",
            "Date",
            "30–31 May 2026",
            "Time",
            "10am–5pm",
        ],
    }

    assert navigation._raw_when(payload) == "30–31 May 2026 · 10am–5pm"
    assert navigation._raw_where(payload) == ""


def test_review_does_not_call_parser_or_field_rewriters() -> None:
    source = read_text(
        "surface/local_events_runtime/review_detail_navigation_authority.py"
    )

    assert "_extract.event_from_card(" not in source
    assert "_extract.pick_when(" not in source
    assert "_extract.pick_venue(" not in source
    assert "listing_summary=" not in source
    assert "_raw_when(payload)" in source
    assert "_raw_where(payload)" in source


def test_open_detail_owner_does_not_patch_detail_payload() -> None:
    source = read_text("surface/local_events_runtime/open_detail_fields_authority.py")

    assert "DETAIL_CARD_JS" not in source
    assert "merge_detail_payload" not in source
    assert "pick_when" not in source
    assert "pick_venue" not in source
    assert "source defaults must not overwrite" not in source


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
    assert 'add(lines, "time")' in script
    assert 'add(lines, "location")' in script
    assert "opening\\s+hours?" in script
    assert "labeleddates" in script
    assert "labeledtimes" in script
    assert "labeledvenues" in script
    assert "dates: ordereddates" in script
    assert "times: orderedtimes" in script
    assert "venues: orderedvenues" in script


def test_detail_payload_authority_is_applied_before_final_review_binding() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    payload = bootstrap.index("apply_detail_payload_authority()")
    binding = bootstrap.index("    _bind_final_browser_runtime_to_review()")
    diagnostics = bootstrap.index("apply_event_review_diagnostics()")

    assert payload < binding < diagnostics
