from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser  # noqa: E402
from local_events_runtime.listing_url_authority import apply as apply_listing_url_authority  # noqa: E402
from local_events_runtime.source_overrides import apply as apply_source_overrides  # noqa: E402


def test_listing_detail_discovery_accepts_known_routes_and_listing_descendants() -> None:
    apply_source_overrides()
    apply_listing_url_authority()

    card_js = browser.CARD_JS
    assert "function officialDetailUrl(raw)" in card_js
    assert "targetPath === listingPath" in card_js
    assert 'if (role === "listing") return false;' in card_js
    assert 'if (role === "detail") return true;' in card_js
    assert r'listingPath.replace(/\.html?$/i, "")' in card_js
    assert 'targetPath.startsWith(listingStem + "/")' in card_js
    assert "officialDetailUrl(abs) && !urls.includes(abs)" in card_js
    assert "if (!officialDetailUrl(abs)) continue;" in card_js

    # The old call sites must not bypass officialDetailUrl and run their own
    # inconsistent route checks.
    assert 'pathRole(abs) === "detail" && !urls.includes(abs)' not in card_js
    assert '!sameDomain(abs) || pathRole(abs) !== "detail"' not in card_js


def test_structural_fallback_is_not_every_same_domain_link() -> None:
    apply_source_overrides()
    apply_listing_url_authority()

    card_js = browser.CARD_JS
    assert "if (!targetPath || targetPath === listingPath) return false;" in card_js
    assert r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$" in card_js
    assert 'return Boolean(listingStem && targetPath.startsWith(listingStem + "/"));' in card_js


def test_gardens_calendar_file_descendant_contract_is_present() -> None:
    authority = read_text("surface/local_events_runtime/listing_url_authority.py")
    diagnostics = read_text("surface/local_events_runtime/structural_link_authority.py")

    assert "/calendar-of-events.html" in authority
    assert "/calendar-of-events/orchid-extravaganza-2026.html" in authority
    assert 'targetPath.startsWith(listingStem + "/")' in authority
    assert 'targetPath.startsWith(listingStem + "/")' in diagnostics


def test_review_detail_navigation_has_one_bounded_wait() -> None:
    implementation = read_text("surface/local_events_runtime/review_detail_authority.py")

    assert 'wait_until="domcontentloaded"' in implementation
    assert 'wait_until="networkidle"' not in implementation
    assert 'LOCAL_EVENT_REVIEW_DETAIL_TIMEOUT_MS' in implementation
    assert '"8000"' in implementation
