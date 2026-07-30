from __future__ import annotations

from typing import Any

from . import artscience_detail as _artscience_detail
from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview
from . import review_effective_fields_authority as _effective

_APPLIED = False
_BASE_PREVIEW_COLLECT = None
_ARTSCIENCE_SOURCE_ID = "artscience"


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _needs_detail(candidate: _review.EventCandidate) -> bool:
    """Return true only for a candidate still downgraded to listing evidence."""

    return str(candidate.detail_error or "").startswith(
        "preview_listing_evidence_only"
    )


def _listing_card(candidate: _review.EventCandidate) -> dict[str, Any]:
    """Force the final detail owner to read the official detail document.

    Supplying listing dates, venue, summary, or the full evidence text may make the
    normal detail owner treat a list card as complete. Preview exists so the operator
    can review the actual official detail facts before selecting REAL EVENT / NOT EVENT,
    therefore only identity and title evidence are passed here.
    """

    title = str(candidate.title or "").strip()
    return {
        "url": candidate.detail_url,
        "headings": [title] if title else [],
        "link_text": title,
        "text_lines": [title] if title else [],
        "text": title,
    }


def _apply_detail(candidate: _review.EventCandidate, detail: dict[str, str]) -> None:
    """Apply final fields while retaining the original list-card identity.

    The official detail document may redirect to a public canonical URL. Preview
    selection must still be able to match the original rendered list-card link before
    formal collection opens that detail document, so candidate_id remains the identity
    created from the listing href while detail_url becomes the final public URL.
    """

    final_url = str(detail.get("detail_url") or candidate.detail_url).strip()
    candidate.detail_url = final_url
    candidate.title = str(detail.get("title") or candidate.title).strip()[:300]
    candidate.when = str(detail.get("when") or candidate.when).strip()[:180]
    candidate.where = str(detail.get("where") or candidate.where).strip()[:300]
    candidate.summary = str(detail.get("summary") or candidate.summary).strip()[:500]
    candidate.detail_status = str(detail.get("detail_status") or "failed")
    candidate.detail_error = str(detail.get("detail_error") or "").strip()[:500]
    candidate.detail_page_title = str(
        detail.get("detail_page_title") or ""
    ).strip()[:300]


def _refresh_diagnostics(state: _review.ReviewState) -> None:
    rows = state.event_collection.get("listing_diagnostics")
    if not isinstance(rows, list):
        return

    by_listing: dict[str, list[_review.EventCandidate]] = {}
    for event in state.events:
        by_listing.setdefault(event.listing_url, []).append(event)

    updated = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            diagnostic = _diagnostics.ListingRecognitionDiagnostic.model_validate(raw)
        except Exception:
            updated.append(raw)
            continue
        events = by_listing.get(diagnostic.listing_url, [])
        diagnostic.detail_collected = sum(
            event.detail_status == "collected" for event in events
        )
        diagnostic.detail_incomplete = sum(
            event.detail_status == "incomplete" for event in events
        )
        diagnostic.detail_failed = sum(
            event.detail_status == "failed" for event in events
        )
        updated.append(_diagnostics._finish(diagnostic).model_dump(mode="json"))
    state.event_collection["listing_diagnostics"] = updated


def _new_context(browser: Any) -> Any:
    return browser.new_context(
        viewport={"width": 1440, "height": 1000},
        device_scale_factor=1,
    )


def _collect_artscience_detail(
    playwright: Any,
    source: dict[str, Any],
    candidate: _review.EventCandidate,
) -> dict[str, str]:
    """Use one fresh browser process for one MBS detail document.

    The deployed MBS session can load the first detail page and then return
    ERR_HTTP2_PROTOCOL_ERROR for later pages when the same Chromium network process is
    reused. A fresh headed Chromium process per detail page prevents those documents
    from sharing the failing HTTP/2 connection while preserving the verified browser
    transport and rendered-DOM authority.
    """

    browser = _browser.launch_chromium(playwright)
    try:
        context = _new_context(browser)
        try:
            page = context.new_page()
            try:
                return _artscience_detail.collect_detail_candidate(
                    page,
                    source,
                    candidate.listing_url,
                    candidate.detail_url,
                )
            finally:
                if not page.is_closed():
                    page.close()
        finally:
            context.close()
    finally:
        browser.close()


