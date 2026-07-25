from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import listing_pagination_authority as pagination  # noqa: E402


def test_numeric_controls_require_a_real_pagination_container() -> None:
    script = pagination.VALIDATED_NEXT_PAGE_JS

    assert "const paginationContainer = element => element.closest(" in script
    assert "!paginationContainer(element)" in script
    assert "Number(text) === pageIndex + 2" in script
    assert "hasPaginationEvidence(element)" in script


def test_page_advance_requires_changed_listing_inventory() -> None:
    script = pagination.VALIDATED_NEXT_PAGE_JS

    assert "const inventory = () =>" in script
    assert "before.detailUrls.join" in script
    assert "before.pageUrl !== after.pageUrl" in script
    assert 'reason: "next_control_did_not_change_listing_inventory"' in script
    assert "clicked: false" in script
    assert "clicked: true" in script


def test_review_binds_validated_pagination_before_runtime_handoff() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    dynamic = bootstrap.index("apply_dynamic_listing_authority()")
    pagination_apply = bootstrap.index("apply_listing_pagination_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")

    assert dynamic < pagination_apply < binding
    assert '"CLICK_NEXT_PAGE_JS"' in bootstrap
