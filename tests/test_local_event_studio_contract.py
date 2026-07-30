from __future__ import annotations

import pytest

from .conftest import read_text

pytestmark = pytest.mark.frontend


def test_studio_uses_one_scroll_owner_and_one_render_lifecycle() -> None:
    studio = read_text("surface/web/assets/js/local_event_studio.js")
    guard = read_text("surface/web/assets/js/local_event_review_scroll_guard.js")
    filters = read_text("surface/web/assets/js/local_event_review_filters.js")

    assert "setInterval(loadState, 3000)" not in studio
    assert "previousSetInterval" not in guard
    assert "Number(delay) === 3000" not in guard
    assert "MutationObserver" not in guard
    assert "MutationObserver" not in filters
    assert "window.scrollTo" not in filters
    assert 'document.addEventListener("infoscreen:review-rendered", restorePosition)' in guard
    assert 'document.addEventListener("infoscreen:review-rendered", refreshAfterRender)' in filters


def test_studio_preview_never_writes_list_page_decisions() -> None:
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")

    assert "/api/local-events/review/listing-decision" not in preview
    assert "setListingDecision" not in preview
    assert "withExclusiveConfirmedListings" not in preview
    assert "Confirm this list page before previewing it" in preview
