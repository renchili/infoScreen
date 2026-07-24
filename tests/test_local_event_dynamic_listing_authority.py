from __future__ import annotations

import json

from .conftest import SURFACE, read_text


def test_dynamic_listing_expansion_never_clicks_generic_detail_links() -> None:
    authority = read_text(
        "surface/local_events_runtime/dynamic_listing_authority.py"
    )

    assert "const safeAnchor = anchor =>" in authority
    assert "target.origin === current.origin && target.pathname === current.pathname" in authority
    assert "if (enclosingAnchor && !safeAnchor(enclosingAnchor)) return false" in authority
    assert "navigationDetected: true" in authority
    assert "view more|" not in authority.lower()
    assert "see more|" not in authority.lower()
    assert '"button, [role=\'button\']' in authority
    assert '"button, a[href]' not in authority


def test_dynamic_listing_authority_is_applied_before_card_discovery() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    dynamic = bootstrap.index("apply_dynamic_listing_authority()")
    structural = bootstrap.index("apply_structural_link_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")
    diagnostics = bootstrap.index("apply_event_review_diagnostics()")

    assert dynamic < structural < binding < diagnostics


def test_studio_review_receives_final_browser_scripts_not_import_snapshots() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    assert "def _bind_final_browser_runtime_to_review()" in bootstrap
    for name in (
        '"CARD_JS"',
        '"PREPARE_PAGE_JS"',
        '"DETAIL_CARD_JS"',
        '"CLICK_NEXT_PAGE_JS"',
        '"launch_chromium"',
    ):
        assert name in bootstrap
    assert "setattr(review, name, getattr(_browser, name))" in bootstrap


def test_reported_source_configuration_preserves_full_official_coverage() -> None:
    payload = json.loads(
        (SURFACE / "conf" / "event_sources.json").read_text(encoding="utf-8")
    )
    acm = next(source for source in payload["sources"] if source["id"] == "acm")
    sentosa = next(source for source in payload["sources"] if source["id"] == "sentosa")
    rws = next(source for source in payload["sources"] if source["id"] == "rws")
    kallang = next(source for source in payload["sources"] if source["id"] == "thekallang")

    assert "https://www.acm.nhb.gov.sg/whats-on/overview" in acm["listing_urls"]
    assert "a.a-listing-content__anchor-card[href]" in acm["card_selectors"]
    assert sentosa["load_more_rounds"] >= 80
    assert "a[href*='/en/things-to-do/events/']" in sentosa["card_selectors"]
    assert "singaporeoceanarium.com" in rws["allowed_domains"]
    assert "a[href*='/en/visit/events/']" in rws["card_selectors"]
    assert kallang["listing_urls"] == [
        "https://www.thekallang.com.sg/en/things-to-do/events.html"
    ]
