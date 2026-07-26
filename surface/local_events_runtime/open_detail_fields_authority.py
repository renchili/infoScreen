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
_BASE_PICK_WHEN = None
_BASE_PICK_VENUE = None

_EXPLICIT_YEAR_RE = re.compile(r"\b20\d{2}\b")
_VENUE_HINT_RE = re.compile(
    r"\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|"
    r"auditorium|atrium|foyer|lobby|library|centre|center|park|gardens?|zoo|"
    r"green|hardcourt|courtyard|plaza|studio|basement|meeting point)\b",
    re.I,
)
_NON_VENUE_RE = re.compile(
    r"^(?:admission|ticket|tickets|free|paid|book|register|programme|program|"
    r"event|events|exhibition|exhibitions|terms?|conditions?|last updated|"
    r"in[-\s]?gallery|in[-\s]?museum|outdoor(?: installation| performances?)?|"
    r"performances?|drop-in(?: activities| experiences)?|registered programmes?|"
    r"exclusive promotion|giveaway)\b",
    re.I,
)
_SUMMARY_SORT_OLD = (
    "summaryRows.sort((left, right) => right.score - left.score || "
    "left.text.length - right.text.length);"
)
_SUMMARY_SORT_NEW = "summaryRows.sort((left, right) => right.score - left.score);"
_ACM_PRIMARY_FACTS_MARKER = "infoscreen_acm_primary_facts_v1"


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        return [_extract.clean(value) for value in raw if _extract.clean(value)]
    return _extract.lines(card.get("text") or "")


