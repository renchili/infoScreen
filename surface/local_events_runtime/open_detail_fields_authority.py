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
_BASE_BROWSER_MERGE = None
_BASE_SOURCE_MERGE = None
_BASE_PICK_WHEN = None
_BASE_PICK_VENUE = None

_ACM_PARENT_FIELDS_MARKER = "infoscreen_acm_parent_fields_v3"

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


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


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
    """Read ACM's visible parent Date/Time and optional Location/Admission rows."""

    if _ACM_PARENT_FIELDS_MARKER in script:
        return script

    return (
        "() => {\n"
        f"  const base = ({script})();\n"
        r'''
  const infoscreen_acm_parent_fields_v3 = true;
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const host = String(location.hostname || "").replace(/^www\./i, "").toLowerCase();
  const path = String(location.pathname || "");
  const isAcm = host === "acm.nhb.gov.sg" ||
    (host === "nhb.gov.sg" && /^\/acm\/whats-on\//i.test(path));
  if (!isAcm) return base;

  const month = /\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b/i;
  const explicitYear = /\b20\d{2}\b/;
  const timed = /\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i;
  const recurrence = /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b/i;
  const admissionLike = /\b(?:free|admission|ticket|tickets|fees?|charges?|pricing|price|\$)\b/i;
  const venueLike = /\b(?:asian civilisations museum|museum|gallery|galleries|level|room|hall|foyer|green|hardcourt|courtyard|plaza|studio)\b/i;
  const narrative = /\b(?:explore|experience|discover|join|learn|enjoy|featuring|presented|step into|during the|this section)\b/i;
  const metadata = /\b(?:last updated|updated on|copyright|privacy|cookie|newsletter)\b/i;

  const dateText = value => {
    const text = clean(value);
    return Boolean(
      text && text.length <= 180 && explicitYear.test(text) && month.test(text) &&
      !metadata.test(text) && !narrative.test(text)
    );
  };
  const timeText = value => {
    const text = clean(value);
    return Boolean(
      text && text.length <= 180 && timed.test(text) && !explicitYear.test(text) &&
      (recurrence.test(text) || /[\/,&]/.test(text)) && !narrative.test(text)
    );
  };
  const venueText = value => {
    const text = clean(value);
    if (!text || text.length > 140 || explicitYear.test(text) || timed.test(text) ||
        admissionLike.test(text) || narrative.test(text) || metadata.test(text)) return false;
    return /^asian civilisations museum$/i.test(text) || venueLike.test(text);
  };
  const admissionText = value => {
    const text = clean(value);
    return Boolean(text && text.length <= 180 && admissionLike.test(text));
  };
  const normaliseFacts = raw => {
    if (!raw || typeof raw !== "object") return null;
    const date = clean(raw.date);
    const time = clean(raw.time);
    const venue = clean(raw.venue);
    const admission = clean(raw.admission || raw.ticket);
    if (!dateText(date) || !timeText(time)) return null;
    if (venue && !venueText(venue)) return null;
    return {date, time, venue, admission};
  };

  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
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
  const iconTokens = element => {
    const values = [attrs(element)];
    for (const child of element.querySelectorAll(
      "img,svg,use,i,[class*='icon' i],[id*='icon' i]"
    )) values.push(attrs(child));
    return clean(values.join(" ")).toLowerCase();
  };
  const dateIcon = /\b(?:calendar|event[-_ ]?date|icon[-_ ]?date|date[-_ ]?icon)\b/i;
  const timeIcon = /\b(?:clock|event[-_ ]?time|icon[-_ ]?time|time[-_ ]?icon)\b/i;
  const placeIcon = /\b(?:location|venue|map[-_ ]?pin|marker|pin[-_ ]?map|icon[-_ ]?(?:location|venue))\b/i;
  const ticketIcon = /\b(?:ticket|admission|price|fee)\b/i;

  let facts = normaliseFacts(base.primary_facts);
  if (!facts) {
    const heading = Array.from(
      document.querySelectorAll("main h1, article h1, h1")
    ).find(visible) || null;
    if (heading) {
      const root = heading.closest(
        "article, [class*='event-detail' i], [class*='eventDetail' i], " +
        "[class*='detail-page' i], [class*='content-detail' i], main"
      ) || document.querySelector("main") || document.querySelector("article") ||
        document.body;
      const headingRect = heading.getBoundingClientRect();
      const rows = [];
      const seen = new Set();

      for (const element of Array.from(root.querySelectorAll("*"))) {
        if (!visible(element)) continue;
        const rect = element.getBoundingClientRect();
        if (rect.top < headingRect.bottom - 16 || rect.top > headingRect.bottom + 1600 ||
            rect.height > 210) continue;
        const text = clean(element.innerText || element.textContent || "");
        if (!text || text.length > 240 || text.split(/\s+/).length > 38) continue;
        const sameTextChild = Array.from(element.children || []).some(child =>
          visible(child) && clean(child.innerText || child.textContent || "") === text
        );
        if (sameTextChild) continue;
        const signature = `${text}\u0000${Math.round(rect.top / 3)}`;
        if (seen.has(signature)) continue;
        seen.add(signature);
        rows.push({
          text,
          top: rect.top,
          left: rect.left,
          tokens: iconTokens(element),
        });
      }
      rows.sort((left, right) => left.top - right.top || left.left - right.left);

      const groups = [];
      for (let dateIndex = 0; dateIndex < rows.length; dateIndex += 1) {
        const dateRow = rows[dateIndex];
        if (!dateText(dateRow.text)) continue;

        const following = rows.filter(row =>
          row.top >= dateRow.top && row.top - dateRow.top <= 520
        );
        const timeRows = following.filter(row => timeText(row.text));
        if (!timeRows.length) continue;

        const venueRow = following.find(row =>
          row.top >= timeRows[0].top && venueText(row.text)
        ) || null;
        const admissionRow = following.find(row =>
          row.top >= (venueRow ? venueRow.top : timeRows[0].top) && admissionText(row.text)
        ) || null;

        const timeValues = [];
        for (const row of timeRows) {
          if (!timeValues.includes(row.text)) timeValues.push(row.text);
        }
        const combinedTime = timeValues.slice(0, 3).join(" / ");

        let score = 1000 - dateIndex;
        if (dateIcon.test(dateRow.tokens)) score += 100;
        if (timeRows.some(row => timeIcon.test(row.tokens))) score += 100;
        if (venueRow && placeIcon.test(venueRow.tokens)) score += 140;
        if (admissionRow && ticketIcon.test(admissionRow.tokens)) score += 60;
        if (venueRow && /^asian civilisations museum$/i.test(venueRow.text)) score += 100;
        score -= Math.round(timeRows[0].top - dateRow.top);

        groups.push({
          score,
          date: dateRow.text,
          time: combinedTime,
          venue: venueRow ? venueRow.text : "",
          admission: admissionRow ? admissionRow.text : "",
        });
      }
      groups.sort((left, right) => right.score - left.score);
      facts = normaliseFacts(groups[0]);
    }
  }

  if (!facts) {
    const rawLines = Array.isArray(base.lines)
      ? base.lines
      : (Array.isArray(base.text_lines)
        ? base.text_lines
        : String(base.text || "").split(/\n+/));
    const lines = rawLines.map(clean).filter(Boolean);
    for (let dateIndex = 0; dateIndex < lines.length && !facts; dateIndex += 1) {
      if (!dateText(lines[dateIndex])) continue;

      const nearby = lines.slice(dateIndex + 1, dateIndex + 9);
      const times = nearby.filter(timeText);
      if (!times.length) continue;
      const venue = nearby.find(venueText) || "";
      const admission = nearby.find(admissionText) || "";
      facts = normaliseFacts({
        date: lines[dateIndex],
        time: [...new Set(times)].slice(0, 3).join(" / "),
        venue,
        admission,
      });
    }
  }

  if (!facts) return base;

  const when = clean(`${facts.date} · ${facts.time}`);
  const lines = [];
  const add = value => {
    const text = clean(value);
    if (text && !lines.includes(text)) lines.push(text);
  };
  add(base.title);
  add("Date");
  add(facts.date);
  add("Time");
  add(facts.time);
  if (facts.venue) {
    add("Location");
    add(facts.venue);
  }
  if (facts.admission) {
    add("Admission");
    add(facts.admission);
  }
  add(base.summary);
  for (const value of base.lines || base.text_lines || []) add(value);

  return {
    ...base,
    dates: [when],
    venues: facts.venue ? [facts.venue] : [],
    primary_facts: facts,
    lines,
    text_lines: lines,
    text: lines.join("\n"),
  };
}
'''
    )


