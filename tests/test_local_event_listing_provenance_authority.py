from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import listing_provenance_authority as authority  # noqa: E402


def test_official_listing_can_back_a_cross_domain_event_detail() -> None:
    listing = "https://www.rwsentosa.com/en/events"
    detail = "https://www.singaporeoceanarium.com/en/visit/events/one-year-anniversary.html"

    assert authority.listing_detail_url(listing, detail) == detail


def test_acm_relative_detail_link_is_resolved_from_the_official_listing() -> None:
    listing = "https://www.acm.nhb.gov.sg/whats-on/overview"
    href = (
        "/whats-on/exhibitions/"
        "crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre"
    )

    assert authority.listing_detail_url(listing, href) == (
        "https://www.acm.nhb.gov.sg/whats-on/exhibitions/"
        "crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre"
    )


def test_listing_provenance_rejects_self_media_credentials_and_non_http_targets() -> None:
    listing = "https://events.example/whats-on"

    assert authority.listing_detail_url(listing, listing) == ""
    assert authority.listing_detail_url(listing, "/poster.pdf") == ""
    assert authority.listing_detail_url(listing, "javascript:alert(1)") == ""
    assert authority.listing_detail_url(listing, "https://user:pass@example.org/event") == ""


def test_configured_card_selector_does_not_require_complete_list_fields() -> None:
    source = {
        "id": "acm",
        "listing_urls": ["https://www.acm.nhb.gov.sg/whats-on/overview"],
        "card_selectors": ["a.a-listing-content__anchor-card[href]"],
    }
    card = {
        "id": "acm-crosscurrents",
        "url": (
            "https://www.acm.nhb.gov.sg/whats-on/exhibitions/"
            "crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre"
        ),
        "detail_urls": [],
        "detail_url_count": 0,
        "extraction_mode": "detail_link",
        "text": "",
        "text_lines": [],
        "headings": [],
        "link_text": "",
    }

    admitted = authority._listing_card(source, card, source["listing_urls"][0])

    assert admitted is not None
    assert admitted["listing_evidence"] == "official_activity_listing_card"
    assert admitted["detail_url_count"] == 1
    assert admitted["url"].endswith("musee-du-louvre")


def test_official_listing_domain_checks_remain_in_manual_listing_validation() -> None:
    manual = read_text("surface/local_events_runtime/manual_listing.py")

    assert "listing URL is outside the institution allow-list" in manual
    assert "source.get(\"allowed_domains\")" in manual
