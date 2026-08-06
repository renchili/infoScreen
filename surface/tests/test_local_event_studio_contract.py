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


def test_isolated_preview_renders_temporary_candidates_before_operator_selection() -> None:
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")
    html = read_text("surface/web/local-events/studio/index.html")

    assert 'function renderPreviewCandidatePanel(payload, url)' in preview
    assert 'document.getElementById("event-candidates")' in preview
    assert 'article.dataset.preview = "true"' in preview
    assert "preview_candidate_listing_detail_urls" in preview
    assert "detail_field_authority_version" in preview
    assert "article.dataset.listingDetailUrl" in preview
    assert 'renderPreviewCandidatePanel(panelPayload(stored), url);' in preview
    assert "candidate_rows: candidates" in preview
    assert 'await reloadState();' not in preview[preview.index("async function collectPreview(card, button)"):preview.index("async function collectForGlobalInstitution(button)")]
    assert "/api/local-events/review/event-decision" not in preview
    assert "RELATED ACTIVITY" not in preview
    assert "Review every candidate as REAL EVENT or NOT EVENT" in preview
    assert "selections are not committed until the List Page review is saved" in preview
    assert "cannot be reviewed until the list page is confirmed" not in preview
    assert "Event review actions are disabled" not in preview
    assert 'id="event-candidates-title"' in html
    assert 'id="event-candidates-hint"' in html


def test_preview_survives_tab_resume_from_versioned_structured_state() -> None:
    persistence = read_text(
        "surface/web/assets/js/local_event_review_preview_persistence.js"
    )
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")
    workflow = read_text(
        "surface/web/assets/js/local_event_review_preview_workflow.js"
    )
    guard = read_text("surface/web/assets/js/local_event_review_scroll_guard.js")
    diagnostics = read_text(
        "surface/web/assets/js/local_event_review_diagnostics.js"
    )
    html = read_text("surface/web/local-events/studio/index.html")

    assert 'const STORAGE_KEY = "infoscreen.review.active-preview-panel"' in persistence
    assert "SNAPSHOT_VERSION = 7" in persistence
    assert 'sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))' in persistence
    assert "snapshot.html" not in persistence
    assert "container.innerHTML" not in persistence
    assert "rebuilds the panel from its versioned structured candidate snapshot" in persistence
    assert 'document.addEventListener("infoscreen:review-preview"' in persistence
    assert 'document.addEventListener("infoscreen:review-rendered"' in persistence
    assert 'document.addEventListener("infoscreen:review-state"' in persistence
    assert "if (event.detail?.restored) return;" in persistence

    assert 'const PREVIEW_AUTHORITY_VERSION = "detail-provenance-v2"' in preview
    assert "const PREVIEW_PANEL_VERSION = 1" in preview
    assert "panel_version: PREVIEW_PANEL_VERSION" in preview
    assert "candidate_rows: candidates" in preview
    assert "listing_detail_urls: normalizedListingDetailUrls" in preview
    assert "function restoreActivePreview()" in preview
    assert "delete entry.candidate_rows;" in preview
    assert "requireCandidates: true" in preview
    assert "renderPreviewCandidatePanel(panelPayload(stored), url);" in preview
    assert "publishPreview(url, stored.diagnostic, { restored: true });" in preview
    restore = preview[
        preview.index("function restoreActivePreview()"):
        preview.index("function enhanceListingCards()")
    ]
    assert restore.index("renderPreviewCandidatePanel") < restore.index("publishPreview")
    assert "restoreActivePreview();" in preview
    assert 'document.addEventListener("infoscreen:review-preview"' in workflow
    assert "const decisions = decisionsFor(expected);" in workflow
    assert "installCandidateActions" in workflow
    assert "value.authority_version === PREVIEW_AUTHORITY_VERSION" in preview
    assert "snapshot.html" not in workflow
    assert "container.innerHTML" not in workflow
    assert "persistPanelSnapshot" not in workflow
    assert 'document.addEventListener("visibilitychange"' in guard
    assert "await loadState();" in guard
    assert "value.authority_version === PREVIEW_AUTHORITY_VERSION" in diagnostics
    assert (
        '<script src="/assets/js/local_event_review_preview_persistence.js" defer></script>'
        in html
    )
    assert html.index("local_event_review_previews.js") < html.index(
        "local_event_review_preview_persistence.js"
    )
    assert html.index("local_event_review_preview_persistence.js") < html.index(
        "local_event_review_preview_workflow.js"
    )


def test_preview_requires_every_candidate_to_be_real_event_or_not_event() -> None:
    preview = read_text("surface/web/assets/js/local_event_review_previews.js")
    workflow = read_text(
        "surface/web/assets/js/local_event_review_preview_workflow.js"
    )
    html = read_text("surface/web/local-events/studio/index.html")

    assert 'const DECISION_KEY = "infoscreen.review.preview-event-decisions"' in workflow
    assert 'actionButton("REAL EVENT"' in workflow
    assert 'actionButton("NOT EVENT"' in workflow
    assert 'actionButton("RESET"' in workflow
    assert "if (pendingCount) return;" in workflow
    assert "Preview candidates · select real events" in workflow
    assert "REVIEW REQUIRED · Select REAL EVENT or NOT EVENT" in workflow
    assert "CONFIRM ${realCount} REAL EVENT" in workflow
    assert "COLLECT ${realCount} SELECTED REAL EVENT" in workflow
    assert 'const PROTOCOL_PREFIX = "preview-review-v1:"' in workflow
    assert "function listingDetailUrl(card)" in workflow
    assert "listing_detail_url: listingDetailUrl(card)" in workflow
    assert "listing_detail_url: row.listing_detail_url" in workflow
    assert "function completeCandidateRow(row)" in workflow
    assert "rows.some((row) => !completeCandidateRow(row))" in workflow
    assert "PREVIEW DATA INVALID" in workflow
    assert 'const raw = text(value);' in preview
    assert 'if (!raw) return "";' in preview
    assert 'const raw = text(value);' in workflow
    assert 'if (!raw) return "";' in workflow
    assert 'request("/api/local-events/review/listing-decision"' in workflow
    assert 'request("/api/local-events/review/collect-events"' in workflow
    assert 'document.addEventListener("infoscreen:review-preview"' in workflow
    assert 'document.addEventListener("infoscreen:review-rendered"' in workflow
    assert (
        '<script src="/assets/js/local_event_review_preview_workflow.js" defer></script>'
        in html
    )
    assert html.index("local_event_review_preview_persistence.js") < html.index(
        "local_event_review_preview_workflow.js"
    )
