from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import browser, event_review_diagnostics  # noqa: E402
from local_events_runtime.detail_date_authority import apply as apply_detail_date_authority  # noqa: E402
from local_events_runtime.structural_link_authority import apply as apply_structural_link_authority  # noqa: E402


def test_calendar_of_events_detail_links_use_structural_authority() -> None:
    apply_detail_date_authority()
    apply_structural_link_authority()

    # The real CARD extractor must not require route-name enumeration.
    assert "officialDetailUrl(abs)" in browser.CARD_JS

    # Review diagnostics must use the same same-domain/non-listing/media rule.
    diagnostic_js = event_review_diagnostics.LISTING_DIAGNOSTIC_JS
    assert "targetPath === listingPath" in diagnostic_js
    assert "jpg|jpeg|png|gif|webp|svg|pdf" in diagnostic_js
    assert 'pathRole(anchor.getAttribute("href") || "") === "detail"' not in diagnostic_js


def test_production_and_review_bootstraps_load_structural_authority() -> None:
    job = read_text("surface/jobs/local_event_search.py")
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    assert "from local_events_runtime import listing_url_authority" in job
    assert "listing_url_authority.apply()" in job
    assert "apply_structural_link_authority()" in bootstrap
