from __future__ import annotations

import re
from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_membership_authority as _membership
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_CANDIDATE_EXPIRED = None
_BASE_EXPLICIT_VENUE = None
_ACM_PARENT_FIELDS_MARKER = "infoscreen_acm_parent_fields_v1"

_VENUE_HINT_RE = re.compile(
    r"\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|"
    r"auditorium|atrium|foyer|lobby|library|centre|center|park|gardens?|zoo)\b",
    re.I,
)
_NON_VENUE_RE = re.compile(
    r"^(?:admission|ticket|tickets|free|paid|book|register|programme|program|"
    r"event|events|exhibition|exhibitions|terms?|conditions?|last updated)\b",
    re.I,
)


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        return [_extract.clean(value) for value in raw if _extract.clean(value)]
    return _extract.lines(card.get("text") or "")


def explicit_venue(card: dict[str, Any]) -> str:
    """Recognise an unlabelled venue line in an official detail document."""

    venue = _BASE_EXPLICIT_VENUE(card)
    if venue:
        return venue

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(_card_lines(card)):
        if not line or len(line) > 180 or len(line.split()) > 24:
            continue
        if _NON_VENUE_RE.search(line):
            continue
        if _extract.DATE_LINE_RE.search(line) or _extract.TIME_RE.fullmatch(line):
            continue
        if not _VENUE_HINT_RE.search(line):
            continue

        score = 0
        if re.search(r"\bmuseum\b", line, re.I):
            score += 200
        if re.search(r"\b(?:gallery|galleries)\b", line, re.I):
            score += 100
        if re.search(r"\blevel\s+\d+\b", line, re.I):
            score += 80
        if re.search(r"\b\d{5,6}\b", line):
            score += 50
        score -= min(index, 50)
        candidates.append((score, -len(line), line))

    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def candidate_expired(candidate: Any) -> bool:
    """Never expire an explicit ongoing/start-only schedule by its start date."""

    when = _extract.clean(getattr(candidate, "when", ""))
    if when and _extract.current_date_label(when):
        return False
    return bool(_BASE_CANDIDATE_EXPIRED(candidate))


def _wrap_acm_parent_fields(script: str) -> str:
    """Select ACM's parent Date, Time, and Location rows before child programmes."""

    if _ACM_PARENT_FIELDS_MARKER in script:
        return script

    return (
        "() => {\n"
        f"  const base = ({script})();\n"
        r'''
  const infoscreen_acm_parent_fields_v1 = true;
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const host = String(location.hostname || "").replace(/^www\./i, "").toLowerCase();
  const path = String(location.pathname || "");
  const isAcm = host === "acm.nhb.gov.sg" ||
    (host === "nhb.gov.sg" && /^\/acm\/whats-on\//i.test(path));
  if (!isAcm) return base;

  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(visible) || null;
  if (!heading) return base;

  const root = heading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") || document.body;
  const headingRect = heading.getBoundingClientRect();

  const month = "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|" +
    "jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|" +
    "nov(?:ember)?|dec(?:ember)?)";
  const dateRe = new RegExp(
    "(?:\\b\\d{1,2}\\s*(?:[-–—]\\s*\\d{1,2}\\s*)?" + month +
    "\\s+20\\d{2}\\b|\\b" + month +
    "\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,)?\\s+20\\d{2}\\b|" +
    "\\b20\\d{2}-\\d{1,2}-\\d{1,2}\\b)",
    "i"
  );
  const timeRe = /\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i;
  const recurrenceRe = /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b/i;
  const ticketRe = /\b(?:free|admission|ticket|tickets|fees?|charges?|pricing|price|\$)\b/i;
  const narrativeRe = /\b(?:explore|experience|discover|join|learn|enjoy|featuring|presented|step into)\b/i;
  const venueRe = /\b(?:asian civilisations museum|museum|gallery|level|room|hall|foyer|green|hardcourt|courtyard|plaza|studio)\b/i;

  const rows = [];
  const seen = new Set();
  for (const element of root.querySelectorAll("div,li,p,span")) {
    if (!visible(element)) continue;
    const rect = element.getBoundingClientRect();
    if (rect.top < headingRect.bottom - 8 || rect.top > headingRect.bottom + 1100) continue;
    if (rect.height > 180 || rect.width < 40) continue;

    const text = clean(element.innerText || element.textContent || "");
    if (!text || text.length > 180 || text.split(/\s+/).length > 30) continue;
    const repeatedByChild = Array.from(element.children || []).some(child =>
      visible(child) && clean(child.innerText || child.textContent || "") === text
    );
    if (repeatedByChild) continue;

    const key = `${text}\u0000${Math.round(rect.top / 3)}\u0000${Math.round(rect.left / 3)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({text, top: rect.top, left: rect.left, area: rect.width * rect.height});
  }
  rows.sort((left, right) => left.top - right.top || left.left - right.left || left.area - right.area);

  const dates = rows.filter(row => dateRe.test(row.text));
  const date = dates[0] || null;
  if (!date) return base;

  const times = rows.filter(row =>
    row.top >= date.top - 6 && row.top - date.top <= 320 &&
    timeRe.test(row.text) && (recurrenceRe.test(row.text) || /[\/,&]/.test(row.text))
  );
  const time = times[0] || null;
  if (!time) return base;

  const venues = rows.filter(row =>
    row.top >= time.top - 6 && row.top - time.top <= 360 &&
    row.text.length <= 120 && venueRe.test(row.text) &&
    !dateRe.test(row.text) && !timeRe.test(row.text) &&
    !ticketRe.test(row.text) && !narrativeRe.test(row.text)
  );
  venues.sort((left, right) => {
    const leftExact = /^asian civilisations museum$/i.test(left.text) ? 0 : 1;
    const rightExact = /^asian civilisations museum$/i.test(right.text) ? 0 : 1;
    return leftExact - rightExact || left.top - right.top || left.area - right.area;
  });
  const venue = venues[0] || null;
  if (!venue) return base;

  const when = clean(`${date.text} · ${time.text}`);
  const lines = [];
  const add = value => {
    const text = clean(value);
    if (text && !lines.includes(text)) lines.push(text);
  };
  add(base.title);
  add("Date");
  add(when);
  add("Location");
  add(venue.text);
  add(base.summary);
  for (const value of base.lines || base.text_lines || []) add(value);

  return {
    ...base,
    dates: [when],
    venues: [venue.text],
    lines,
    text_lines: lines,
    text: lines.join("\n"),
  };
}
'''
    )


def _patch_acm_parent_fields() -> None:
    _detail_dates.ACTIVITY_DETAIL_JS = _wrap_acm_parent_fields(
        _detail_dates.ACTIVITY_DETAIL_JS
    )
    _browser.DETAIL_CARD_JS = _wrap_acm_parent_fields(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _wrap_acm_parent_fields(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )


def apply() -> None:
    """Install shared open-date, venue, and ACM parent-field repair."""

    global _APPLIED, _BASE_CANDIDATE_EXPIRED, _BASE_EXPLICIT_VENUE
    if _APPLIED:
        return

    _BASE_CANDIDATE_EXPIRED = _detail_dates._candidate_expired
    _BASE_EXPLICIT_VENUE = _membership._explicit_venue
    _patch_acm_parent_fields()
    _detail_dates._candidate_expired = candidate_expired
    _membership._explicit_venue = explicit_venue
    _APPLIED = True


__all__ = [
    "apply",
    "candidate_expired",
    "explicit_venue",
    "_patch_acm_parent_fields",
    "_wrap_acm_parent_fields",
]