def _facts(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}

    evidence = raw.get("detail_evidence")
    values = (
        raw.get("detail_primary_facts"),
        raw.get("primary_facts"),
        evidence.get("primary_facts") if isinstance(evidence, dict) else None,
    )
    for value in values:
        if not isinstance(value, dict):
            continue
        facts = {
            "date": _clean(value.get("date")),
            "time": _clean(value.get("time")),
            "venue": _clean(value.get("venue")),
            "admission": _clean(value.get("admission") or value.get("ticket")),
        }
        if facts["date"] and facts["time"]:
            return facts
    return {}


def _when(facts: dict[str, str]) -> str:
    if not facts:
        return ""
    return _clean(f"{facts['date']} · {facts['time']}")


def merge_detail_payload(
    card: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Preserve ACM parent facts across the generic browser merge."""

    merged = dict(_BASE_BROWSER_MERGE(card, detail))
    facts = _facts(detail)
    if not facts:
        return merged

    merged["detail_primary_facts"] = facts
    merged["detail_dates"] = [_when(facts)]
    merged["detail_venues"] = [facts["venue"]] if facts["venue"] else []
    return merged


def merge_source_detail(
    source: dict[str, Any],
    card: dict[str, Any],
    payload: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Preserve the same facts in scheduled/formal collection evidence."""

    merged = dict(_BASE_SOURCE_MERGE(source, card, payload, index))
    facts = _facts(payload)
    if not facts:
        return merged

    evidence = dict(merged.get("detail_evidence") or {})
    evidence["primary_facts"] = facts
    evidence["date_candidates"] = [_when(facts)]
    evidence["venue_candidates"] = [facts["venue"]] if facts["venue"] else []
    merged["detail_evidence"] = evidence
    merged["detail_primary_facts"] = facts
    return merged


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
    """Make the parent ACM Date + Time group the final When authority."""

    value = _when(_facts(card))
    if value:
        return _extract.short(value, 180), value
    return _BASE_PICK_WHEN(card)


def pick_venue(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    when_line: str,
) -> str:
    """Use only an explicit parent ACM Location when parent facts were found."""

    facts = _facts(card)
    if facts:
        return facts.get("venue", "")
    return _BASE_PICK_VENUE(source, card, when, when_line)


def _patch_acm_parent_fields() -> None:
    _detail_dates.ACTIVITY_DETAIL_JS = _wrap_acm_parent_fields(
        _detail_dates.ACTIVITY_DETAIL_JS
    )
    _browser.DETAIL_CARD_JS = _wrap_acm_parent_fields(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _wrap_acm_parent_fields(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )


def apply() -> None:
    """Install open-date, venue, and authoritative ACM parent-field repair."""

    global _APPLIED, _BASE_CANDIDATE_EXPIRED, _BASE_EXPLICIT_VENUE
    global _BASE_BROWSER_MERGE, _BASE_SOURCE_MERGE
    global _BASE_PICK_WHEN, _BASE_PICK_VENUE
    if _APPLIED:
        return

    _BASE_CANDIDATE_EXPIRED = _detail_dates._candidate_expired
    _BASE_EXPLICIT_VENUE = _membership._explicit_venue
    _BASE_BROWSER_MERGE = _browser.merge_detail_payload
    _BASE_SOURCE_MERGE = _source_overrides._merge_detail
    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_PICK_VENUE = _extract.pick_venue

    _patch_acm_parent_fields()
    _browser.merge_detail_payload = merge_detail_payload
    _source_overrides._merge_detail = merge_source_detail
    _extract.pick_when = pick_when
    _extract.pick_venue = pick_venue
    _detail_dates._candidate_expired = candidate_expired
    _membership._explicit_venue = explicit_venue
    _APPLIED = True


__all__ = [
    "apply",
    "candidate_expired",
    "explicit_venue",
    "merge_detail_payload",
    "merge_source_detail",
    "pick_venue",
    "pick_when",
    "_facts",
    "_patch_acm_parent_fields",
    "_when",
    "_wrap_acm_parent_fields",
]