def _detail_date_rows(card: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for value in card.get("detail_dates") or []:
        text = _extract.clean(value)
        if text and text not in rows:
            rows.append(text)
    evidence = card.get("detail_evidence")
    if isinstance(evidence, dict):
        for value in evidence.get("date_candidates") or []:
            text = _extract.clean(value)
            if text and text not in rows:
                rows.append(text)
    return rows


def _primary_detail_date(card: dict[str, Any]) -> str:
    """Use the structurally isolated parent fact row before parser fallbacks."""

    dated: list[tuple[int, str, list[Any], bool]] = []
    for index, row in enumerate(_detail_date_rows(card)):
        parsed = _extract.label_dates(row)
        if parsed:
            dated.append((index, row, parsed, bool(_EXPLICIT_YEAR_RE.search(row))))

    explicit_ranges = [item for item in dated if item[3] and len(item[2]) >= 2]
    if explicit_ranges:
        return explicit_ranges[0][1]

    explicit_singles = [item for item in dated if item[3] and len(item[2]) == 1]
    if explicit_singles:
        return explicit_singles[0][1]

    ranges = [item for item in dated if len(item[2]) >= 2]
    if ranges:
        return ranges[0][1]
    return dated[0][1] if dated else ""


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
    """Prefer the parent fact component's combined date and time."""

    primary = _primary_detail_date(card)
    if primary:
        return _extract.short(primary, 180), primary
    return _BASE_PICK_WHEN(card)


def _valid_venue(value: object, *, require_hint: bool = False) -> bool:
    text = _extract.clean(value)
    if not text or len(text) > 180 or len(text.split()) > 24:
        return False
    if _NON_VENUE_RE.search(text):
        return False
    if _extract.DATE_LINE_RE.search(text) or _extract.TIME_RE.fullmatch(text):
        return False
    return not require_hint or bool(_VENUE_HINT_RE.search(text))


def pick_venue(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    when_line: str,
) -> str:
    """Trust the structurally isolated venue and reject taxonomy labels."""

    venue = _extract.clean(_BASE_PICK_VENUE(source, card, when, when_line))
    if _valid_venue(venue):
        return venue
    return _extract.clean(source.get("default_venue") or source.get("name"))


def explicit_venue(card: dict[str, Any]) -> str:
    """Recognise a real unlabelled venue line in an official detail document."""

    venue = _extract.clean(_BASE_EXPLICIT_VENUE(card))
    if _valid_venue(venue):
        return venue

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(_card_lines(card)):
        if not _valid_venue(line, require_hint=True):
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


def _patched_summary_script(script: str) -> str:
    if _SUMMARY_SORT_OLD in script:
        return script.replace(_SUMMARY_SORT_OLD, _SUMMARY_SORT_NEW, 1)
    if _SUMMARY_SORT_NEW not in script:
        raise RuntimeError("detail_summary_order_patch_missing")
    return script


def _patch_detail_summary_order() -> None:
    """Keep the first equally scored primary paragraph ahead of later child text."""

    _detail_dates.ACTIVITY_DETAIL_JS = _patched_summary_script(
        _detail_dates.ACTIVITY_DETAIL_JS
    )
    _browser.DETAIL_CARD_JS = _patched_summary_script(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _patched_summary_script(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )


def _wrap_acm_primary_facts(script: str) -> str:
    """Post-process one detail payload using ACM's visible parent fact component."""

    if _ACM_PRIMARY_FACTS_MARKER in script:
        return script

    return (
        "() => {\n"
        f"  const base = ({script})();\n"
        r'''
  const infoscreen_acm_primary_facts_v1 = true;
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
  const follows = (left, right) => Boolean(
    left && right &&
    (left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING)
  );
  const attrs = element => {
    if (!element || !element.getAttribute) return "";
    const values = [];
    for (const name of [
      "class", "id", "aria-label", "title", "alt", "src", "href",
      "data-icon", "data-testid", "data-component", "data-module"
    ]) {
      const value = clean(element.getAttribute(name));
      if (value) values.push(value);
    }
    return values.join(" ");
  };
  const tokensAround = element => {
    const values = [];
    let current = element;
    for (let depth = 0; current && depth < 4; depth += 1, current = current.parentElement) {
      values.push(attrs(current));
      for (const child of current.querySelectorAll(
        "img,svg,use,i,[class*='icon' i],[id*='icon' i]"
      )) {
        values.push(attrs(child));
      }
    }
    return clean(values.join(" ")).toLowerCase();
  };
  const primaryHeading = Array.from(
    document.querySelectorAll("main h1, article h1, h1")
  ).find(visible) || null;
  if (!primaryHeading) return base;

  const root = primaryHeading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") ||
    document.body;
  const headingRect = primaryHeading.getBoundingClientRect();
  const rawRows = [];

  for (const element of Array.from(root.querySelectorAll("*"))) {
    if (!visible(element) || !follows(primaryHeading, element)) continue;
    const text = clean(element.innerText || element.textContent || "");
    if (!text || text.length > 240 || text.split(/\s+/).length > 36) continue;

    const rect = element.getBoundingClientRect();
    if (rect.top < headingRect.bottom - 8 || rect.top > headingRect.bottom + 2200) {
      continue;
    }
    const childRepeatsText = Array.from(element.children || []).some(
      child => visible(child) &&
        clean(child.innerText || child.textContent || "") === text
    );
    if (childRepeatsText) continue;

    rawRows.push({
      element,
      text,
      tokens: tokensAround(element),
      top: rect.top,
    });
  }

  const rows = [];
  const seen = new Set();
  for (const row of rawRows) {
    const signature = `${row.text}\u0000${Math.round(row.top / 4)}`;
    if (seen.has(signature)) continue;
    seen.add(signature);
    rows.push(row);
  }

  const month = "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|" +
    "jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|" +
    "nov(?:ember)?|dec(?:ember)?)";
  const concreteDate = new RegExp(
    "(?:\\b\\d{1,2}\\s*(?:[-–—]\\s*\\d{1,2}\\s*)?" + month +
    "\\s+20\\d{2}\\b|\\b" + month +
    "\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,)?\\s+20\\d{2}\\b|" +
    "\\b20\\d{2}-\\d{1,2}-\\d{1,2}\\b)",
    "i"
  );
  const closedOrStart = new RegExp(
    "^(?:now\\s+)?(?:till|until|through|thru|from)\\s+.*20\\d{2}",
    "i"
  );
  const clockTime = /\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i;
  const recurrence = /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b/i;
  const ticket = /\b(?:free|admission|ticket|tickets|fees?|charges?|pricing|price|\$)\b/i;
  const narrative = /\b(?:explore|experience|discover|join|learn|enjoy|featuring|presented)\b/i;
  const dateIcon = /\b(?:calendar|event[-_ ]?date|icon[-_ ]?date|date[-_ ]?icon)\b/i;
  const timeIcon = /\b(?:clock|event[-_ ]?time|icon[-_ ]?time|time[-_ ]?icon)\b/i;
  const placeIcon = /\b(?:location|venue|map[-_ ]?pin|marker|pin[-_ ]?map|icon[-_ ]?(?:location|venue))\b/i;

  const isDateRow = row => (
    concreteDate.test(row.text) || closedOrStart.test(row.text) ||
    (dateIcon.test(row.tokens) && /\b20\d{2}\b/.test(row.text))
  );
  const isTimeRow = row => (
    clockTime.test(row.text) &&
    (recurrence.test(row.text) || timeIcon.test(row.tokens) || !concreteDate.test(row.text))
  );
  const isVenueRow = row => {
    if (!row.text || concreteDate.test(row.text) || clockTime.test(row.text) ||
        ticket.test(row.text) || narrative.test(row.text)) return false;
    if (/^asian civilisations museum$/i.test(row.text)) return true;
    return placeIcon.test(row.tokens);
  };
  const neutralVenueRow = row => (
    row.text.length <= 100 &&
    !concreteDate.test(row.text) &&
    !clockTime.test(row.text) &&
    !ticket.test(row.text) &&
    !narrative.test(row.text) &&
    !/^(?:date|time|location|venue|where|when)$/i.test(row.text)
  );

  const candidates = [];
  for (let dateIndex = 0; dateIndex < rows.length; dateIndex += 1) {
    const dateRow = rows[dateIndex];
    if (!isDateRow(dateRow)) continue;

    let timeIndex = -1;
    for (let index = dateIndex + 1; index <= Math.min(rows.length - 1, dateIndex + 10); index += 1) {
      if (isTimeRow(rows[index])) {
        timeIndex = index;
        break;
      }
    }
    if (timeIndex < 0) continue;

    let venueIndex = -1;
    for (let index = timeIndex + 1; index <= Math.min(rows.length - 1, timeIndex + 10); index += 1) {
      if (isVenueRow(rows[index])) {
        venueIndex = index;
        break;
      }
      if (ticket.test(rows[index].text)) break;
    }
    if (venueIndex < 0) {
      for (let index = timeIndex + 1; index <= Math.min(rows.length - 1, timeIndex + 5); index += 1) {
        if (neutralVenueRow(rows[index])) {
          venueIndex = index;
          break;
        }
        if (ticket.test(rows[index].text)) break;
      }
    }
    if (venueIndex < 0) continue;

    const venueRow = rows[venueIndex];
    if (venueRow.top - dateRow.top > 650) continue;

    let score = 1000 - dateIndex;
    if (dateIcon.test(dateRow.tokens)) score += 120;
    if (timeIcon.test(rows[timeIndex].tokens)) score += 120;
    if (placeIcon.test(venueRow.tokens)) score += 160;
    if (/^asian civilisations museum$/i.test(venueRow.text)) score += 100;
    score -= Math.max(0, timeIndex - dateIndex - 1) * 10;
    score -= Math.max(0, venueIndex - timeIndex - 1) * 10;
    candidates.push({
      score,
      dateIndex,
      timeIndex,
      venueIndex,
      dateRow,
      timeRow: rows[timeIndex],
      venueRow,
    });
  }

  candidates.sort((left, right) => right.score - left.score || left.dateIndex - right.dateIndex);
  const facts = candidates[0];
  if (!facts) return base;

  const when = clean(
    facts.dateRow.text +
    (facts.timeRow.text && facts.timeRow.text !== facts.dateRow.text
      ? " · " + facts.timeRow.text
      : "")
  );
  const venue = clean(facts.venueRow.text);

  const sectionBoundary = Array.from(root.querySelectorAll("h2,h3"))
    .filter(visible)
    .find(element => follows(facts.venueRow.element, element) && (
      /^[A-Z0-9][A-Z0-9 &/:'’–—-]{4,}$/.test(clean(element.innerText || element.textContent || "")) ||
      /\b(?:drop-in activities|performances|gallery experiences|registered activities|collectible zine)\b/i.test(
        clean(element.innerText || element.textContent || "")
      )
    )) || null;
  const summaryCandidates = Array.from(root.querySelectorAll(
    "p,[itemprop='description'],[class*='intro' i],[class*='description' i]"
  ))
    .filter(visible)
    .filter(element => follows(primaryHeading, element))
    .filter(element => !sectionBoundary || follows(element, sectionBoundary))
    .map(element => clean(element.innerText || element.textContent || ""))
    .filter(text => text.length >= 40 && text.length <= 1200)
    .filter(text => !ticket.test(text))
    .filter((text, index, all) => all.indexOf(text) === index);
  const summary = summaryCandidates[0] || clean(base.summary);

  const lines = [];
  const add = value => {
    const text = clean(value);
    if (text && !lines.includes(text)) lines.push(text);
  };
  add(base.title);
  add("Date");
  add(when);
  add("Location");
  add(venue);
  add(summary);

  return {
    ...base,
    dates: when ? [when] : [],
    venues: venue ? [venue] : [],
    summary,
    summary_candidates: summary ? [summary] : [],
    lines,
    text_lines: lines,
    text: lines.join("\n"),
    primary_facts: {
      date: facts.dateRow.text,
      time: facts.timeRow.text,
      venue,
    },
  };
}
'''
    )


def _patch_acm_primary_facts() -> None:
    """Bind parent date/time/venue rows before any child-programme section."""

    _detail_dates.ACTIVITY_DETAIL_JS = _wrap_acm_primary_facts(
        _detail_dates.ACTIVITY_DETAIL_JS
    )
    _browser.DETAIL_CARD_JS = _wrap_acm_primary_facts(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _wrap_acm_primary_facts(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )


def apply() -> None:
    """Install parent-fact extraction, lifecycle, venue, and summary repairs."""

    global _APPLIED, _BASE_CANDIDATE_EXPIRED, _BASE_EXPLICIT_VENUE
    global _BASE_PICK_WHEN, _BASE_PICK_VENUE
    if _APPLIED:
        return

    _BASE_CANDIDATE_EXPIRED = _detail_dates._candidate_expired
    _BASE_EXPLICIT_VENUE = _membership._explicit_venue
    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_PICK_VENUE = _extract.pick_venue

    _patch_detail_summary_order()
    _patch_acm_primary_facts()
    _extract.pick_when = pick_when
    _extract.pick_venue = pick_venue
    _detail_dates._candidate_expired = candidate_expired
    _membership._explicit_venue = explicit_venue
    _APPLIED = True


__all__ = [
    "apply",
    "candidate_expired",
    "explicit_venue",
    "pick_venue",
    "pick_when",
    "_patch_acm_primary_facts",
    "_patch_detail_summary_order",
    "_primary_detail_date",
    "_wrap_acm_primary_facts",
]
