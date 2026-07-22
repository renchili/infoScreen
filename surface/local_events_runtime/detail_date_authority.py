from __future__ import annotations

import re
from typing import Any

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds
from . import source_overrides

_applied = False
_BASE_LABEL_DATES = _extract.label_dates
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

# Extract only the activity body. Site metadata such as "Last Updated", related
# cards, footer dates, copyright years, and previous/next navigation must never
# compete with the Event's own date and venue.
ACTIVITY_DETAIL_JS = r"""
() => {
  const oneLine = value => String(value || "").replace(/\s+/g, " ").trim();
  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
  const dateOnly = value => /^(?:\d{1,2}\s*(?:&|and|[-–—]|to)\s*)?\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}$|^20\d{2}-\d{1,2}-\d{1,2}$/i.test(oneLine(value));
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event)\b/i.test(value);
  const boundary = value => /^(related (?:events?|programmes?|programs?|activities?)|you may also like|more from|explore more|recommended for you)$/i.test(value);
  const add = (out, value) => {
    const text = oneLine(value);
    if (text && !out.includes(text)) out.push(text);
  };

  const structured = [];
  const visit = (value, depth = 0) => {
    if (!value || typeof value !== "object" || depth > 10) return;
    if (Array.isArray(value)) {
      value.forEach(item => visit(item, depth + 1));
      return;
    }
    const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"] || value.type];
    if (types.some(item => /(^|:)event$/i.test(String(item || "")))) {
      add(structured, value.name || value.headline || value.title);
      const start = oneLine(value.startDate || value.start || "");
      const end = oneLine(value.endDate || value.end || "");
      add(structured, start && end && start !== end ? `${start} - ${end}` : (start || end));
      const location = value.location || value.venue || value.place;
      if (typeof location === "string") {
        add(structured, location);
      } else if (location && typeof location === "object") {
        add(structured, location.name || location.title);
        const address = location.address;
        if (typeof address === "string") add(structured, address);
        else if (address && typeof address === "object") {
          add(structured, [address.streetAddress, address.addressLocality, address.postalCode].filter(Boolean).join(", "));
        }
      }
      add(structured, value.description || value.summary);
    }
    Object.values(value).forEach(child => visit(child, depth + 1));
  };
  for (const script of document.querySelectorAll('script[type*="ld+json" i]')) {
    try { visit(JSON.parse(script.textContent || "")); } catch (error) {}
  }

  const root = document.querySelector("main") || document.querySelector("article") || document.body;
  const rawLines = String(root ? (root.innerText || root.textContent || "") : "").split(/\n+/);
  const body = [];
  let skipFollowingDate = false;
  for (const raw of rawLines) {
    const line = oneLine(raw);
    if (!line) continue;
    if (boundary(line) && body.length >= 3) break;
    if (rejected(line)) {
      skipFollowingDate = true;
      continue;
    }
    if (skipFollowingDate && dateOnly(line)) {
      skipFollowingDate = false;
      continue;
    }
    skipFollowingDate = false;
    add(body, line);
    if (body.length >= 180) break;
  }

  const headings = Array.from(document.querySelectorAll("main h1, main h2, article h1, article h2, h1, h2"))
    .filter(visible)
    .map(element => oneLine(element.innerText || element.textContent || ""))
    .filter(value => value && !rejected(value) && !boundary(value))
    .slice(0, 8);
  const imageAlts = Array.from(document.querySelectorAll("main img[alt], article img[alt], img[alt]"))
    .filter(visible)
    .map(image => oneLine(image.getAttribute("alt")))
    .filter(Boolean)
    .slice(0, 8);
  const lines = [...structured, ...body].filter((value, index, all) => all.indexOf(value) === index);
  return {
    text: lines.join("\n"),
    text_lines: lines,
    headings,
    image_alts: imageAlts,
    title: headings[0] || structured[0] || ""
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
    """Return Event date fragments without deciding whether the Event is current.

    Parsing and lifecycle filtering are separate responsibilities. Discarding past
    dates during parsing allowed unrelated current metadata such as "Last Updated"
    to replace the real historical Event range.
    """

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


def _listing_card_without_listing_date(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    """Admit an isolated official list card before reading its detail-page date.

    A listing page proves activity membership through one official detail link and
    a usable title. The listing itself is not required to repeat date or venue
    fields; those fields remain mandatory only after detail-page enrichment.
    """

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
    """Merge detail evidence without overwriting correct official-list fields."""

    listing = _listing_fields(source, card)
    merged = dict(detail)
    merged["title"] = listing["title"] or _extract.clean(detail.get("title"))
    # The isolated official listing card is the closest evidence to membership and
    # date. A detail page may fill a missing date, but metadata cannot replace one.
    merged["when"] = listing["when"] or _extract.clean(detail.get("when"))
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
    """Install shared listing/detail date and lifecycle authority."""

    global _applied
    global _BASE_DETAIL_CANDIDATE, _BASE_REVIEW_LOAD, _BASE_REPLACE_EVENTS
    global _BASE_SET_EVENT_DECISION
    if _applied:
        return

    source_overrides.apply()

    # Source overrides previously discarded a rendered list card before opening
    # its official detail page when the list card did not repeat a date.
    _browser.CARD_JS = _browser.CARD_JS.replace(
        '    if (!hasDateText(textLines(card).join(" "))) continue;\n',
        "",
    )
    _browser.DETAIL_CARD_JS = ACTIVITY_DETAIL_JS
    source_overrides._listing_card = _listing_card_without_listing_date

    # Esplanade and other official listings use forms such as "12 & 13 Jun 2026".
    # Parsing must retain past ranges as evidence; output/review lifecycle code then
    # decides whether the Event is still active.
    _extract.MULTI_DAY_SAME_MONTH_RE = MULTI_DAY_SAME_MONTH_RE
    _extract.ISO_RANGE_RE = ISO_RANGE_RE
    _extract.label_dates = _activity_label_dates
    _extract.date_fragments = _activity_date_fragments

    # Import after parser and DETAIL_CARD_JS changes so Event Review binds the same
    # authorities as the formal collector.
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
    "_candidate_expired",
    "_listing_card_without_listing_date",
    "_merge_detail_fields",
]
