from __future__ import annotations

import re
from typing import Any

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds
from . import source_overrides

_applied = False
_BASE_LABEL_DATES = _extract.label_dates
_BASE_PICK_WHEN = _extract.pick_when
_BASE_PICK_VENUE = _extract.pick_venue
_BASE_DETAIL_CANDIDATE = None
_BASE_REVIEW_LOAD = None
_BASE_REPLACE_EVENTS = None
_BASE_SET_EVENT_DECISION = None

MULTI_DAY_SAME_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}})\s*(?:&|and)\s*(\d{{1,2}})\s+({_extract.MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b",
    re.I,
)
ISO_RANGE_RE = re.compile(
    rf"\b(20\d{{2}}-\d{{1,2}}-\d{{1,2}})\s*{_extract.SEP}\s*(20\d{{2}}-\d{{1,2}}-\d{{1,2}})\b",
    re.I,
)
_WHEN_INLINE_RE = re.compile(r"^(?:event\s+)?(?:date|dates|when)\s*[:\-]\s*(.+)$", re.I)
_WHEN_LABEL_RE = re.compile(r"^(?:event\s+)?(?:date|dates|when)\s*:?[\s]*$", re.I)
_VENUE_INLINE_RE = re.compile(r"^(?:location|venue|where)\s*[:\-]\s*(.+)$", re.I)
_VENUE_LABEL_RE = re.compile(r"^(?:location|venue|where)\s*:?[\s]*$", re.I)
_FIELD_LABEL_RE = re.compile(
    r"^(?:event\s+)?(?:date|dates|when|location|venue|where|time|event\s+time|doors\s+open|language|promoter|price|prices|ticket\s+prices?)\s*:?[\s]*$",
    re.I,
)
_NON_EVENT_DATE_CONTEXT_RE = re.compile(
    r"\b(?:road\s+closure|closure\s+notice|traffic\s+notice|notice|presale|pre-sale|general\s+sale|ticket\s+sale|registration|doors\s+open|event\s+time|last\s+updated|updated\s+on|copyright)\b",
    re.I,
)

# Extract one activity document, not the complete site shell. The primary Event h1
# is the start boundary and recommendation/footer headings are end boundaries. The
# returned payload satisfies both browser.merge_detail_payload() and the formal
# collector's source_overrides._merge_detail() contract.
ACTIVITY_DETAIL_JS = r"""
() => {
  const oneLine = value => String(value || "").replace(/\s+/g, " ").trim();
  const key = value => oneLine(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event)\b/i.test(value);
  const boundary = value => /^(related (?:events?|programmes?|programs?|activities?)|you may also like|more from|explore more|recommended for you|plan your visit)$/i.test(value);
  const dateLabel = value => /^(?:event\s+)?(?:date|dates|when)\s*:?$/i.test(value);
  const venueLabel = value => /^(?:location|venue|where)\s*:?$/i.test(value);
  const add = (out, value) => {
    const text = oneLine(value);
    if (text && !out.includes(text)) out.push(text);
  };

  const primaryHeading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(visible) || null;
  const primaryTitle = oneLine(primaryHeading ? (primaryHeading.innerText || primaryHeading.textContent) : "");
  const root = primaryHeading && primaryHeading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") || document.body;

  const eventObjects = [];
  const visit = (value, depth = 0) => {
    if (!value || typeof value !== "object" || depth > 10 || eventObjects.length >= 40) return;
    if (Array.isArray(value)) {
      value.forEach(item => visit(item, depth + 1));
      return;
    }
    const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"] || value.type];
    if (types.some(item => /(^|:)event$/i.test(String(item || "")))) eventObjects.push(value);
    Object.values(value).forEach(child => visit(child, depth + 1));
  };
  for (const script of document.querySelectorAll('script[type*="ld+json" i]')) {
    try { visit(JSON.parse(script.textContent || "")); } catch (error) {}
  }

  const titleKey = key(primaryTitle);
  const matchingEvents = eventObjects.filter(event => {
    const eventKey = key(event.name || event.headline || event.title || "");
    return Boolean(eventKey && titleKey && (
      eventKey === titleKey || eventKey.includes(titleKey) || titleKey.includes(eventKey)
    ));
  });
  const primaryEvent = matchingEvents[0] || (eventObjects.length === 1 ? eventObjects[0] : null);

  const structuredLines = [];
  if (primaryEvent) {
    add(structuredLines, primaryEvent.name || primaryEvent.headline || primaryEvent.title);
    const start = oneLine(primaryEvent.startDate || primaryEvent.start || "");
    const end = oneLine(primaryEvent.endDate || primaryEvent.end || "");
    add(structuredLines, start && end && start !== end ? `${start} - ${end}` : (start || end));
    const location = primaryEvent.location || primaryEvent.venue || primaryEvent.place;
    if (typeof location === "string") {
      add(structuredLines, location);
    } else if (location && typeof location === "object") {
      add(structuredLines, location.name || location.title);
      const address = location.address;
      if (typeof address === "string") add(structuredLines, address);
      else if (address && typeof address === "object") {
        add(structuredLines, [address.streetAddress, address.addressLocality, address.postalCode].filter(Boolean).join(", "));
      }
    }
    add(structuredLines, primaryEvent.description || primaryEvent.summary);
  }

  const rawLines = String(root ? (root.innerText || root.textContent || "") : "")
    .split(/\n+/).map(oneLine).filter(Boolean);
  const body = [];
  const dates = [];
  const venues = [];
  let started = !primaryTitle;
  let skipFollowingDate = false;

  for (let index = 0; index < rawLines.length; index += 1) {
    const line = rawLines[index];
    if (!started) {
      const lineKey = key(line);
      if (lineKey === titleKey || lineKey.includes(titleKey) || titleKey.includes(lineKey)) {
        started = true;
      } else {
        continue;
      }
    }
    if (boundary(line) && body.length >= 3) break;
    if (rejected(line)) {
      skipFollowingDate = true;
      continue;
    }
    if (skipFollowingDate) {
      skipFollowingDate = false;
      continue;
    }
    add(body, line);

    if (dateLabel(line)) {
      for (const candidate of rawLines.slice(index + 1, index + 4)) {
        if (dateLabel(candidate) || venueLabel(candidate)) break;
        if (!rejected(candidate)) {
          add(dates, candidate);
          break;
        }
      }
    }
    if (venueLabel(line)) {
      for (const candidate of rawLines.slice(index + 1, index + 4)) {
        if (dateLabel(candidate) || venueLabel(candidate)) break;
        if (!rejected(candidate)) {
          add(venues, candidate);
          break;
        }
      }
    }
    if (body.length >= 220) break;
  }

  if (primaryEvent) {
    const start = oneLine(primaryEvent.startDate || primaryEvent.start || "");
    const end = oneLine(primaryEvent.endDate || primaryEvent.end || "");
    add(dates, start && end && start !== end ? `${start} - ${end}` : (start || end));
    const location = primaryEvent.location || primaryEvent.venue || primaryEvent.place;
    if (typeof location === "string") add(venues, location);
    else if (location && typeof location === "object") add(venues, location.name || location.title);
  }

  const headings = Array.from(root ? root.querySelectorAll("h1, h2") : [])
    .filter(visible)
    .map(element => oneLine(element.innerText || element.textContent || ""))
    .filter(value => value && !rejected(value) && !boundary(value))
    .slice(0, 8);
  const imageAlts = Array.from(root ? root.querySelectorAll("img[alt]") : [])
    .filter(visible)
    .map(image => oneLine(image.getAttribute("alt")))
    .filter(Boolean)
    .slice(0, 8);
  const lines = [...structuredLines, ...body]
    .filter((value, index, all) => all.indexOf(value) === index);
  const summary = oneLine(document.querySelector('meta[name="description"]')?.content) ||
    oneLine(document.querySelector('meta[property="og:description"]')?.content);

  return {
    canonical: document.querySelector('link[rel="canonical"]')?.href || location.href,
    title: primaryTitle || headings[0] || oneLine(document.title),
    eventObjects: primaryEvent ? [primaryEvent] : [],
    dates,
    venues,
    lines,
    summary,
    text: lines.join("\n"),
    text_lines: lines,
    headings: primaryTitle ? [primaryTitle, ...headings.filter(value => value !== primaryTitle)] : headings,
    image_alts: imageAlts
  };
}
"""


def _activity_label_dates(label: str):
    """Expand all supported Event date forms into concrete dates."""

    dates = list(_BASE_LABEL_DATES(label))
    text = _extract.clean(label)
    years = [int(value) for value in re.findall(r"\b(20\d{2})\b", text)]
    inherited_year = years[-1] if years else _extract.TODAY.year
    for first_day, second_day, month_name, explicit_year in MULTI_DAY_SAME_MONTH_RE.findall(text):
        year = explicit_year or inherited_year
        for day in (first_day, second_day):
            parsed = _extract.parse_date(day, month_name, year)
            if parsed and parsed not in dates:
                dates.append(parsed)
    return sorted(dates)


def _activity_date_fragments(text: str) -> list[str]:
    """Return Event date fragments without deciding whether the Event is current."""

    found: list[tuple[int, int, str]] = []
    patterns = [
        ISO_RANGE_RE,
        _extract.FULL_RANGE_RE,
        _extract.END_YEAR_RANGE_RE,
        MULTI_DAY_SAME_MONTH_RE,
        _extract.SAME_MONTH_RANGE_RE,
        _extract.MONTH_FIRST_RANGE_RE,
        _extract.ISO_DATE_RE,
        _extract.TEXT_DATE_RE,
        _extract.MONTH_FIRST_DATE_RE,
    ]
    for priority, pattern in enumerate(patterns):
        for match in pattern.finditer(text):
            fragment = _extract.clean(match.group(0))
            if not fragment or not _extract.label_dates(fragment):
                continue
            found.append((priority, match.start(), fragment))

    unique: list[str] = []
    for _, _, fragment in sorted(found, key=lambda item: (item[0], item[1], -len(item[2]))):
        if any(fragment != existing and fragment in existing for existing in unique):
            continue
        if fragment not in unique:
            unique.append(fragment)
    return unique


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        return [_extract.clean(item) for item in raw if _extract.clean(item)]
    return _extract.lines(card.get("text") or "")


def _activity_pick_when(card: dict[str, Any]) -> tuple[str, str]:
    """Prefer the value attached to the Event's explicit Date/When label."""

    lines = _card_lines(card)
    for index, line in enumerate(lines):
        inline = _WHEN_INLINE_RE.fullmatch(line)
        if inline:
            value = _extract.clean(inline.group(1))
            if _extract.label_dates(value):
                return _extract.short(value, 180), line
        if _WHEN_LABEL_RE.fullmatch(line):
            for candidate in lines[index + 1:index + 5]:
                if _FIELD_LABEL_RE.fullmatch(candidate):
                    break
                if _extract.label_dates(candidate):
                    return _extract.short(candidate, 180), line

    scored: list[tuple[int, int, str, str]] = []
    for index, line in enumerate(lines):
        windows = [line]
        if index + 1 < len(lines):
            windows.append(" ".join(lines[index:index + 2]))
        if index + 2 < len(lines):
            windows.append(" ".join(lines[index:index + 3]))
        for window in windows:
            if _NON_EVENT_DATE_CONTEXT_RE.search(window):
                continue
            for fragment in _activity_date_fragments(window):
                score = _extract.score_when(fragment, window)
                if len(_extract.label_dates(fragment)) >= 2:
                    score += 100
                scored.append((score, -index, fragment, window))
    if scored:
        scored.sort(key=lambda item: (-item[0], -item[1], len(item[2])))
        _, _, fragment, source_line = scored[0]
        return _extract.short(fragment, 180), source_line
    return _BASE_PICK_WHEN(card)


def _valid_labeled_venue(value: str) -> bool:
    text = _extract.clean(value)
    if not text or len(text) > 180 or len(text.split()) > 24:
        return False
    if _FIELD_LABEL_RE.fullmatch(text):
        return False
    if _extract.DATE_LINE_RE.search(text) or _extract.TIME_RE.fullmatch(text):
        return False
    return not _NON_EVENT_DATE_CONTEXT_RE.search(text)


def _activity_pick_venue(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    when_line: str,
) -> str:
    """Prefer the value attached to an explicit Location/Venue/Where label."""

    lines = _card_lines(card)
    for index, line in enumerate(lines):
        inline = _VENUE_INLINE_RE.fullmatch(line)
        if inline:
            value = _extract.clean(inline.group(1))
            if _valid_labeled_venue(value):
                return value
        if _VENUE_LABEL_RE.fullmatch(line):
            for candidate in lines[index + 1:index + 5]:
                if _FIELD_LABEL_RE.fullmatch(candidate):
                    break
                if _valid_labeled_venue(candidate):
                    return candidate
    return _BASE_PICK_VENUE(source, card, when, when_line)


def _listing_card_without_listing_date(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    """Admit an isolated official list card before reading its detail-page date."""

    mode = _extract.clean(card.get("extraction_mode"))
    if mode not in {"detail_link", "nhb_dom_card"}:
        return None
    if int(card.get("detail_url_count") or 0) != 1:
        return None
    if not _official_feeds.card_title(card):
        return None

    canonical = source_overrides._candidate_url(source, card)
    if not canonical:
        return None

    admitted = dict(card)
    admitted.update(
        url=canonical,
        page_url=canonical,
        listing_evidence=source_overrides.LISTING_EVIDENCE,
        listing_url=listing_url,
        listing_card_id=_extract.clean(card.get("id")),
        listing_extraction_mode=mode,
    )
    return admitted


def _listing_fields(source: dict[str, Any], card: dict[str, Any]) -> dict[str, str]:
    title = _extract.pick_title(card) or _official_feeds.card_title(card)
    when, when_line = _extract.pick_when(card)
    where = _extract.pick_venue(source, card, when, when_line)
    summary = _extract.pick_summary(card, title, when, where)
    return {
        "title": _extract.clean(title),
        "when": _extract.clean(when),
        "where": _extract.clean(where),
        "summary": _extract.clean(summary),
    }


def _merge_detail_fields(
    source: dict[str, Any],
    card: dict[str, Any],
    detail: dict[str, str],
) -> dict[str, str]:
    """Use labeled detail fields first and retain list-card values as fallback."""

    listing = _listing_fields(source, card)
    merged = dict(detail)
    merged["title"] = _extract.clean(detail.get("title")) or listing["title"]
    merged["when"] = _extract.clean(detail.get("when")) or listing["when"]
    detail_where = _extract.clean(detail.get("where"))
    source_default = _extract.clean(source.get("default_venue") or source.get("name"))
    merged["where"] = detail_where or listing["where"] or source_default
    merged["summary"] = _extract.clean(detail.get("summary")) or listing["summary"]
    return merged


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Read a detail page while preserving fields already present on its list card."""

    try:
        detail = _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )
    except Exception as exc:
        listing = _listing_fields(source, card)
        return {
            "detail_url": raw_url,
            **listing,
            "detail_status": "incomplete" if listing["title"] else "failed",
            "detail_error": f"{type(exc).__name__}: {exc}"[:500],
            "detail_page_title": "",
        }
    return _merge_detail_fields(source, card, detail)


def _candidate_expired(candidate: Any) -> bool:
    dates = _extract.label_dates(getattr(candidate, "when", ""))
    return bool(dates and max(dates) < _extract.TODAY)


def _review_load(store: Any):
    state = _BASE_REVIEW_LOAD(store)
    state.events = [candidate for candidate in state.events if not _candidate_expired(candidate)]
    return state


def _replace_events(store: Any, candidates: list[Any], collection: dict[str, Any]):
    active = [candidate for candidate in candidates if not _candidate_expired(candidate)]
    expired = len(candidates) - len(active)
    metadata = dict(collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = expired
    return _BASE_REPLACE_EVENTS(store, active, metadata)


def _set_event_decision(store: Any, candidate_id: str, decision: str):
    if decision == "confirmed":
        state = _review_load(store)
        match = next(
            (candidate for candidate in state.events if candidate.candidate_id == candidate_id),
            None,
        )
        if match is None:
            raise ValueError("event candidate not found or has already ended")
    return _BASE_SET_EVENT_DECISION(store, candidate_id, decision)


def apply() -> None:
    """Install shared listing/detail field and lifecycle authority."""

    global _applied
    global _BASE_DETAIL_CANDIDATE, _BASE_REVIEW_LOAD, _BASE_REPLACE_EVENTS
    global _BASE_SET_EVENT_DECISION
    if _applied:
        return

    source_overrides.apply()

    _browser.CARD_JS = _browser.CARD_JS.replace(
        '    if (!hasDateText(textLines(card).join(" "))) continue;\n',
        "",
    )
    _browser.DETAIL_CARD_JS = ACTIVITY_DETAIL_JS
    source_overrides.AUTHORITATIVE_DETAIL_JS = ACTIVITY_DETAIL_JS
    source_overrides._listing_card = _listing_card_without_listing_date

    _extract.MULTI_DAY_SAME_MONTH_RE = MULTI_DAY_SAME_MONTH_RE
    _extract.ISO_RANGE_RE = ISO_RANGE_RE
    _extract.label_dates = _activity_label_dates
    _extract.date_fragments = _activity_date_fragments
    _extract.pick_when = _activity_pick_when
    _extract.pick_venue = _activity_pick_venue

    from . import event_review as _review

    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _BASE_REVIEW_LOAD = _review.EventReviewStore.load
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events
    _BASE_SET_EVENT_DECISION = _review.EventReviewStore.set_event_decision
    _review._detail_candidate = _detail_candidate
    _review.EventReviewStore.load = _review_load
    _review.EventReviewStore.replace_events = _replace_events
    _review.EventReviewStore.set_event_decision = _set_event_decision
    _applied = True


__all__ = [
    "ACTIVITY_DETAIL_JS",
    "MULTI_DAY_SAME_MONTH_RE",
    "apply",
    "_activity_date_fragments",
    "_activity_label_dates",
    "_activity_pick_venue",
    "_activity_pick_when",
    "_candidate_expired",
    "_listing_card_without_listing_date",
    "_merge_detail_fields",
]
