from __future__ import annotations

import re
import time
from typing import Any

from . import detail_date_authority as _detail_dates
from . import event_review as _review
from . import extract as _extract
from . import review_detail_navigation_authority as _detail_navigation

_APPLIED = False
_BASE_LOAD = None
_BASE_STATE_PAYLOAD = None
_BASE_REPLACE_EVENTS = None
_BASE_RAW_WHEN = None
_REQUESTED_URL_PAYLOAD_KEY = "_infoscreen_requested_url"

_DATE_NOISE_RE = re.compile(
    r"\b(?:last updated|updated on|page updated|copyright|privacy|cookie|"
    r"newsletter|presale|pre-sale|ticket sale|registration opens?|"
    r"previous programme|next programme|previous event|next event)\b",
    re.I,
)
_ESPLANADE_SERIES_URL_RE = re.compile(
    r"^https?://(?:www\.)?esplanade\.com/whats-on/festivals-and-series/"
    r"(?:series|festivals?)/",
    re.I,
)
_DATE_SEGMENT_SEPARATOR_RE = re.compile(r"\s+(?:·|•|\|)\s+")

DETAIL_STABLE_READY_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const root = document.querySelector("main") ||
    document.querySelector("article") || document.body;
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || ""));
  if (!root || !heading) return false;
  const text = clean(root.innerText || root.textContent || "");
  return document.readyState === "complete" && text.length >= 120;
}
"""

# Read plain activity fact rows from the current detail page. The activity title is the
# start boundary and recommendation headings are the end boundary, so related activities
# cannot supply dates or venues for the current activity.
DETAIL_DOCUMENT_FACTS_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const key = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const add = (rows, value) => {
    const text = clean(value);
    if (text && !rows.includes(text)) rows.push(text);
  };
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event|presale|pre-sale|ticket sale|registration opens?)\b/i.test(clean(value));
  const boundary = value => /^(?:you might also like|you may also like|activities? (?:might|may) also enjoy|related (?:events?|programmes?|programs?|activities?)|recommended for you|more from|explore more|previous programme|next programme|previous event|next event|visit .+ today)$/i.test(clean(value));
  const dateLike = value => /(?:\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?(?:\s*(?:,|&|\/|[-–—])\s*\d{1,2}(?:st|nd|rd|th)?)*\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+20\d{2}\b)/i.test(clean(value));
  const timeLike = value => /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b|\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)?\s*[-–—]\s*\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i.test(clean(value));
  const venueLike = value => /\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|auditorium|foyer|atrium|courtyard|plaza|studio|park|gardens?|zoo|centre|center)\b/i.test(clean(value));

  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || "")) || null;
  const title = clean(heading ? (heading.innerText || heading.textContent) : "");
  const titleKey = key(title);
  const root = (heading && heading.closest("main")) ||
    document.querySelector("main") ||
    (heading && heading.closest(
      "article, [class*='event-detail' i], [class*='eventDetail' i], " +
      "[class*='detail-page' i], [class*='content-detail' i]"
    )) || document.querySelector("article") || document.body;

  const rawLines = String(root ? (root.innerText || root.textContent || "") : "")
    .split(/\n+/).map(clean).filter(Boolean);
  const sectionLines = [];
  let started = !title;
  for (const line of rawLines) {
    if (!started) {
      const lineKey = key(line);
      if (lineKey === titleKey || lineKey.includes(titleKey) || titleKey.includes(lineKey)) {
        started = true;
      } else {
        continue;
      }
    }
    if (boundary(line) && sectionLines.length >= 2) break;
    if (!rejected(line)) add(sectionLines, line);
    if (sectionLines.length >= 260) break;
  }

  const dates = [];
  const venues = [];
  for (const line of sectionLines) {
    if (line.length <= 240 && dateLike(line)) add(dates, line);
    if (
      line.length <= 180 && line.split(/\s+/).length <= 24 &&
      venueLike(line) && !dateLike(line) && !timeLike(line) &&
      !/^(?:visit|explore|experience|discover|join|learn|see|walk|programme|programmes|admission|ticket|tickets|book)\b/i.test(line)
    ) add(venues, line);
  }

  for (const element of root ? root.querySelectorAll(
    "time[datetime], [itemprop='startDate'], [itemprop='endDate'], " +
    "[data-date], [data-start-date], [data-end-date]"
  ) : []) {
    for (const attribute of ["datetime", "content", "data-date", "data-start-date", "data-end-date"]) {
      const value = clean(element.getAttribute(attribute));
      if (value && dateLike(value)) add(dates, value);
    }
    const text = clean(element.innerText || element.textContent || "");
    if (text && dateLike(text)) add(dates, text);
  }

  for (const image of root ? root.querySelectorAll("img[alt]") : []) {
    const alt = clean(image.getAttribute("alt"));
    if (alt && dateLike(alt)) add(dates, alt);
  }

  const summary = clean(document.querySelector('meta[name="description"]')?.content) ||
    clean(document.querySelector('meta[property="og:description"]')?.content);
  return {dates, venues, summary, lines: sectionLines};
}
"""


