from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics

_APPLIED = False
_BASE_COLLECT = None


def _preview_store(store: _review.EventReviewStore) -> bool:
    return store.root.name.startswith("infoscreen-event-preview-")


def _listing_card(candidate: _review.EventCandidate) -> dict[str, Any]:
    lines = [
        value
        for value in (
            candidate.title,
            candidate.when,
            candidate.where,
            candidate.summary,
            candidate.evidence.text,
        )
        if str(value or "").strip()
    ]
    return {
        "url": candidate.detail_url,
        "headings": [candidate.title] if candidate.title else [],
        "link_text": candidate.title,
        "text_lines": lines,
        "text": "\n".join(lines),
    }


def _apply_detail(candidate: _review.EventCandidate, detail: dict[str, str]) -> None:
    final_url = str(detail.get("detail_url") or candidate.detail_url).strip()
    candidate.detail_url = final_url
    candidate.candidate_id = _review.stable_id(
        candidate.source_id,
        candidate.listing_url,
        final_url,
    )
    candidate.title = str(detail.get("title") or candidate.title).strip()[:300]
    candidate.when = str(detail.get("when") or candidate.when).strip()[:180]
    candidate.where = str(detail.get("where") or candidate.where).strip()[:300]
    candidate.summary = str(detail.get("summary") or candidate.summary).strip()[:500]
    candidate.detail_status = str(detail.get("detail_status") or "failed")
    candidate.detail_error = str(detail.get("detail_error") or "").strip()[:500]
    candidate.detail_page_title = str(detail.get("detail_page_title") or "").strip()[:300]


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


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    state = _BASE_COLLECT(store)
    if not _preview_store(store) or not state.events:
        return state

    sources = {
        str(source.get("id") or ""): source for source in store.inventory()
    }
    errors: list[dict[str, str]] = []
    attempted = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
            )
            try:
                for candidate in state.events:
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
                        detail = _review._detail_candidate(
                            context,
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
                context.close()
        finally:
            browser.close()

    state.events = sorted(
        state.events,
        key=lambda event: (
            event.source_name.casefold(),
            event.listing_url,
            event.evidence.document_position.get("y", 0),
        ),
    )
    state.event_collection = {
        **state.event_collection,
        "preview_detail_mode": "official_detail_pages",
        "detail_page_request_count": attempted,
        "detail_page_requests_skipped": 0,
        "detail_page_error_count": len(errors),
        "detail_page_errors": errors,
    }
    _refresh_diagnostics(state)
    return store.save(state)


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _diagnostics.collect_event_candidates = collect_event_candidates
        return

    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = ["apply", "collect_event_candidates"]
