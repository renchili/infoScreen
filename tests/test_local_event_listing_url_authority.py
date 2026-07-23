from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser  # noqa: E402
from local_events_runtime.listing_url_authority import apply as apply_listing_url_authority  # noqa: E402
from local_events_runtime.source_overrides import apply as apply_source_overrides  # noqa: E402


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
