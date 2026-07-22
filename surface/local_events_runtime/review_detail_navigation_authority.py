from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_provenance_authority as _provenance

_APPLIED = False
DETAIL_COMMIT_TIMEOUT_MS = 60_000
DETAIL_CONTENT_WAIT_MS = 12_000

DETAIL_READY_JS = r"""
() => {
  const body = document.body;
  if (!body) return false;
  const text = String(body.innerText || body.textContent || "").replace(/\s+/g, " ").trim();
  if (text.length < 20) return false;
  return Boolean(
    document.querySelector("main h1, article h1, h1") ||
    document.querySelector(
      "time[datetime], [itemprop='startDate'], [itemprop='endDate'], " +
      "[class*='event-date' i], [class*='date-range' i], " +
      "[class*='event-location' i], [class*='event-venue' i]"
    ) ||
    document.readyState === "interactive" ||
    document.readyState === "complete"
  );
}
"""


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Read one detail page without waiting for long-lived lifecycle events.

    Official Event pages often keep analytics, consent, or personalisation requests
    alive. Preview remains a blocking operation, but each detail read stops waiting
    as soon as the response has committed and a readable activity document exists.
    Missing fields produce an incomplete candidate rather than removing membership.
    """

    if "#nhb-" in raw_url or "#nhb-json-" in raw_url:
        listing = _detail_dates._listing_fields(source, card)
        return {
            "detail_url": raw_url,
            **listing,
            "detail_status": "incomplete",
            "detail_error": "public_detail_url_not_found",
            "detail_page_title": "",
        }

    requested_url = _provenance.listing_detail_url(listing_url, raw_url)
    if not requested_url:
        raise ValueError("detail URL is not a safe HTTP(S) target from the listing")

    detail = context.new_page()
    try:
        response = detail.goto(
            requested_url,
            wait_until="commit",
            timeout=DETAIL_COMMIT_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            raise ValueError(f"detail_http_status_{response.status}")

        try:
            detail.wait_for_function(
                DETAIL_READY_JS,
                timeout=DETAIL_CONTENT_WAIT_MS,
            )
        except Exception:
            # The extractor still inspects the committed DOM. Field absence is
            # represented as detail_status=incomplete, not as a dropped activity.
            pass
        detail.wait_for_timeout(150)

        final_url = _provenance.listing_detail_url(listing_url, str(detail.url))
        if not final_url:
            final_url = requested_url

        payload = detail.evaluate(_browser.DETAIL_CARD_JS) or {}
        if not isinstance(payload, dict):
            payload = {}
        merged = _browser.merge_detail_payload(
            {
                **card,
                "url": final_url,
                "page_url": final_url,
                "detail_urls": [final_url],
                "detail_url_count": 1,
            },
            payload,
        )
        event, reason = _extract.event_from_card(source, merged)
        page_title = _extract.clean(payload.get("title") or detail.title() or "")

        if event is None:
            listing = _detail_dates._listing_fields(source, card)
            title = (
                _extract.clean(payload.get("title"))
                or listing["title"]
                or _extract.title_from_url(final_url)
            )
            summary = (
                _extract.clean(payload.get("summary"))
                or _extract.clean(merged.get("detail_summary"))
                or listing["summary"]
            )
            return {
                "detail_url": final_url,
                "title": title,
                "when": _detail_dates._activity_pick_when(merged)[0] or listing["when"],
                "where": _detail_dates._activity_pick_venue(
                    source,
                    merged,
                    "",
                    "",
                ) or listing["where"],
                "summary": summary,
                "detail_status": "incomplete",
                "detail_error": reason,
                "detail_page_title": page_title,
            }

        return {
            "detail_url": final_url,
            "title": str(event.get("title") or payload.get("title") or ""),
            "when": str(event.get("when") or ""),
            "where": str(event.get("where") or ""),
            "summary": str(event.get("summary") or payload.get("summary") or ""),
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": page_title,
        }
    finally:
        detail.close()


def apply() -> None:
    """Install bounded blocking detail navigation for Review Preview."""

    global _APPLIED
    if _APPLIED:
        return

    from . import event_review as review

    review._detail_candidate = _detail_candidate
    _APPLIED = True


__all__ = [
    "DETAIL_COMMIT_TIMEOUT_MS",
    "DETAIL_CONTENT_WAIT_MS",
    "DETAIL_READY_JS",
    "apply",
]
