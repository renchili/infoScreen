from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_provenance_authority as _provenance
from .detail_summary_authority import useful_event_summary

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

FALLBACK_DETAIL_FIELDS_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event|presale|pre-sale|ticket sale|registration opens?)\b/i.test(clean(value));
  const dateLike = value => /\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+20\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+20\d{2}\b/i.test(clean(value));
  const root = document.querySelector("main") || document.querySelector("article") || document.body;
  const add = (rows, value) => {
    const text = clean(value);
    if (text && !rows.includes(text)) rows.push(text);
  };
  const values = element => {
    const output = [];
    for (const attribute of [
      "datetime", "content", "data-date", "data-start-date", "data-end-date",
      "data-location", "data-venue", "aria-label"
    ]) {
      add(output, element.getAttribute && element.getAttribute(attribute));
    }
    add(output, element.innerText || element.textContent || "");
    return output;
  };
  const rejectedElement = element => {
    const own = values(element).join(" ");
    if (rejected(own)) return true;
    const parentText = clean(element.parentElement?.innerText || element.parentElement?.textContent || "");
    return parentText.length <= 260 && rejected(parentText);
  };

  const dates = [];
  for (const element of root.querySelectorAll(
    "time[datetime],time,[itemprop='startDate'],[itemprop='endDate']," +
    "[data-date],[data-start-date],[data-end-date]," +
    "[class*='date' i],[id*='date' i]"
  )) {
    if (!visible(element) || rejectedElement(element)) continue;
    for (const value of values(element)) {
      if (dateLike(value)) add(dates, value);
    }
  }

  const venues = [];
  for (const element of root.querySelectorAll(
    "address,[itemprop='location'],[data-location],[data-venue]," +
    "[class*='location' i],[id*='location' i]," +
    "[class*='venue' i],[id*='venue' i]"
  )) {
    if (!visible(element) || rejectedElement(element)) continue;
    for (const value of values(element)) {
      if (value && value.length <= 220 && !dateLike(value)) add(venues, value);
    }
  }

  const summary = clean(document.querySelector('meta[name="description"]')?.content) ||
    clean(document.querySelector('meta[property="og:description"]')?.content);
  return {dates, venues, summary};
}
"""


def _clean_rows(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    output: list[str] = []
    for value in raw:
        text = _extract.clean(value)
        if text and text not in output:
            output.append(text)
    return output


def _best_summary(
    payload: dict[str, Any],
    merged: dict[str, Any],
    event: dict[str, Any] | None = None,
    listing_summary: object = "",
) -> str:
    """Choose real narrative detail text before parser fallback labels.

    ``event_from_card`` intentionally returns a non-empty generic fallback when no
    summary survives its parser. Review previously preferred that fallback over the
    detail payload's real narrative, producing ``Open the official page for details.``
    while the kiosk displayed the same URL's extracted description.
    """
    candidates = [
        *_clean_rows(payload.get("summary_candidates")),
        payload.get("summary"),
        *_clean_rows(merged.get("detail_summary_candidates")),
        merged.get("detail_summary"),
    ]
    if isinstance(event, dict):
        candidates.append(event.get("summary"))
    candidates.append(listing_summary)

    for candidate in candidates:
        summary = useful_event_summary(candidate)
        if summary:
            return _extract.short(summary, 500)
    return ""


def _merge_fallback_fields(
    payload: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Fill missing fields without diluting already authoritative detail rows."""
    merged = dict(payload)
    for key in ("dates", "venues"):
        current = [
            " ".join(str(value or "").split())
            for value in merged.get(key) or []
            if " ".join(str(value or "").split())
        ]
        if current:
            merged[key] = current
            continue

        filled: list[str] = []
        for value in fallback.get(key) or []:
            text = " ".join(str(value or "").split())
            if text and text not in filled:
                filled.append(text)
        merged[key] = filled

    if not str(merged.get("summary") or "").strip():
        merged["summary"] = str(fallback.get("summary") or "").strip()
    return merged


def _listing_candidate_if_complete(
    source: dict[str, Any],
    requested_url: str,
    card: dict[str, Any],
) -> dict[str, str] | None:
    """Use an authoritative complete list card without opening its detail page.

    The source inventory defines the rendered list card as the membership authority
    and detail pages as enrichment. Opening every detail page made Review Preview
    serially wait on dozens of pages even when title, date, and venue were already
    present. A source may opt into ``review_detail_policy=always`` when its detail page
    must replace misleading child/list-card fields, as ACM does.
    """
    policy = _extract.clean(source.get("review_detail_policy") or "missing_fields").casefold()
    if policy == "always":
        return None

    listing = _detail_dates._listing_fields(source, card)
    if not all(listing.get(key) for key in ("title", "when", "where")):
        return None

    return {
        "detail_url": requested_url,
        "title": listing["title"],
        "when": listing["when"],
        "where": listing["where"],
        "summary": useful_event_summary(listing.get("summary")) or "",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "",
    }


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Read one required detail page without waiting for long-lived lifecycle events.

    Complete authoritative list cards return immediately. Official Event pages are
    opened only when fields are missing or the source explicitly requires detail
    correction. Missing fields produce an incomplete candidate rather than removing
    membership.
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

    listing_candidate = _listing_candidate_if_complete(source, requested_url, card)
    if listing_candidate is not None:
        return listing_candidate

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
            pass
        detail.wait_for_timeout(150)

        final_url = _provenance.listing_detail_url(listing_url, str(detail.url))
        if not final_url:
            final_url = requested_url

        payload = detail.evaluate(_browser.DETAIL_CARD_JS) or {}
        if not isinstance(payload, dict):
            payload = {}
        if not payload.get("dates") or not payload.get("venues") or not payload.get("summary"):
            fallback = detail.evaluate(FALLBACK_DETAIL_FIELDS_JS) or {}
            if isinstance(fallback, dict):
                payload = _merge_fallback_fields(payload, fallback)

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
        listing = _detail_dates._listing_fields(source, card)

        if event is None:
            authoritative_when, authoritative_when_line = _extract.pick_when(merged)
            authoritative_where = _extract.pick_venue(
                source,
                merged,
                authoritative_when,
                authoritative_when_line,
            )
            title = (
                _extract.clean(payload.get("title"))
                or listing["title"]
                or _extract.title_from_url(final_url)
            )
            return {
                "detail_url": final_url,
                "title": title,
                "when": _extract.clean(authoritative_when) or listing["when"],
                "where": _extract.clean(authoritative_where) or listing["where"],
                "summary": _best_summary(
                    payload,
                    merged,
                    listing_summary=listing["summary"],
                ),
                "detail_status": "incomplete",
                "detail_error": reason,
                "detail_page_title": page_title,
            }

        return {
            "detail_url": final_url,
            "title": str(event.get("title") or payload.get("title") or ""),
            "when": str(event.get("when") or ""),
            "where": str(event.get("where") or ""),
            "summary": _best_summary(
                payload,
                merged,
                event,
                listing["summary"],
            ),
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": page_title,
        }
    finally:
        detail.close()


def apply() -> None:
    """Install bounded, conditional detail navigation for Review Preview."""
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
    "FALLBACK_DETAIL_FIELDS_JS",
    "_best_summary",
    "_listing_candidate_if_complete",
    "apply",
]
