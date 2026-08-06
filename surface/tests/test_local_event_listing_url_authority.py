from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser  # noqa: E402
from local_events_runtime.listing_page_policy import rejection_reason  # noqa: E402
from local_events_runtime.listing_provenance_authority import listing_detail_url  # noqa: E402
from local_events_runtime.listing_url_authority import apply as apply_listing_url_authority  # noqa: E402
from local_events_runtime.preview_collector_authority import PREVIEW_LISTING_JS  # noqa: E402
from local_events_runtime.source_overrides import apply as apply_source_overrides  # noqa: E402


GARDENS_LISTING = (
    "https://www.gardensbythebay.com.sg/en/things-to-do/"
    "calendar-of-events.html"
)
GARDENS_RESOURCE = (
    "https://www.gardensbythebay.com.sg/en/learn-with-us/"
    "explore-resources/whats-blooming.html"
)
GARDENS_EVENT = (
    "https://www.gardensbythebay.com.sg/en/things-to-do/calendar-of-events/"
    "formula-1-exhibition-singapore.html"
)


def test_listing_detail_discovery_uses_official_list_provenance_not_target_domain() -> None:
    apply_source_overrides()
    apply_listing_url_authority()

    card_js = browser.CARD_JS
    assert "function officialDetailUrl(raw)" in card_js
    assert "The configured or operator-confirmed listing page is the official authority" in card_js
    assert '!/^https?:$/i.test(target.protocol)' in card_js
    assert "target.username || target.password" in card_js
    assert "target.origin === listing.origin" in card_js
    assert r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$" in card_js
    assert "officialDetailUrl(abs) && !urls.includes(abs)" in card_js
    assert "if (!officialDetailUrl(abs)) continue;" in card_js

    # The target host is deliberately not compared with allowedDomains. The
    # official listing card, not same-domain coincidence, is the provenance proof.
    helper = read_text("surface/local_events_runtime/listing_url_authority.py")
    assert "if (!sameDomain(target.href)) return false" not in helper
    assert "target hostname" not in helper.lower()


def test_listing_detail_discovery_still_rejects_unsafe_or_self_links() -> None:
    authority = read_text("surface/local_events_runtime/listing_url_authority.py")

    assert "if (!/^https?:$/i.test(target.protocol)) return false;" in authority
    assert "if (target.username || target.password) return false;" in authority
    assert "targetPath === listingPath" in authority
    assert "target.search === listing.search" in authority
    assert r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$" in authority


def test_review_detail_navigation_has_one_bounded_wait() -> None:
    implementation = read_text("surface/local_events_runtime/review_detail_authority.py")

    assert 'wait_until="domcontentloaded"' in implementation
    assert 'wait_until="networkidle"' not in implementation
    assert "listing_detail_url(listing_url, raw_url)" in implementation
    assert "_review._host_allowed(requested_url, source)" not in implementation
    assert "redirected outside the source allow-list" not in implementation


def test_gardens_blooming_resource_is_never_an_event_listing_or_detail() -> None:
    assert rejection_reason(GARDENS_RESOURCE) == "gardens_non_event_resource_path"
    assert listing_detail_url(GARDENS_LISTING, GARDENS_RESOURCE) == ""
    assert listing_detail_url(GARDENS_LISTING, GARDENS_EVENT) == GARDENS_EVENT

    assert "gardensbythebay.com.sg" in PREVIEW_LISTING_JS
    assert "learn-with-us\\/explore-resources" in PREVIEW_LISTING_JS

    formal_browser = read_text(
        "surface/local_events_runtime/listing_url_authority.py"
    )
    direct_preview = read_text(
        "surface/local_events_runtime/preview_direct_detail_collector_authority.py"
    )
    formal_selection = read_text(
        "surface/local_events_runtime/preview_event_selection_authority.py"
    )
    discovery = read_text(
        "surface/local_events_runtime/scoped_listing_collection.py"
    )
    manual = read_text("surface/local_events_runtime/manual_listing.py")

    assert "knownNonEventResource" in formal_browser
    assert "_provenance.listing_detail_url(" in direct_preview
    assert "listing_page_rejection_reason(listing.url, listing.link_text)" in direct_preview
    assert "listing_page_rejection_reason(listing.url, listing.link_text)" in formal_selection
    assert "listing_page_rejection_reason(url, link_text)" in discovery
    assert "listing_page_rejection_reason(url)" in manual
