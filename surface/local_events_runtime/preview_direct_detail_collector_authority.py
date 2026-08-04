from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from . import artscience_detail as _artscience_detail
from . import browser as _browser
from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import preview_collector_authority as _preview
from . import review_effective_fields_authority as _effective

_APPLIED = False
_ARTSCIENCE_SOURCE_ID = "artscience"
_ESPLANADE_SOURCE_ID = "esplanade"
_ESPLANADE_CONTAINER_PREFIX = "/whats-on/festivals-and-series/"
_ESPLANADE_CONTAINER_INDEXES = {
    "festivals",
    "series",
    "free-programmes",
    "collaborations",
}

_ESPLANADE_EVENTS_LINK_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const current = new URL(location.href);
  const candidates = [];
  for (const anchor of document.querySelectorAll("a[href]")) {
    let url;
    try {
      url = new URL(anchor.getAttribute("href"), location.href);
    } catch (error) {
      continue;
    }
    if (url.origin !== current.origin) continue;
    const path = url.pathname.replace(/\/$/, "");
    if (!path.startsWith("/whats-on/festivals-and-series/")) continue;
    if (!path.endsWith("/events")) continue;
    const text = clean(anchor.innerText || anchor.textContent || anchor.getAttribute("aria-label"));
    candidates.push({href: url.href, score: /^events$/i.test(text) ? 0 : 1});
  }
  candidates.sort((left, right) => left.score - right.score);
  return candidates[0]?.href || "";
}
"""


def _listing_card(raw: dict[str, Any]) -> dict[str, Any]:
    title = str(raw.get("title") or "").strip()
    lines = [title] if title else []

    # Esplanade festival/series child cards already carry their own date and venue.
    # Preserve the exact card evidence so the normal listing-field parser can avoid an
    # unnecessary detail-page request when the child card is complete.
    if raw.get("_container_child"):
        raw_lines = raw.get("text_lines")
        if isinstance(raw_lines, list):
            lines = [str(value or "").strip() for value in raw_lines if str(value or "").strip()]
        else:
            lines = [
                value.strip()
                for value in str(raw.get("text") or "").splitlines()
                if value.strip()
            ]
        for value in (
            title,
            str(raw.get("when") or "").strip(),
            str(raw.get("where") or "").strip(),
            str(raw.get("summary") or "").strip(),
        ):
            if value and value not in lines:
                lines.append(value)

    return {
        "url": str(raw.get("detail_url") or "").strip(),
        "headings": [title] if title else [],
        "link_text": title,
        "when": str(raw.get("when") or "").strip(),
        "where": str(raw.get("where") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "text_lines": lines,
        "text": "\n".join(lines),
    }


def _new_context(browser: Any) -> Any:
    return browser.new_context(
        viewport={"width": 1440, "height": 1200},
        device_scale_factor=1,
    )


def _open_page_like_listing(
    context: Any,
    url: str,
    error_prefix: str,
) -> tuple[Any, Any]:
    """Create a fresh Page and make its first navigation like the List Page."""

    page = context.new_page()
    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=_preview.PREVIEW_PAGE_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            raise ValueError(f"{error_prefix}_http_status_{response.status}")
        page.wait_for_timeout(_preview.PREVIEW_SETTLE_MS)
        return page, response
    except Exception:
        if not page.is_closed():
            page.close()
        raise


def _close_browser_document(
    browser: Any | None,
    context: Any | None,
    page: Any | None,
) -> None:
    if page is not None:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
    if context is not None:
        try:
            context.close()
        except Exception:
            pass
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass


def _open_browser_document_like_listing(
    playwright: Any,
    url: str,
    error_prefix: str,
) -> tuple[Any, Any, Any, Any]:
    """Open one URL with the exact process/context/page lifecycle used by Listing."""

    browser = _browser.launch_chromium(playwright)
    context = None
    page = None
    try:
        context = _new_context(browser)
        page, response = _open_page_like_listing(
            context,
            url,
            error_prefix,
        )
        return browser, context, page, response
    except Exception:
        _close_browser_document(browser, context, page)
        raise


def _collect_artscience_detail(
    context: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
    raw: dict[str, Any],
) -> dict[str, str]:
    """Open and parse one ArtScience Detail inside the supplied browser context."""

    requested_url = str(raw.get("detail_url") or "").strip()
    if not requested_url or not _preview._host_allowed(requested_url, source):
        raise ValueError("detail page is outside the source allow-list")

    detail_page, _response = _open_page_like_listing(
        context,
        requested_url,
        "detail",
    )
    try:
        final_url = str(detail_page.url)
        if not _preview._host_allowed(final_url, source):
            raise ValueError("detail page redirected outside the source allow-list")
        detail_page.bring_to_front()
        return _artscience_detail.read_loaded_detail_candidate(
            detail_page,
            source,
            listing.url,
            requested_url,
        )
    finally:
        if not detail_page.is_closed():
            detail_page.close()


def _collect_artscience_detail_in_fresh_browser(
    playwright: Any,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
    raw: dict[str, Any],
) -> dict[str, str]:
    """Run one Detail as the first MBS document in a new sequential browser."""

    browser = _browser.launch_chromium(playwright)
    context = None
    try:
        context = _new_context(browser)
        return _collect_artscience_detail(
            context,
            source,
            listing,
            raw,
        )
    finally:
        _close_browser_document(browser, context, None)


def _collect_detail(
    playwright: Any,
    shared_context: Any | None,
    source: dict[str, Any],
    listing: _review.ListingPageCandidate,
    raw: dict[str, Any],
) -> dict[str, str]:
    if listing.source_id == _ARTSCIENCE_SOURCE_ID:
        return _collect_artscience_detail_in_fresh_browser(
            playwright,
            source,
            listing,
            raw,
        )

    if shared_context is None:
        raise RuntimeError("shared detail context is unavailable")
    return _effective.detail_candidate(
        shared_context,
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


def _payload_rows(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(payload, dict):
        rows = [
            item
            for item in payload.get("rows") or []
            if isinstance(item, dict)
        ]
        observed = payload.get("observed") or {}
        return rows, observed if isinstance(observed, dict) else {}
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], {}
    return [], {}


def _is_esplanade_container_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "/").rstrip("/")
    if host != "esplanade.com" or not path.startswith(_ESPLANADE_CONTAINER_PREFIX):
        return False

    tail = path[len(_ESPLANADE_CONTAINER_PREFIX):].strip("/")
    if not tail or tail in _ESPLANADE_CONTAINER_INDEXES:
        return False
    parts = [part.casefold() for part in tail.split("/") if part]
    if not parts or "events" in parts:
        return False
    if parts[-1] in {"about", "contact", "ticketing-and-promotions"}:
        return False

    if parts[0] == "festivals":
        return len(parts) >= 3
    if parts[0] in {"series", "free-programmes", "collaborations"}:
        return len(parts) >= 2
    # Legacy aliases such as /baybeats/2026, /a-date-with-friends/2026 and
    # /dans-focus redirect to the canonical festival/series landing page.
    return True


def _is_esplanade_child_event_url(value: str, event_listing_url: str) -> bool:
    try:
        parsed = urlsplit(value)
        listing = urlsplit(event_listing_url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "/").rstrip("/")
    listing_path = (listing.path or "/").rstrip("/")
    if host != "esplanade.com" or "/events/" not in path:
        return False
    if listing_path.endswith("/events"):
        return path.startswith(listing_path + "/")
    return path.startswith(_ESPLANADE_CONTAINER_PREFIX)


def _evaluate_listing_rows(
    page: Any,
    source: dict[str, Any],
    listing_url: str,
    max_events: int,
) -> list[dict[str, Any]]:
    payload = page.evaluate(
        _preview.PREVIEW_LISTING_JS,
        {
            "allowedDomains": source.get("allowed_domains") or [],
            "listingUrl": listing_url,
            "sourceId": _ESPLANADE_SOURCE_ID,
            "maxEvents": max(1, max_events),
        },
    ) or {}
    rows, _observed = _payload_rows(payload)
    return rows


def _child_rows_from_payload(
    rows: list[dict[str, Any]],
    *,
    event_listing_url: str,
    container_url: str,
    container_title: str,
    max_events: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        detail_url = str(raw.get("detail_url") or "").strip()
        if (
            not detail_url
            or detail_url in seen
            or not _is_esplanade_child_event_url(detail_url, event_listing_url)
        ):
            continue
        child = dict(raw)
        child["_container_child"] = True
        child["_container_url"] = container_url
        child["_container_title"] = container_title
        child["_evidence_page_url"] = event_listing_url
        output.append(child)
        seen.add(detail_url)
        if len(output) >= max_events:
            break
    return output


def _expand_esplanade_container(
    context: Any,
    source: dict[str, Any],
    raw: dict[str, Any],
    max_events: int,
) -> tuple[list[dict[str, Any]], str]:
    container_url = str(raw.get("detail_url") or "").strip()
    container_title = str(raw.get("title") or "").strip()
    page, _response = _open_page_like_listing(
        context,
        container_url,
        "container",
    )
    try:
        final_container_url = str(page.url)
        if not _preview._host_allowed(final_container_url, source):
            raise ValueError("container page redirected outside the source allow-list")

        # Keep the landing-page cards as a fallback because some Esplanade Events tabs
        # are populated later than the landing page itself.
        landing_rows = _evaluate_listing_rows(
            page,
            source,
            final_container_url,
            max_events,
        )
        landing_children = _child_rows_from_payload(
            landing_rows,
            event_listing_url=final_container_url,
            container_url=final_container_url,
            container_title=container_title,
            max_events=max_events,
        )

        events_url = str(page.evaluate(_ESPLANADE_EVENTS_LINK_JS) or "").strip()
        if not events_url or not _preview._host_allowed(events_url, source):
            return landing_children, final_container_url

        if events_url.rstrip("/") != final_container_url.rstrip("/"):
            response = page.goto(
                events_url,
                wait_until="domcontentloaded",
                timeout=_preview.PREVIEW_PAGE_TIMEOUT_MS,
            )
            if response is not None and response.status >= 400:
                raise ValueError(f"container_events_http_status_{response.status}")
            page.wait_for_timeout(_preview.PREVIEW_SETTLE_MS)

        final_events_url = str(page.url)
        events_rows = _evaluate_listing_rows(
            page,
            source,
            final_events_url,
            max_events,
        )
        event_children = _child_rows_from_payload(
            events_rows,
            event_listing_url=final_events_url,
            container_url=final_container_url,
            container_title=container_title,
            max_events=max_events,
        )
        return (event_children or landing_children), final_events_url
    finally:
        if not page.is_closed():
            page.close()


def _expand_esplanade_rows(
    context: Any,
    source: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, list[dict[str, str]]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    container_count = 0
    child_count = 0
    errors: list[dict[str, str]] = []

    for raw in rows:
        if len(output) >= _preview.MAX_PREVIEW_EVENTS:
            break
        detail_url = str(raw.get("detail_url") or "").strip()
        if not _is_esplanade_container_url(detail_url):
            if detail_url and detail_url not in seen:
                output.append(raw)
                seen.add(detail_url)
            continue

        container_count += 1
        remaining = _preview.MAX_PREVIEW_EVENTS - len(output)
        try:
            children, events_url = _expand_esplanade_container(
                context,
                source,
                raw,
                remaining,
            )
        except Exception as exc:
            errors.append(
                {
                    "container_url": detail_url,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
            continue

        if not children:
            errors.append(
                {
                    "container_url": detail_url,
                    "error": "no_child_event_cards_recognised",
                }
            )
            continue

        for child in children:
            child_url = str(child.get("detail_url") or "").strip()
            if not child_url or child_url in seen:
                continue
            child["_evidence_page_url"] = str(
                child.get("_evidence_page_url") or events_url
            )
            output.append(child)
            seen.add(child_url)
            child_count += 1
            if len(output) >= _preview.MAX_PREVIEW_EVENTS:
                break

    return output, container_count, child_count, errors


def collect_preview(store: _review.EventReviewStore) -> _review.ReviewState:
    """Collect one selected Listing, expanding Esplanade festival containers."""

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
    fresh_detail_browsers = 0
    container_count = 0
    container_child_count = 0
    container_errors: list[dict[str, str]] = []
    default_venue = str(source.get("default_venue") or source.get("name") or "")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        listing_browser = None
        listing_context = None
        listing_page = None
        try:
            (
                listing_browser,
                listing_context,
                listing_page,
                response,
            ) = _open_browser_document_like_listing(
                playwright,
                listing.url,
                "listing",
            )
            if response is not None:
                http_status = int(response.status)
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
            rows, observed = _payload_rows(payload)

            if listing.source_id == _ESPLANADE_SOURCE_ID:
                (
                    rows,
                    container_count,
                    container_child_count,
                    container_errors,
                ) = _expand_esplanade_rows(
                    listing_context,
                    source,
                    rows,
                )

            if listing.source_id == _ARTSCIENCE_SOURCE_ID:
                # Detail must be the first MBS document in a new Chromium process.
                # Close the Listing process before starting the first Detail process.
                _close_browser_document(
                    listing_browser,
                    listing_context,
                    listing_page,
                )
                listing_browser = None
                listing_context = None
                listing_page = None
            else:
                if not listing_page.is_closed():
                    listing_page.close()
                listing_page = None

            for raw in rows:
                detail_url = str(raw.get("detail_url") or "").strip()
                title = str(raw.get("title") or "").strip()
                if not title or not _preview._host_allowed(detail_url, source):
                    continue

                detail_attempts += 1
                if listing.source_id == _ARTSCIENCE_SOURCE_ID:
                    fresh_detail_browsers += 1
                try:
                    detail = _collect_detail(
                        playwright,
                        listing_context,
                        source,
                        listing,
                        raw,
                    )
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
            _close_browser_document(
                listing_browser,
                listing_context,
                listing_page,
            )

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
                    page_url=str(raw.get("_evidence_page_url") or final_url),
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

    artscience = listing.source_id == _ARTSCIENCE_SOURCE_ID
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
                "fresh_browser_first_goto_as_listing"
                if artscience
                else "detail_owner_navigation"
            ),
            "preview_detail_fresh_browser_count": fresh_detail_browsers,
            "preview_detail_transport": (
                "sequential_browser_processes"
                if artscience
                else "same_browser_context"
            ),
            "preview_browser_process_count": (
                1 + fresh_detail_browsers if artscience else 1
            ),
            "preview_browser_reuse": (
                "single_playwright_sequential_browsers"
                if artscience
                else "listing_and_details"
            ),
            "preview_detail_context_count": (
                fresh_detail_browsers if artscience else 1
            ),
            "preview_container_policy": "expand_esplanade_festival_series",
            "preview_container_count": container_count,
            "preview_container_child_count": container_child_count,
            "preview_container_errors": container_errors,
            "preview_candidate_listing_detail_urls": listing_detail_urls,
            "detail_page_request_count": detail_attempts,
            "detail_page_requests_skipped": 0,
            "detail_page_error_count": len(detail_errors),
            "detail_page_errors": detail_errors,
            "final_url": final_url,
            "http_status": http_status,
            "listing_diagnostics": [diagnostic.model_dump(mode="json")],
            "errors": container_errors,
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
    "_collect_artscience_detail",
    "_collect_artscience_detail_in_fresh_browser",
    "_expand_esplanade_container",
    "_expand_esplanade_rows",
    "_is_esplanade_container_url",
    "_open_browser_document_like_listing",
    "_open_page_like_listing",
]
