from __future__ import annotations

import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_provenance_authority as _provenance
from .detail_summary_authority import useful_event_summary

_APPLIED = False
DETAIL_COMMIT_TIMEOUT_MS = 60_000
DETAIL_CONTENT_WAIT_MS = 12_000
_DEFAULT_DETAIL_CONCURRENCY = 6
_MAX_DETAIL_CONCURRENCY = 12
_MAX_CONTEXT_STATES = 4
_MAX_CACHE_RESULTS = 2048

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

PREFETCH_DETAIL_URLS_JS = r"""
(args) => {
  const roots = [];
  const addRoot = element => {
    if (element && !roots.includes(element)) roots.push(element);
  };
  for (const element of document.querySelectorAll("[data-infoscreen-card-id]")) {
    addRoot(element);
  }
  for (const selector of args.selectors || []) {
    try {
      for (const element of document.querySelectorAll(selector)) addRoot(element);
    } catch (error) {}
  }

  const urls = [];
  const addUrl = value => {
    try {
      const url = new URL(String(value || ""), location.href).href;
      if (url && !urls.includes(url)) urls.push(url);
    } catch (error) {}
  };
  for (const root of roots) {
    if (root.matches && root.matches("a[href]")) addUrl(root.getAttribute("href"));
    for (const anchor of root.querySelectorAll("a[href]")) {
      addUrl(anchor.getAttribute("href"));
    }
  }
  return urls;
}
"""

START_DETAIL_NAVIGATION_JS = r"""
(url) => {
  setTimeout(() => {
    window.location.assign(url);
  }, 0);
  return true;
}
"""

WAIT_FOR_NAVIGATION_JS = r"""
() => location.href !== "about:blank"
"""

_FIELD_LABELS = {
    "date": {
        "date", "dates", "when", "date & time", "date and time",
        "opening hours", "opening hour", "hours",
    },
    "time": {
        "time", "times", "duration", "date & time", "date and time",
        "opening hours", "opening hour", "hours",
    },
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
    r"programmes|admission|ticket|tickets|book|advisory|closure|construction)\b",
    re.I,
)


@dataclass
class _PrefetchedDetail:
    page: Any
    requested_url: str
    status: dict[str, int | None] = field(default_factory=lambda: {"value": None})


@dataclass
class _ContextState:
    context: Any
    listing_key: str = ""
    listing_url: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    entries: dict[str, _PrefetchedDetail] = field(default_factory=dict)
    page_ids: set[int] = field(default_factory=set)
    cache: "OrderedDict[str, dict[str, str]]" = field(default_factory=OrderedDict)


_STATES: "OrderedDict[int, _ContextState]" = OrderedDict()


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

    labeled_dates = _clean_rows(payload.get("labeled_dates"))
    labeled_times = _clean_rows(payload.get("labeled_times"))
    structured_dates = _clean_rows(payload.get("structured_dates"))
    structured_times = _clean_rows(payload.get("structured_times"))
    trusted_dates = labeled_dates or structured_dates
    trusted_times = labeled_times or structured_times
    if trusted_dates or trusted_times:
        return " · ".join([*trusted_dates, *trusted_times])

    if _extract.clean(payload.get("field_authority_version")):
        return ""

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

    labeled_venues = _clean_rows(payload.get("labeled_venues"))
    structured_venues = _clean_rows(payload.get("structured_venues"))
    trusted_venues = labeled_venues or structured_venues
    if trusted_venues:
        return trusted_venues[0]

    if _extract.clean(payload.get("field_authority_version")):
        return ""

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
    authority_version = _extract.clean(merged.get("field_authority_version"))
    for key in ("dates", "venues"):
        values = _clean_rows(fallback.get(key))
        if not values:
            continue
        if authority_version:
            merged[f"fallback_{key}"] = values
        elif not _clean_rows(merged.get(key)):
            merged[key] = values
    if not _extract.clean(merged.get("summary")):
        merged["summary"] = _extract.clean(fallback.get("summary"))
    return merged


