from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag, urljoin

from . import artscience_detail as _artscience_detail
from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview
from . import review_detail_navigation_authority as _detail_navigation
from . import review_effective_fields_authority as _effective

_APPLIED = False
_ARTSCIENCE_SOURCE_ID = "artscience"


def _listing_card(raw: dict[str, Any]) -> dict[str, Any]:
    title = str(raw.get("title") or "").strip()
    return {
        "url": str(raw.get("detail_url") or "").strip(),
        "headings": [title] if title else [],
        "link_text": title,
        "text_lines": [title] if title else [],
        "text": title,
    }


def _url_key(base_url: str, raw_url: str) -> str:
    return urldefrag(urljoin(str(base_url or ""), str(raw_url or "").strip()))[0]


def _matching_rendered_anchor(listing_page: Any, raw: dict[str, Any]) -> Any:
    """Return the actual rendered link represented by one Preview card."""

    selector = str(raw.get("selector") or "").strip()
    detail_url = str(raw.get("detail_url") or "").strip()
    if not selector or not detail_url:
        raise ValueError("preview card is missing selector or detail URL")

    cards = listing_page.locator(selector)
    if cards.count() != 1:
        raise ValueError(
            f"rendered_preview_card_match_count_{cards.count()} for {selector}"
        )

    target_key = _url_key(str(listing_page.url), detail_url)
    anchors = cards.locator("a[href]")
    for index in range(anchors.count()):
        anchor = anchors.nth(index)
        href = str(anchor.get_attribute("href") or "").strip()
        if href and _url_key(str(listing_page.url), href) == target_key:
            return anchor
    raise ValueError("rendered_detail_link_not_found_in_preview_card")


def _mark_listing_page(
    listing_page: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
) -> None:
    """Restore card selectors after a same-tab detail visit and browser Back."""

    listing_page.evaluate(
        _preview.PREVIEW_LISTING_JS,
        {
            "allowedDomains": source.get("allowed_domains") or [],
            "listingUrl": listing.url,
            "sourceId": listing.source_id,
            "maxEvents": _preview.MAX_PREVIEW_EVENTS,
        },
    )


def _restore_listing_page(
    listing_page: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
) -> None:
    """Return the real browser tab to the rendered List Page for the next click."""

    expected = _url_key(listing.url, listing.url)
    try:
        listing_page.go_back(
            wait_until="domcontentloaded",
            timeout=_preview.PREVIEW_PAGE_TIMEOUT_MS,
        )
    except Exception:
        pass

    if _url_key(str(listing_page.url), str(listing_page.url)) != expected:
        response = listing_page.goto(
            listing.url,
            wait_until="domcontentloaded",
            timeout=_preview.PREVIEW_PAGE_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            raise ValueError(f"listing_restore_http_status_{response.status}")

    listing_page.wait_for_timeout(_preview.PREVIEW_SETTLE_MS)
    _mark_listing_page(listing_page, source, listing)


def _read_clicked_artscience_detail(
    context: Any,
    listing_page: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
    raw: dict[str, Any],
) -> dict[str, str]:
    """Click the rendered List Page link and parse the page Chrome actually opens."""

    requested_url = str(raw.get("detail_url") or "").strip()
    anchor = _matching_rendered_anchor(listing_page, raw)
    anchor.scroll_into_view_if_needed()
    target = str(anchor.get_attribute("target") or "").strip().lower()

    if target == "_blank":
        with context.expect_page(
            timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS
        ) as opened:
            anchor.click(timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS)
        detail_page = opened.value
        try:
            detail_page.bring_to_front()
            try:
                detail_page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=_detail_navigation.DETAIL_CONTENT_WAIT_MS,
                )
            except Exception:
                pass
            return _artscience_detail.read_loaded_detail_candidate(
                detail_page,
                source,
                listing.url,
                requested_url,
            )
        finally:
            if not detail_page.is_closed():
                detail_page.close()

    try:
        with listing_page.expect_navigation(
            wait_until="commit",
            timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS,
        ) as navigation:
            anchor.click(timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS)
        response = navigation.value
        if response is not None and response.status >= 400:
            raise ValueError(f"detail_http_status_{response.status}")
        listing_page.bring_to_front()
        return _artscience_detail.read_loaded_detail_candidate(
            listing_page,
            source,
            listing.url,
            requested_url,
        )
    finally:
        _restore_listing_page(listing_page, source, listing)


