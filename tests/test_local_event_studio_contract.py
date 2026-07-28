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


def test_studio_preview_never_writes_list_page_decisions_and_keeps_its_diagnostic() -> None:
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")
    diagnostics = read_text("surface/web/assets/js/local_event_review_diagnostics.js")

    assert "/api/local-events/review/listing-decision" not in preview
    assert "setListingDecision" not in preview
    assert "withExclusiveConfirmedListings" not in preview
    assert "Confirm this list page before previewing it" not in preview
    assert 'diagnostic: diagnostic && typeof diagnostic === "object"' in preview
    assert 'new CustomEvent("infoscreen:review-preview"' in preview
    assert 'const PREVIEW_STORAGE_KEY = "infoscreen.review.event-previews"' in diagnostics
    assert "stored?.diagnostic" in diagnostics
    assert "preview_diagnostic_missing" in diagnostics
    assert 'document.addEventListener("infoscreen:review-preview"' in diagnostics


def test_isolated_preview_renders_temporary_candidates_without_review_actions() -> None:
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")
    html = read_text("surface/web/local-events/studio/index.html")

    assert 'function renderPreviewCandidatePanel(payload, url)' in preview
    assert 'document.getElementById("event-candidates")' in preview
    assert 'article.dataset.preview = "true"' in preview
    assert 'TEMPORARY PREVIEW · NOT SAVED · Event review actions are disabled.' in preview
    assert 'renderPreviewCandidatePanel(payload, url);' in preview
    assert 'await reloadState();' not in preview[preview.index("async function collectPreview(card, button)"):preview.index("async function collectForGlobalInstitution(button)")]
    assert "/api/local-events/review/event-decision" not in preview
    assert "RELATED ACTIVITY" not in preview
    assert 'id="event-candidates-title"' in html
    assert 'id="event-candidates-hint"' in html