def _repair_fields(
    raw: dict[str, Any],
    runtime_row: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return collected Review fields unchanged."""

    return dict(raw)


def _line_dates(value: object) -> list[Any]:
    text = _extract.clean(value)
    if not text:
        return []
    try:
        return list(_detail_dates._activity_label_dates(text))
    except Exception:
        return list(_extract.label_dates(text))


def _first_date_fragment(value: str) -> str:
    """Return the earliest complete date fragment from one aggregate text row."""

    text = _extract.clean(value)
    if not text:
        return ""

    for segment in _DATE_SEGMENT_SEPARATOR_RE.split(text):
        candidate = _extract.clean(segment)
        if candidate and _line_dates(candidate):
            return candidate

    try:
        fragments = list(_detail_dates._activity_date_fragments(text))
    except Exception:
        fragments = []

    lowered = text.casefold()
    ranked: list[tuple[int, int, str]] = []
    for fragment in fragments:
        candidate = _extract.clean(fragment)
        if not candidate:
            continue
        position = lowered.find(candidate.casefold())
        if position >= 0:
            ranked.append((position, -len(candidate), candidate))
    if ranked:
        ranked.sort()
        return ranked[0][2]
    return text


def _detail_date_line(
    payload: dict[str, Any],
    requested_url: str = "",
) -> str:
    """Return the current detail's date row, excluding child-programme aggregates."""

    rows: list[object] = []
    raw_dates = payload.get("dates")
    if isinstance(raw_dates, list):
        rows.extend(raw_dates)
    rows.extend(_detail_navigation._payload_lines(payload))

    esplanade_series = bool(_ESPLANADE_SERIES_URL_RE.search(requested_url))
    seen: set[str] = set()
    for raw in rows:
        text = _extract.clean(raw)
        if not text or text in seen or len(text) > 240:
            continue
        seen.add(text)
        if _DATE_NOISE_RE.search(text):
            continue
        if _detail_navigation._label_key(text) in _detail_navigation._ALL_FIELD_LABELS:
            continue
        if not _line_dates(text):
            continue
        return _first_date_fragment(text) if esplanade_series else text
    return ""


def _raw_when(payload: dict[str, Any]) -> str:
    """Use one exact date row, then append at most one opening-hours row."""

    requested_url = _extract.clean(payload.get(_REQUESTED_URL_PAYLOAD_KEY))
    base_picker = _BASE_RAW_WHEN or _detail_navigation._raw_when
    base = _extract.clean(base_picker(payload))
    date_line = _detail_date_line(payload, requested_url)
    if not date_line:
        return ""

    # The generic base picker may concatenate every date-bearing row from the page,
    # including recommendation cards and child programmes. The current page's first
    # exact date range is authoritative.
    values = [date_line]
    if base and base != date_line and not _line_dates(base):
        values.append(base)

    already_has_time = any(
        _detail_navigation._UNLABELLED_TIME_RE.search(value)
        for value in values
    )
    if not already_has_time:
        for line in _detail_navigation._payload_lines(payload):
            text = _extract.clean(line)
            if (
                text
                and text not in values
                and not _line_dates(text)
                and _detail_navigation._UNLABELLED_TIME_RE.search(text)
            ):
                values.append(text)
                break

    return " · ".join(values)


def _merge_document_facts(
    payload: dict[str, Any],
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Append document facts even when the base extractor produced a false date."""

    merged = dict(payload)
    for key in ("dates", "venues"):
        values = _detail_navigation._clean_rows(merged.get(key))
        for value in _detail_navigation._clean_rows(facts.get(key)):
            if value not in values:
                values.append(value)
        merged[key] = values

    lines = _detail_navigation._payload_lines(merged)
    for value in _detail_navigation._clean_rows(facts.get("lines")):
        if value not in lines:
            lines.append(value)
    merged["lines"] = lines
    merged["text_lines"] = lines
    merged["text"] = "\n".join(lines)

    if not _extract.clean(merged.get("summary")):
        merged["summary"] = _extract.clean(facts.get("summary"))
    return merged


def _facts_signature(facts: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("dates", "venues", "lines"):
        values.extend(_detail_navigation._clean_rows(facts.get(key)))
    return "\0".join(values)


def _facts_have_date(facts: dict[str, Any]) -> bool:
    rows: list[str] = []
    rows.extend(_detail_navigation._clean_rows(facts.get("dates")))
    rows.extend(_detail_navigation._clean_rows(facts.get("lines")))
    return any(_line_dates(value) for value in rows)


def _collect_document_facts(page: Any) -> dict[str, Any]:
    """Wait for date-bearing activity facts; never settle early on time-only rows."""

    timeout_seconds = max(1.0, _detail_navigation.DETAIL_CONTENT_WAIT_MS / 1000)
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] = {}
    previous_signature = ""
    stable_since = time.monotonic()

    while True:
        try:
            observed = page.evaluate(DETAIL_DOCUMENT_FACTS_JS) or {}
        except Exception:
            observed = {}
        if isinstance(observed, dict):
            latest = observed

        now = time.monotonic()
        signature = _facts_signature(latest)
        if signature != previous_signature:
            previous_signature = signature
            stable_since = now
        else:
            stable_for = now - stable_since
            if _facts_have_date(latest) and stable_for >= 0.35:
                return latest

        if now >= deadline:
            return latest
        page.wait_for_timeout(150)


def _payload_fields(
    page: Any,
    payload: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Read the effective fields already present in one primary detail payload."""

    title = _extract.clean(payload.get("title") or page.title() or "")
    when = _raw_when(payload)
    where = _detail_navigation._raw_where(payload)
    summary = _detail_navigation._raw_summary(payload)
    return title, when, where, summary


def _read_detail_page(
    page: Any,
    listing_url: str,
    requested_url: str,
    entry: Any | None,
) -> dict[str, str]:
    """Read one detail document and construct the only Review field result."""

    if entry is None:
        response = page.goto(
            requested_url,
            wait_until="commit",
            timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            raise ValueError(f"detail_http_status_{response.status}")
    else:
        try:
            page.wait_for_function(
                _detail_navigation.WAIT_FOR_NAVIGATION_JS,
                timeout=_detail_navigation.DETAIL_COMMIT_TIMEOUT_MS,
            )
        except Exception:
            if str(page.url or "") == "about:blank":
                raise
        status = entry.status.get("value")
        if status is not None and status >= 400:
            raise ValueError(f"detail_http_status_{status}")

    try:
        page.wait_for_function(
            DETAIL_STABLE_READY_JS,
            timeout=_detail_navigation.DETAIL_CONTENT_WAIT_MS,
        )
    except Exception:
        pass

    final_url = _detail_navigation._provenance.listing_detail_url(
        listing_url,
        str(page.url),
    ) or requested_url

    # The enriched primary extractor already reads structured Event data, labeled
    # date/venue fields, and visible activity content. Do not make every candidate wait
    # through the fallback polling window when those required fields are already ready.
    payload = page.evaluate(_detail_navigation._browser.DETAIL_CARD_JS) or {}
    if not isinstance(payload, dict):
        payload = {}
    payload[_REQUESTED_URL_PAYLOAD_KEY] = requested_url
    title, when, where, summary = _payload_fields(page, payload)

    if not all((title, when, where)):
        facts = _collect_document_facts(page)
        payload = _merge_document_facts(payload, facts)
        title, when, where, summary = _payload_fields(page, payload)

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
        "detail_page_title": _extract.clean(payload.get("title") or page.title() or ""),
    }


def detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Single detail owner used by Web collection, caching, and direct review reads."""

    if "#nhb-" in raw_url or "#nhb-json-" in raw_url:
        listing = _detail_dates._listing_fields(source, card)
        return {
            "detail_url": raw_url,
            **listing,
            "detail_status": "incomplete",
            "detail_error": "public_detail_url_not_found",
            "detail_page_title": "",
        }

    requested_url = _detail_navigation._provenance.listing_detail_url(
        listing_url,
        raw_url,
    )
    if not requested_url:
        raise ValueError("detail URL is not a safe HTTP(S) target from the listing")

    listing_candidate = _detail_navigation._listing_candidate_if_complete(
        source,
        requested_url,
        card,
    )
    if listing_candidate is not None:
        return listing_candidate

    state = _detail_navigation._state(context)
    cached = _detail_navigation._cache_get(state, source, requested_url)
    if cached is not None:
        return cached

    _detail_navigation._prepare_prefetch(
        context,
        state,
        source,
        listing_url,
        requested_url,
    )
    entry = _detail_navigation._take_prefetched(state, requested_url)
    page = entry.page if entry is not None else context.new_page()

    try:
        result = _read_detail_page(
            page,
            listing_url,
            requested_url,
            entry,
        )
        _detail_navigation._cache_put(state, source, requested_url, result)
        return result
    finally:
        try:
            is_closed = getattr(page, "is_closed", None)
            if not callable(is_closed) or not is_closed():
                page.close()
        finally:
            state.page_ids.discard(id(page))
            if entry is not None:
                _detail_navigation._fill_prefetch(state)


def _expired(candidate: _review.EventCandidate) -> bool:
    """Exclude explicit past-date results and candidates whose end date has passed."""

    detail_error = _extract.clean(candidate.detail_error).casefold()
    if detail_error == "past_date" or detail_error.startswith("past_date:"):
        return True
    return bool(_detail_dates._candidate_expired(candidate))


def _active_candidates(
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> tuple[list[_review.EventCandidate], dict[str, Any]]:
    active = [candidate for candidate in candidates if not _expired(candidate)]
    removed = len(candidates) - len(active)
    metadata = dict(collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = int(
        metadata.get("expired_candidate_count") or 0
    ) + removed
    return active, metadata


def load(store: _review.EventReviewStore) -> _review.ReviewState:
    state = _BASE_LOAD(store)
    state.events, state.event_collection = _active_candidates(
        list(state.events),
        state.event_collection,
    )
    return state


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    payload = dict(_BASE_STATE_PAYLOAD(store))
    events = [
        dict(row)
        for row in payload.get("events") or []
        if isinstance(row, dict)
    ]
    payload["events"] = [
        row
        for row in events
        if not _expired(_review.EventCandidate.model_validate(row))
    ]
    collection = dict(payload.get("event_collection") or {})
    removed = len(events) - len(payload["events"])
    collection["candidate_count"] = len(payload["events"])
    collection["expired_candidate_count"] = int(
        collection.get("expired_candidate_count") or 0
    ) + removed
    payload["event_collection"] = collection
    return payload


def replace_events(
    store: _review.EventReviewStore,
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    active, metadata = _active_candidates(list(candidates), collection)
    return _BASE_REPLACE_EVENTS(store, active, metadata)


def apply() -> None:
    """Install one final detail and lifecycle owner for Review Web."""

    global _APPLIED, _BASE_LOAD, _BASE_STATE_PAYLOAD
    global _BASE_REPLACE_EVENTS, _BASE_RAW_WHEN

    if not _APPLIED:
        _BASE_RAW_WHEN = _detail_navigation._raw_when
        _BASE_LOAD = (
            _detail_dates._BASE_REVIEW_LOAD
            or _review.EventReviewStore.load
        )
        _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
        _BASE_REPLACE_EVENTS = (
            _detail_dates._BASE_REPLACE_EVENTS
            or _review.EventReviewStore.replace_events
        )
        _APPLIED = True

    # Re-apply these bindings every time so no later authority or test fixture can leave
    # Review collection on an older detail implementation.
    _detail_navigation.DETAIL_READY_JS = DETAIL_STABLE_READY_JS
    _detail_navigation.FALLBACK_DETAIL_FIELDS_JS = DETAIL_DOCUMENT_FACTS_JS
    _detail_navigation._raw_when = _raw_when
    _detail_navigation._read_detail_page = _read_detail_page
    _detail_navigation._detail_candidate = detail_candidate
    _review._detail_candidate = detail_candidate
    _review.EventReviewStore.load = load
    _review.EventReviewStore.state_payload = state_payload
    _review.EventReviewStore.replace_events = replace_events


__all__ = [
    "DETAIL_DOCUMENT_FACTS_JS",
    "DETAIL_STABLE_READY_JS",
    "apply",
    "detail_candidate",
    "load",
    "replace_events",
    "state_payload",
    "_collect_document_facts",
    "_detail_date_line",
    "_expired",
    "_first_date_fragment",
    "_merge_document_facts",
    "_payload_fields",
    "_raw_when",
    "_read_detail_page",
    "_repair_fields",
]
