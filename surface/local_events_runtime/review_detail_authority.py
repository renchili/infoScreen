from __future__ import annotations

from typing import Any

from . import detail_authority
from . import event_review as _review
from .extract import clean
from .source_overrides import (
    AUTHORITATIVE_DETAIL_JS,
    _merge_detail,
    _valid_title,
)

_APPLIED = False


def _official_detail_url(
    source: dict[str, Any],
    listing_url: str,
    payload: dict[str, Any],
    browser_url: str,
) -> str:
    """Return the official public detail URL reported by the detail page.

    The browser URL is only a fallback. A same-domain canonical URL from the detail
    document is preferred, then source-configured public-path rewrites are applied.
    The result must remain outside the originating listing page.
    """

    listing = _review.canonical_url(listing_url)
    candidates = [payload.get("canonical"), browser_url]
    errors: list[str] = []

    for raw in candidates:
        value = detail_authority.public_detail_url(source, raw)
        if not value:
            continue
        try:
            canonical = _review.canonical_url(value)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not _review._host_allowed(canonical, source):
            errors.append("detail URL is outside the source allow-list")
            continue
        if canonical == listing:
            errors.append("detail URL resolves to the listing page")
            continue
        return canonical

    raise ValueError(errors[0] if errors else "official detail URL not found")


def _authoritative_title(
    payload: dict[str, Any],
    event: dict[str, Any] | None,
    merged: dict[str, Any],
) -> str:
    """Prefer the detail-page H1/OG title over list-card headings."""

    for value in [
        payload.get("title"),
        (event or {}).get("title"),
        *((merged.get("headings") or [])[:2]),
        merged.get("link_text"),
    ]:
        title = _valid_title(value)
        if title:
            return title
    return _review._listing_title(merged)


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Collect review fields through the authoritative detail parser."""

    if "#nhb-" in raw_url or "#nhb-json-" in raw_url:
        return {
            "detail_url": raw_url,
            "title": _review._listing_title(card),
            "when": "",
            "where": "",
            "summary": "",
            "detail_status": "incomplete",
            "detail_error": "public_detail_url_not_found",
            "detail_page_title": "",
        }

    requested_url = _review.canonical_url(raw_url)
    if not _review._host_allowed(requested_url, source):
        raise ValueError("detail URL is outside the source allow-list")
    if requested_url == _review.canonical_url(listing_url):
        raise ValueError("detail URL resolves to the listing page")

    detail = context.new_page()
    try:
        response = detail.goto(
            requested_url,
            wait_until="domcontentloaded",
            timeout=_review.DOM_TIMEOUT_MS,
        )
        detail.wait_for_timeout(250)
        if response is not None and response.status >= 400:
            raise ValueError(f"detail_http_status_{response.status}")

        browser_url = _review.canonical_url(str(detail.url))
        if not _review._host_allowed(browser_url, source):
            raise ValueError("detail page redirected outside the source allow-list")

        payload = detail.evaluate(AUTHORITATIVE_DETAIL_JS) or {}
        if not isinstance(payload, dict):
            payload = {}
        detail_url = _official_detail_url(
            source,
            listing_url,
            payload,
            browser_url,
        )

        detail_card = {
            **card,
            "url": detail_url,
            "page_url": detail_url,
            "detail_urls": [detail_url],
            "detail_url_count": 1,
        }
        merged = _merge_detail(source, detail_card, payload, 0)
        merged.update(
            url=detail_url,
            page_url=detail_url,
            detail_urls=[detail_url],
            detail_url_count=1,
        )

        event, reason = detail_authority.event_from_card(source, merged)
        title = _authoritative_title(payload, event, merged)
        page_title = _valid_title(payload.get("title")) or clean(detail.title() or "")

        if event is None:
            return {
                "detail_url": detail_url,
                "title": title,
                "when": "",
                "where": "",
                "summary": clean(merged.get("text") or "")[:500],
                "detail_status": "incomplete",
                "detail_error": reason,
                "detail_page_title": page_title,
            }

        return {
            "detail_url": detail_url,
            "title": title,
            "when": str(event.get("when") or ""),
            "where": str(event.get("where") or ""),
            "summary": str(event.get("summary") or ""),
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": page_title,
        }
    finally:
        detail.close()


def apply() -> None:
    """Install authoritative detail title and URL handling for review collection."""

    global _APPLIED
    if _APPLIED:
        return
    detail_authority.apply()
    _review._detail_candidate = _detail_candidate
    _APPLIED = True


__all__ = ["apply"]
