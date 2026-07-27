from __future__ import annotations

import re
from typing import Any

from . import detail_date_authority as _detail_dates
from . import event_review as _review
from . import extract as _extract
from . import review_detail_navigation_authority as _detail_navigation

_APPLIED = False
_BASE_DETAIL_CANDIDATE = None
_BASE_LOAD = None
_BASE_STATE_PAYLOAD = None
_BASE_REPLACE_EVENTS = None
_BASE_RAW_WHEN = None

_DATE_NOISE_RE = re.compile(
    r"\b(?:last updated|updated on|page updated|copyright|privacy|cookie|"
    r"newsletter|presale|pre-sale|ticket sale|registration opens?|"
    r"previous programme|next programme|previous event|next event)\b",
    re.I,
)

DETAIL_STABLE_READY_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const root = document.querySelector("main") ||
    document.querySelector("article") || document.body;
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || ""));
  if (!root || !heading) return false;

  const text = clean(root.innerText || root.textContent || "");
  if (text.length < 120) return false;

  const dateLike = /(?:\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?(?:\s*(?:,|&|\/|[-–—])\s*\d{1,2}(?:st|nd|rd|th)?)*\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+20\d{2}\b)/i;
  if (dateLike.test(text) || document.querySelector(
    "time[datetime], [itemprop='startDate'], [itemprop='endDate'], " +
    "[data-start-date], [data-end-date], [data-date]"
  )) return true;

  const signature = `${location.href}\u0000${text.slice(0, 6000)}`;
  const now = Date.now();
  const previous = window.__infoscreenDetailReadyState;
  if (!previous || previous.signature !== signature) {
    window.__infoscreenDetailReadyState = {signature, since: now};
    return false;
  }
  return document.readyState === "complete" && now - previous.since >= 1200;
}
"""

DETAIL_DOCUMENT_FACTS_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const key = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const add = (rows, value) => {
    const text = clean(value);
    if (text && !rows.includes(text)) rows.push(text);
  };
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event|presale|pre-sale|ticket sale|registration opens?)\b/i.test(clean(value));
  const boundary = value => /^(?:you might also like|related (?:events?|programmes?|programs?|activities?)|recommended for you|more from|explore more|previous programme|next programme|previous event|next event|visit .+ today)$/i.test(clean(value));
  const dateLike = value => /(?:\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?(?:\s*(?:,|&|\/|[-–—])\s*\d{1,2}(?:st|nd|rd|th)?)*\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+20\d{2}\b)/i.test(clean(value));
  const timeLike = value => /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b|\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)?\s*[-–—]\s*\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i.test(clean(value));
  const venueLike = value => /\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|auditorium|foyer|atrium|courtyard|plaza|studio|park|gardens?|zoo|centre|center)\b/i.test(clean(value));

  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(element => clean(element.innerText || element.textContent || "")) || null;
  const title = clean(heading ? (heading.innerText || heading.textContent) : "");
  const titleKey = key(title);
  const main = heading && heading.closest("main");
  const root = main || document.querySelector("main") ||
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
    for (const attribute of ["datetime", "content", "data-date", "data-start-date", "data-end-date"] ) {
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
    """Return the collected Review fields unchanged.

    Runtime snapshots, listing cards, parser reconstruction, and source defaults must
    not overwrite title, when, where, or summary returned by the detail collector.
    """

    return dict(raw)


def _line_dates(value: object) -> list[Any]:
    text = _extract.clean(value)
    if not text:
        return []
    try:
        return list(_detail_dates._activity_label_dates(text))
    except Exception:
        return list(_extract.label_dates(text))


def _detail_date_line(payload: dict[str, Any]) -> str:
    """Return one exact date-bearing detail line, without rewriting its text."""

    rows: list[object] = []
    raw_dates = payload.get("dates")
    if isinstance(raw_dates, list):
        rows.extend(raw_dates)
    rows.extend(_detail_navigation._payload_lines(payload))

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
        if _line_dates(text):
            return text
    return ""


def _raw_when(payload: dict[str, Any]) -> str:
    """Preserve separate detail Date and Time rows in one exact display value."""

    base = _extract.clean(_BASE_RAW_WHEN(payload))
    if _line_dates(base):
        return base

    date_line = _detail_date_line(payload)
    if not date_line:
        return base

    if base and base != date_line:
        return f"{date_line} · {base}"

    for line in _detail_navigation._payload_lines(payload):
        text = _extract.clean(line)
        if (
            text
            and text != date_line
            and not _line_dates(text)
            and _detail_navigation._UNLABELLED_TIME_RE.search(text)
        ):
            return f"{date_line} · {text}"
    return date_line


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Preserve the exact result returned by the active detail collector."""

    result = dict(
        _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )
    )
    return {
        key: str(value or "") if key != "status" else value
        for key, value in result.items()
    }


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
    """Load exact persisted fields and hide only candidates that are already past."""

    state = _BASE_LOAD(store)
    state.events, state.event_collection = _active_candidates(
        list(state.events),
        state.event_collection,
    )
    return state


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Expose exact persisted fields; do not backfill them from another runtime."""

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
    """Persist exact collected fields and exclude already-ended candidates."""

    active, metadata = _active_candidates(list(candidates), collection)
    return _BASE_REPLACE_EVENTS(store, active, metadata)


def apply() -> None:
    """Install final exact-field and lifecycle handling for Review Web output."""

    global _APPLIED, _BASE_DETAIL_CANDIDATE, _BASE_LOAD
    global _BASE_STATE_PAYLOAD, _BASE_REPLACE_EVENTS, _BASE_RAW_WHEN
    if _APPLIED:
        return

    _detail_navigation.DETAIL_READY_JS = DETAIL_STABLE_READY_JS
    _detail_navigation.FALLBACK_DETAIL_FIELDS_JS = DETAIL_DOCUMENT_FACTS_JS
    _BASE_RAW_WHEN = _detail_navigation._raw_when
    _detail_navigation._raw_when = _raw_when

    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _BASE_LOAD = _review.EventReviewStore.load
    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events

    _review._detail_candidate = _detail_candidate
    _review.EventReviewStore.load = load
    _review.EventReviewStore.state_payload = state_payload
    _review.EventReviewStore.replace_events = replace_events
    _APPLIED = True


__all__ = [
    "DETAIL_DOCUMENT_FACTS_JS",
    "DETAIL_STABLE_READY_JS",
    "apply",
    "load",
    "replace_events",
    "state_payload",
    "_detail_candidate",
    "_detail_date_line",
    "_expired",
    "_raw_when",
    "_repair_fields",
]