def _collect_detail(
    context: Any,
    listing_page: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
    raw: dict[str, Any],
) -> dict[str, str]:
    if listing.source_id == _ARTSCIENCE_SOURCE_ID:
        return _read_clicked_artscience_detail(
            context,
            listing_page,
            source,
            listing,
            raw,
        )

    return _effective.detail_candidate(
        context,
        source,
        listing.url,
        str(raw.get("detail_url") or "").strip(),
        _listing_card(raw),
    )


def _failed_detail(
    raw: dict[str, Any],
    default_venue: str,
    error: str,
) -> dict[str, str]:
    return {
        "detail_url": str(raw.get("detail_url") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
        "when": str(raw.get("when") or "").strip(),
        "where": str(raw.get("where") or default_venue).strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "detail_status": "failed",
        "detail_error": error[:500],
        "detail_page_title": "",
    }


def collect_preview(store: _review.EventReviewStore) -> _review.ReviewState:
    """Collect one List Page and click its detail links in one real browser lifecycle."""

    state = store.load()
    confirmed = [item for item in state.listing_pages if item.decision == "confirmed"]
    if len(confirmed) != 1:
        raise ValueError("preview requires exactly one selected listing page")

    listing = confirmed[0]
    source = store.source(listing.source_id)
    if not _preview._host_allowed(listing.url, source):
        raise ValueError("listing page is outside the source allow-list")

    _effective.apply()
    started = _review.utc_now()
    rows: list[dict[str, Any]] = []
    observed: dict[str, Any] = {}
    final_url = listing.url
    http_status: int | None = None
    detail_errors: list[dict[str, str]] = []
    detail_attempts = 0
    detail_clicks = 0
    default_venue = str(source.get("default_venue") or source.get("name") or "")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                device_scale_factor=1,
            )
            try:
                listing_page = context.new_page()
                try:
                    response = listing_page.goto(
                        listing.url,
                        wait_until="domcontentloaded",
                        timeout=_preview.PREVIEW_PAGE_TIMEOUT_MS,
                    )
                    if response is not None:
                        http_status = int(response.status)
                        if http_status >= 400:
                            raise ValueError(f"listing_http_status_{http_status}")
                    listing_page.wait_for_timeout(_preview.PREVIEW_SETTLE_MS)
                    final_url = str(listing_page.url)
                    if not _preview._host_allowed(final_url, source):
                        raise ValueError(
                            "listing page redirected outside the source allow-list"
                        )
                    payload = listing_page.evaluate(
                        _preview.PREVIEW_LISTING_JS,
                        {
                            "allowedDomains": source.get("allowed_domains") or [],
                            "listingUrl": listing.url,
                            "sourceId": listing.source_id,
                            "maxEvents": _preview.MAX_PREVIEW_EVENTS,
                        },
                    ) or {}
                    if isinstance(payload, dict):
                        rows = [
                            item
                            for item in payload.get("rows") or []
                            if isinstance(item, dict)
                        ]
                        observed = payload.get("observed") or {}
                    elif isinstance(payload, list):
                        rows = [item for item in payload if isinstance(item, dict)]

                    for raw in rows:
                        detail_url = str(raw.get("detail_url") or "").strip()
                        title = str(raw.get("title") or "").strip()
                        if not title or not _preview._host_allowed(detail_url, source):
                            continue
                        detail_attempts += 1
                        try:
                            detail = _collect_detail(
                                context,
                                listing_page,
                                source,
                                listing,
                                raw,
                            )
                            if listing.source_id == _ARTSCIENCE_SOURCE_ID:
                                detail_clicks += 1
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"[:500]
                            detail = _failed_detail(raw, default_venue, error)
                        raw["_detail"] = detail
                        detail_error = str(detail.get("detail_error") or "").strip()
                        if detail_error:
                            detail_errors.append(
                                {
                                    "detail_url": detail_url,
                                    "error": detail_error[:500],
                                }
                            )
                finally:
                    if not listing_page.is_closed():
                        listing_page.close()
            finally:
                context.close()
        finally:
            browser.close()

    candidates: list[_review.EventCandidate] = []
    listing_detail_urls: dict[str, str] = {}
    for index, raw in enumerate(rows):
        listing_detail_url = str(raw.get("detail_url") or "").strip()
        listing_title = str(raw.get("title") or "").strip()
        if not listing_title or not _preview._host_allowed(listing_detail_url, source):
            continue

        detail = raw.get("_detail")
        if not isinstance(detail, dict):
            detail = _failed_detail(
                raw,
                default_venue,
                "detail_collection_not_attempted",
            )
        candidate_id = _review.stable_id(
            listing.source_id,
            listing.url,
            listing_detail_url,
        )
        listing_detail_urls[candidate_id] = listing_detail_url
        document_position = raw.get("document_position") or {}
        viewport_position = raw.get("viewport_position") or {}

        candidates.append(
            _review.EventCandidate(
                candidate_id=candidate_id,
                source_id=listing.source_id,
                source_name=listing.source_name,
                listing_url=listing.url,
                detail_url=str(
                    detail.get("detail_url") or listing_detail_url
                ).strip(),
                title=str(detail.get("title") or listing_title).strip()[:300],
                when=str(detail.get("when") or raw.get("when") or "").strip()[:180],
                where=str(
                    detail.get("where") or raw.get("where") or default_venue
                ).strip()[:300],
                summary=str(
                    detail.get("summary") or raw.get("summary") or ""
                ).strip()[:500],
                detail_status=str(detail.get("detail_status") or "failed"),
                detail_error=str(detail.get("detail_error") or "").strip()[:500],
                detail_page_title=str(
                    detail.get("detail_page_title") or ""
                ).strip()[:300],
                evidence=_review.EventEvidence(
                    selector=str(raw.get("selector") or "preview-card"),
                    selector_index=index,
                    selector_match_count=1,
                    document_position={
                        key: int(document_position.get(key) or 0)
                        for key in ("x", "y", "width", "height")
                    },
                    viewport_position={
                        key: int(viewport_position.get(key) or 0)
                        for key in ("x", "y", "width", "height")
                    },
                    page_index=0,
                    page_url=final_url,
                    text=str(raw.get("text") or "")[:3000],
                ),
                collected_at=started,
            )
        )

    diagnostic = _preview._diagnostic(
        listing,
        observed,
        final_url=final_url,
        http_status=http_status,
        candidate_count=len(candidates),
    )
    diagnostic.detail_collected = sum(
        candidate.detail_status == "collected" for candidate in candidates
    )
    diagnostic.detail_incomplete = sum(
        candidate.detail_status == "incomplete" for candidate in candidates
    )
    diagnostic.detail_failed = sum(
        candidate.detail_status == "failed" for candidate in candidates
    )
    diagnostic = _diagnostics._finish(diagnostic)

    return store.replace_events(
        candidates,
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "confirmed_listing_count": 1,
            "candidate_count": len(candidates),
            "preview_mode": "direct_single_page_main_content",
            "preview_card_policy": "rendered_title_and_official_detail_link",
            "preview_diagnostics_mode": "same_pass_main_content",
            "formal_collector_bypassed": True,
            "selector_audit_skipped": True,
            "listing_diagnostics_skipped": False,
            "preview_detail_mode": "official_detail_pages",
            "preview_detail_enrichment_entrypoint": (
                "preview_collector._collect_preview"
            ),
            "preview_detail_navigation": (
                "rendered_listing_link_click"
                if listing.source_id == _ARTSCIENCE_SOURCE_ID
                else "detail_owner_navigation"
            ),
            "preview_detail_clicked_count": detail_clicks,
            "preview_detail_transport": "same_browser_context",
            "preview_browser_process_count": 1,
            "preview_browser_reuse": "listing_and_details",
            "preview_detail_context_count": 1,
            "preview_candidate_listing_detail_urls": listing_detail_urls,
            "detail_page_request_count": detail_attempts,
            "detail_page_requests_skipped": 0,
            "detail_page_error_count": len(detail_errors),
            "detail_page_errors": detail_errors,
            "final_url": final_url,
            "http_status": http_status,
            "listing_diagnostics": [diagnostic.model_dump(mode="json")],
            "errors": [],
        },
    )


def apply() -> None:
    """Replace the exact Preview entrypoint; do not wrap another browser lifecycle."""

    global _APPLIED
    _preview._collect_preview = collect_preview
    _APPLIED = True


__all__ = [
    "apply",
    "collect_preview",
    "_matching_rendered_anchor",
    "_read_clicked_artscience_detail",
]