def enrich_preview_state(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
) -> _review.ReviewState:
    """Replace every remaining listing-only Preview row with detail-page fields."""

    if not _preview_store(store) or not state.events:
        return state

    pending = [candidate for candidate in state.events if _needs_detail(candidate)]
    if not pending:
        return state

    existing_listing_urls = state.event_collection.get(
        "preview_candidate_listing_detail_urls"
    )
    listing_detail_urls = (
        dict(existing_listing_urls)
        if isinstance(existing_listing_urls, dict)
        else {}
    )
    for candidate in pending:
        listing_detail_urls.setdefault(
            candidate.candidate_id,
            str(candidate.detail_url or "").strip(),
        )

    _effective.apply()
    sources = {
        str(source.get("id") or ""): source for source in store.inventory()
    }
    errors: list[dict[str, str]] = []
    attempted = 0
    isolated_browser_count = 0
    used_artscience_owner = False
    used_effective_owner = False

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        shared_browser = None
        shared_context = None
        try:
            for candidate in pending:
                source = sources.get(candidate.source_id)
                if source is None:
                    candidate.detail_status = "failed"
                    candidate.detail_error = "source_not_found"
                    errors.append(
                        {
                            "detail_url": candidate.detail_url,
                            "error": "source_not_found",
                        }
                    )
                    continue

                attempted += 1
                try:
                    if candidate.source_id == _ARTSCIENCE_SOURCE_ID:
                        used_artscience_owner = True
                        isolated_browser_count += 1
                        detail = _collect_artscience_detail(
                            playwright,
                            source,
                            candidate,
                        )
                    else:
                        used_effective_owner = True
                        if shared_browser is None:
                            shared_browser = _browser.launch_chromium(playwright)
                            shared_context = _new_context(shared_browser)
                        detail = _effective.detail_candidate(
                            shared_context,
                            source,
                            candidate.listing_url,
                            candidate.detail_url,
                            _listing_card(candidate),
                        )
                    _apply_detail(candidate, detail)
                except Exception as exc:
                    candidate.detail_status = "failed"
                    candidate.detail_error = (
                        f"{type(exc).__name__}: {exc}"
                    )[:500]
                    errors.append(
                        {
                            "detail_url": candidate.detail_url,
                            "error": candidate.detail_error,
                        }
                    )
        finally:
            if shared_context is not None:
                shared_context.close()
            if shared_browser is not None:
                shared_browser.close()

    state.events = sorted(
        state.events,
        key=lambda event: (
            event.source_name.casefold(),
            event.listing_url,
            event.evidence.document_position.get("y", 0),
        ),
    )
    prior_attempts = int(state.event_collection.get("detail_page_request_count") or 0)
    prior_errors = state.event_collection.get("detail_page_errors")
    combined_errors = [
        *(prior_errors if isinstance(prior_errors, list) else []),
        *errors,
    ]
    if used_artscience_owner and used_effective_owner:
        owner_module = "mixed"
        owner_name = "artscience_detail + review_effective_fields"
    elif used_artscience_owner:
        owner_module = _artscience_detail.collect_detail_candidate.__module__
        owner_name = _artscience_detail.collect_detail_candidate.__qualname__
    else:
        owner_module = _effective.detail_candidate.__module__
        owner_name = _effective.detail_candidate.__qualname__

    state.event_collection = {
        **state.event_collection,
        "preview_detail_mode": "official_detail_pages",
        "preview_detail_enrichment_entrypoint": "preview_collector._collect_preview",
        "preview_candidate_listing_detail_urls": listing_detail_urls,
        "preview_detail_transport": (
            "fresh_browser_per_artscience_candidate"
            if isolated_browser_count
            else "shared_browser_context"
        ),
        "preview_detail_isolated_browser_count": isolated_browser_count,
        "preview_detail_owner_module": owner_module,
        "preview_detail_owner_name": owner_name,
        "detail_page_request_count": prior_attempts + attempted,
        "detail_page_requests_skipped": 0,
        "detail_page_error_count": len(combined_errors),
        "detail_page_errors": combined_errors,
    }
    _refresh_diagnostics(state)
    return store.save(state)


def collect_preview_with_details(
    store: _review.EventReviewStore,
) -> _review.ReviewState:
    """Run the real Preview collector, then enrich before it can return upstream."""

    state = _BASE_PREVIEW_COLLECT(store)
    return enrich_preview_state(store, state)


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    """Compatibility entrypoint retained for final-handoff guards and tests."""

    if _preview_store(store):
        return collect_preview_with_details(store)
    return _preview._BASE_COLLECT(store)


def apply() -> None:
    """Patch the exact function that creates preview_listing_evidence_only rows.

    Wrapping event_review_diagnostics is order-sensitive because several authorities
    replace that exported function. preview_collector_authority.collect_event_candidates
    resolves its module-global _collect_preview at call time, so replacing that function
    is the stable point shared by every HTTP and test entrypoint.
    """

    global _APPLIED, _BASE_PREVIEW_COLLECT
    if not _APPLIED:
        _BASE_PREVIEW_COLLECT = _preview._collect_preview
        _APPLIED = True
    _preview._collect_preview = collect_preview_with_details


__all__ = [
    "apply",
    "collect_event_candidates",
    "collect_preview_with_details",
    "enrich_preview_state",
    "_needs_detail",
]
