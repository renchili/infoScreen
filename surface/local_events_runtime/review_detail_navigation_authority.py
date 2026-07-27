from __future__ import annotations

import re
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

_FIELD_LABELS = {
    "date": {"date", "dates", "when"},
    "time": {"time", "times", "duration"},
    "where": {"location", "venue", "where"},
}
_ALL_FIELD_LABELS = set().union(*_FIELD_LABELS.values(), {"admission", "ticket", "tickets"})
_MONTH_PATTERN = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
)
_UNLABELLED_DATE_RE = re.compile(
    rf"(?:\b20\d{{2}}-\d{{1,2}}-\d{{1,2}}\b|"
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?"
    rf"(?:\s*(?:,|[-–—])\s*\d{{1,2}}(?:st|nd|rd|th)?)*"
    rf"\s+{_MONTH_PATTERN}\s+20\d{{2}}\b|"
    rf"\b{_MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s+20\d{{2}}\b)",
    re.I,
)
_UNLABELLED_TIME_RE = re.compile(
    r"\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)?\s*[-–—]\s*"
    r"\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b",
    re.I,
)
_UNLABELLED_VENUE_RE = re.compile(
    r"\b(?:museum|gallery|galleries|room|hall|theatre|theater|auditorium|"
    r"foyer|atrium|courtyard|plaza|studio|park|gardens?|zoo|centre|center)\b",
    re.I,
)
_UNLABELLED_VENUE_NOISE_RE = re.compile(
    r"^(?:visit|explore|experience|discover|join|learn|see|walk|programme|"
    r"programmes|admission|ticket|tickets|book)\b",
    re.I,
)


def _clean_rows(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    output: list[str] = []
    for value in raw:
        text = _extract.clean(value)
        if text and text not in output:
            output.append(text)
    return output


def _payload_lines(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("lines") or payload.get("text_lines")
    if isinstance(rows, list):
        return _clean_rows(rows)
    return [
        _extract.clean(line)
        for line in str(payload.get("text") or "").splitlines()
        if _extract.clean(line)
    ]


def _label_key(value: object) -> str:
    return _extract.clean(value).rstrip(":").casefold()


def _labeled_values(lines: list[str], labels: set[str]) -> list[str]:
    output: list[str] = []
    for index, line in enumerate(lines):
        if _label_key(line) not in labels:
            continue
        for candidate in lines[index + 1 : index + 5]:
            if _label_key(candidate) in _ALL_FIELD_LABELS:
                break
            text = _extract.clean(candidate)
            if text and text not in output:
                output.append(text)
    return output


def _unlabelled_schedule_line(lines: list[str]) -> str:
    """Return a complete schedule line exactly as collected from the page."""

    for line in lines:
        text = _extract.clean(line)
        if not text or len(text) > 240:
            continue
        if _UNLABELLED_DATE_RE.search(text) and _UNLABELLED_TIME_RE.search(text):
            return text
    return ""


def _unlabelled_venue_line(lines: list[str]) -> str:
    """Return a short venue line exactly as collected, never a narrative sentence."""

    for line in lines:
        text = _extract.clean(line)
        if not text or len(text) > 140 or len(text.split()) > 14:
            continue
        if _UNLABELLED_VENUE_NOISE_RE.search(text):
            continue
        if _UNLABELLED_DATE_RE.search(text) or _UNLABELLED_TIME_RE.search(text):
            continue
        if _UNLABELLED_VENUE_RE.search(text):
            return text
    return ""


def _raw_when(payload: dict[str, Any]) -> str:
    """Return exact collected Date/Time/Duration text without reconstruction."""

    lines = _payload_lines(payload)
    date_rows = _labeled_values(lines, _FIELD_LABELS["date"])
    time_rows = _labeled_values(lines, _FIELD_LABELS["time"])

    values: list[str] = []
    for value in [*date_rows, *time_rows]:
        if value and value not in values:
            values.append(value)
    if values:
        return " · ".join(values)

    schedule_line = _unlabelled_schedule_line(lines)
    if schedule_line:
        return schedule_line

    return " · ".join(_clean_rows(payload.get("dates")))


def _raw_where(payload: dict[str, Any]) -> str:
    """Return an exact collected Location/Venue row; never use a source default."""

    lines = _payload_lines(payload)
    rows = _labeled_values(lines, _FIELD_LABELS["where"])
    if rows:
        return rows[0]

    venue_line = _unlabelled_venue_line(lines)
    if venue_line:
        return venue_line

    rows = _clean_rows(payload.get("venues"))
    return rows[0] if rows else ""


def _raw_summary(payload: dict[str, Any]) -> str:
    for candidate in [
        *_clean_rows(payload.get("summary_candidates")),
        payload.get("summary"),
    ]:
        summary = useful_event_summary(candidate)
        if summary:
            return _extract.short(summary, 500)
    return ""


def _merge_fallback_fields(
    payload: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Add only exact fields collected from the same detail document."""

    merged = dict(payload)
    for key in ("dates", "venues"):
        if _clean_rows(merged.get(key)):
            continue
        merged[key] = _clean_rows(fallback.get(key))
    if not _extract.clean(merged.get("summary")):
        merged["summary"] = _extract.clean(fallback.get("summary"))
    return merged


def _listing_candidate_if_complete(
    source: dict[str, Any],
    requested_url: str,
    card: dict[str, Any],
) -> dict[str, str] | None:
    """Use exact complete list-card fields unless the source requires detail reading."""

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
    """Read exact detail fields without parser, runtime, or source-default rewriting."""

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
            detail.wait_for_function(DETAIL_READY_JS, timeout=DETAIL_CONTENT_WAIT_MS)
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

        title = _extract.clean(payload.get("title") or detail.title() or "")
        when = _raw_when(payload)
        where = _raw_where(payload)
        summary = _raw_summary(payload)

        missing = [
            name
            for name, value in (("title", title), ("when", when), ("where", where))
            if not value
        ]
        return {
            "detail_url": final_url,
            "title": title,
            "when": when,
            "where": where,
            "summary": summary,
            "detail_status": "incomplete" if missing else "collected",
            "detail_error": "missing_detail_" + "_and_".join(missing) if missing else "",
            "detail_page_title": _extract.clean(payload.get("title") or detail.title() or ""),
        }
    finally:
        detail.close()


def apply() -> None:
    """Install direct, bounded detail collection for Review Preview."""

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
    "apply",
    "_detail_candidate",
    "_listing_candidate_if_complete",
    "_raw_summary",
    "_raw_when",
    "_raw_where",
    "_unlabelled_schedule_line",
    "_unlabelled_venue_line",
]
