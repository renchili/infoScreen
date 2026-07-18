from __future__ import annotations

import sys

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser  # noqa: E402
from local_events_runtime.listing_url_authority import apply as apply_listing_url_authority  # noqa: E402
from local_events_runtime.source_overrides import apply as apply_source_overrides  # noqa: E402


def test_listing_detail_discovery_is_structural_not_route_enumeration() -> None:
    apply_source_overrides()
    apply_listing_url_authority()

    card_js = browser.CARD_JS
    assert "function officialDetailUrl(raw)" in card_js
    assert "targetPath === listingPath" in card_js
    assert "officialDetailUrl(abs) && !urls.includes(abs)" in card_js
    assert "if (!officialDetailUrl(abs)) continue;" in card_js

    # Route words may remain for pagination/debug roles, but must not decide
    # whether a link from an admitted official listing is a detail candidate.
    assert 'pathRole(abs) === "detail" && !urls.includes(abs)' not in card_js
    assert '!sameDomain(abs) || pathRole(abs) !== "detail"' not in card_js


def test_structural_rule_keeps_media_and_listing_pages_out() -> None:
    apply_source_overrides()
    apply_listing_url_authority()

    card_js = browser.CARD_JS
    assert "if (!targetPath || targetPath === listingPath) return false;" in card_js
    assert r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$" in card_js