def _detail_concurrency() -> int:
    try:
        configured = int(
            os.environ.get(
                "INFOSCREEN_REVIEW_DETAIL_CONCURRENCY",
                str(_DEFAULT_DETAIL_CONCURRENCY),
            )
        )
    except ValueError:
        configured = _DEFAULT_DETAIL_CONCURRENCY
    return max(1, min(_MAX_DETAIL_CONCURRENCY, configured))


def _canonical_url(value: object) -> str:
    text = _extract.clean(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            (parsed.path or "/").rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def _close_entry(entry: _PrefetchedDetail) -> None:
    try:
        if not entry.page.is_closed():
            entry.page.close()
    except Exception:
        pass


def _close_entries(state: _ContextState) -> None:
    for entry in list(state.entries.values()):
        _close_entry(entry)
    state.entries.clear()
    state.page_ids.clear()
    state.pending.clear()


def _state(context: Any) -> _ContextState:
    key = id(context)
    existing = _STATES.get(key)
    if existing is not None and existing.context is context:
        _STATES.move_to_end(key)
        return existing
    if existing is not None:
        _close_entries(existing)

    state = _ContextState(context=context)
    _STATES[key] = state
    while len(_STATES) > _MAX_CONTEXT_STATES:
        _, stale = _STATES.popitem(last=False)
        _close_entries(stale)
    return state


def _cache_key(source: dict[str, Any], requested_url: str) -> str:
    return f"{_extract.clean(source.get('id'))}\0{_canonical_url(requested_url)}"


def _cache_get(
    state: _ContextState,
    source: dict[str, Any],
    requested_url: str,
) -> dict[str, str] | None:
    key = _cache_key(source, requested_url)
    result = state.cache.get(key)
    if result is None:
        return None
    state.cache.move_to_end(key)
    return dict(result)


def _cache_put(
    state: _ContextState,
    source: dict[str, Any],
    requested_url: str,
    result: dict[str, str],
) -> None:
    key = _cache_key(source, requested_url)
    state.cache[key] = dict(result)
    state.cache.move_to_end(key)
    while len(state.cache) > _MAX_CACHE_RESULTS:
        state.cache.popitem(last=False)


def _listing_page(
    context: Any,
    state: _ContextState,
    listing_url: str,
) -> Any | None:
    expected = _canonical_url(listing_url)
    for page in getattr(context, "pages", []):
        try:
            if (
                id(page) not in state.page_ids
                and not page.is_closed()
                and _canonical_url(page.url) == expected
            ):
                return page
        except Exception:
            continue
    return None


def _capture_main_status(entry: _PrefetchedDetail) -> None:
    page = entry.page

    def on_response(response: Any) -> None:
        try:
            if (
                response.request.resource_type == "document"
                and response.frame == page.main_frame
            ):
                entry.status["value"] = int(response.status)
        except Exception:
            return

    page.on("response", on_response)


def _start_prefetch(
    context: Any,
    state: _ContextState,
    requested_url: str,
) -> bool:
    page = context.new_page()
    entry = _PrefetchedDetail(page=page, requested_url=requested_url)
    state.entries[requested_url] = entry
    state.page_ids.add(id(page))
    try:
        _capture_main_status(entry)
        page.evaluate(START_DETAIL_NAVIGATION_JS, requested_url)
        return True
    except Exception:
        state.entries.pop(requested_url, None)
        state.page_ids.discard(id(page))
        _close_entry(entry)
        return False


def _fill_prefetch(state: _ContextState) -> None:
    context = state.context
    while state.pending and len(state.entries) < _detail_concurrency():
        requested_url = state.pending.pop(0)
        if requested_url in state.entries:
            continue
        if _cache_get(state, state.source, requested_url) is not None:
            continue
        _start_prefetch(context, state, requested_url)


def _prepare_prefetch(
    context: Any,
    state: _ContextState,
    source: dict[str, Any],
    listing_url: str,
    requested_url: str,
) -> None:
    listing_page = _listing_page(context, state, listing_url)
    if listing_page is None:
        return

    listing_key = (
        f"{_extract.clean(source.get('id'))}\0{_canonical_url(listing_url)}"
    )
    if state.listing_key != listing_key:
        _close_entries(state)
        state.listing_key = listing_key
        state.listing_url = listing_url
        state.source = dict(source)

        raw_urls = [requested_url]
        try:
            observed = listing_page.evaluate(
                PREFETCH_DETAIL_URLS_JS,
                {"selectors": source.get("card_selectors") or []},
            )
        except Exception:
            observed = []
        if isinstance(observed, list):
            raw_urls.extend(str(value or "") for value in observed)

        pending: list[str] = []
        for raw_url in raw_urls:
            canonical = _provenance.listing_detail_url(listing_url, raw_url)
            if canonical and canonical not in pending:
                pending.append(canonical)
        state.pending = pending
    elif (
        requested_url not in state.entries
        and requested_url not in state.pending
        and _cache_get(state, source, requested_url) is None
    ):
        state.pending.insert(0, requested_url)
    elif requested_url in state.pending:
        state.pending.remove(requested_url)
        state.pending.insert(0, requested_url)

    _fill_prefetch(state)


def _take_prefetched(
    state: _ContextState,
    requested_url: str,
) -> _PrefetchedDetail | None:
    return state.entries.pop(requested_url, None)


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


def _read_detail_page(
    page: Any,
    listing_url: str,
    requested_url: str,
    entry: _PrefetchedDetail | None,
) -> dict[str, str]:
    if entry is None:
        response = page.goto(
            requested_url,
            wait_until="commit",
            timeout=DETAIL_COMMIT_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            raise ValueError(f"detail_http_status_{response.status}")
    else:
        try:
            page.wait_for_function(
                WAIT_FOR_NAVIGATION_JS,
                timeout=DETAIL_COMMIT_TIMEOUT_MS,
            )
        except Exception:
            if str(page.url or "") == "about:blank":
                raise
        status = entry.status.get("value")
        if status is not None and status >= 400:
            raise ValueError(f"detail_http_status_{status}")

    try:
        page.wait_for_function(DETAIL_READY_JS, timeout=DETAIL_CONTENT_WAIT_MS)
    except Exception:
        pass
    page.wait_for_timeout(150)

    final_url = _provenance.listing_detail_url(listing_url, str(page.url))
    if not final_url:
        final_url = requested_url

    payload = page.evaluate(_browser.DETAIL_CARD_JS) or {}
    if not isinstance(payload, dict):
        payload = {}
    if not payload.get("dates") or not payload.get("venues") or not payload.get("summary"):
        fallback = page.evaluate(FALLBACK_DETAIL_FIELDS_JS) or {}
        if isinstance(fallback, dict):
            payload = _merge_fallback_fields(payload, fallback)

    title = _extract.clean(payload.get("title") or page.title() or "")
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
        "detail_page_title": _extract.clean(payload.get("title") or page.title() or ""),
    }


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Read exact detail fields with bounded parallel navigation and URL caching."""

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

    state = _state(context)
    cached = _cache_get(state, source, requested_url)
    if cached is not None:
        return cached

    _prepare_prefetch(context, state, source, listing_url, requested_url)
    entry = _take_prefetched(state, requested_url)
    page = entry.page if entry is not None else context.new_page()

    try:
        result = _read_detail_page(
            page,
            listing_url,
            requested_url,
            entry,
        )
        _cache_put(state, source, requested_url, result)
        return result
    finally:
        try:
            if not page.is_closed():
                page.close()
        finally:
            state.page_ids.discard(id(page))
            if entry is not None:
                _fill_prefetch(state)


def apply() -> None:
    """Install exact-field collection with bounded detail-page concurrency."""

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
    "PREFETCH_DETAIL_URLS_JS",
    "START_DETAIL_NAVIGATION_JS",
    "WAIT_FOR_NAVIGATION_JS",
    "apply",
    "_detail_candidate",
    "_detail_concurrency",
    "_listing_candidate_if_complete",
    "_prepare_prefetch",
    "_raw_summary",
    "_raw_when",
    "_raw_where",
    "_state",
    "_unlabelled_schedule_line",
    "_unlabelled_venue_line",
]
