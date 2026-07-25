from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_BROWSER_MERGE = None
_BASE_SOURCE_MERGE = None
_BASE_PICK_WHEN = None
_BASE_PICK_VENUE = None

_MARKER = "infoscreen_acm_primary_fact_sequence_v2"


def _wrap_script(script: str) -> str:
    """Read ACM's visible Date/Time/Location/Admission group as one parent fact set."""

    if _MARKER in script:
        return script

    return (
        "() => {\n"
        f"  const base = ({script})();\n"
        r'''
  const infoscreen_acm_primary_fact_sequence_v2 = true;
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const host = String(location.hostname || "").replace(/^www\./i, "").toLowerCase();
  const path = String(location.pathname || "");
  const isAcm = host === "acm.nhb.gov.sg" ||
    (host === "nhb.gov.sg" && /^\/acm\/whats-on\//i.test(path));
  if (!isAcm) return base;

  const month = "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|" +
    "jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|" +
    "nov(?:ember)?|dec(?:ember)?)";
  const dated = new RegExp(
    "(?:\\b\\d{1,2}\\s*(?:[-–—]\\s*\\d{1,2}\\s*)?" + month +
    "\\s+20\\d{2}\\b|\\b" + month +
    "\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,)?\\s+20\\d{2}\\b|" +
    "\\b20\\d{2}-\\d{1,2}-\\d{1,2}\\b|" +
    "^(?:now\\s+)?(?:till|until|through|thru|from)\\s+.*20\\d{2})",
    "i"
  );
  const timed = /\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i;
  const recurrence = /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b/i;
  const admissionLike = /\b(?:free|admission|ticket|tickets|fees?|charges?|pricing|price|\$)\b/i;
  const venueLike = /\b(?:asian civilisations museum|museum|gallery|level|room|hall|foyer|green|hardcourt|courtyard|plaza|studio)\b/i;
  const narrative = /\b(?:explore|experience|discover|join|learn|enjoy|featuring|presented|step into)\b/i;

  const dateText = value => {
    const text = clean(value);
    return Boolean(text && dated.test(text));
  };
  const timeText = value => {
    const text = clean(value);
    return Boolean(
      text && timed.test(text) &&
      (recurrence.test(text) || /[\/,&]/.test(text) || !dated.test(text))
    );
  };
  const venueText = value => {
    const text = clean(value);
    if (!text || text.length > 140 || dated.test(text) || timed.test(text) ||
        admissionLike.test(text) || narrative.test(text)) return false;
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
    if (!dateText(date) || !timeText(time) || !venueText(venue)) return null;
    return {date, time, venue, admission};
  };

  let facts = normaliseFacts(base.primary_facts);

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
        if (rect.top < headingRect.bottom - 16 || rect.top > headingRect.bottom + 1500 ||
            rect.height > 190) continue;
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

        const timeRow = rows.slice(dateIndex + 1).find(row =>
          row.top >= dateRow.top && row.top - dateRow.top <= 360 && timeText(row.text)
        );
        if (!timeRow) continue;

        const venueRow = rows.find(row =>
          row.top >= timeRow.top && row.top - timeRow.top <= 420 && venueText(row.text)
        );
        if (!venueRow) continue;

        const admissionRow = rows.find(row =>
          row.top >= venueRow.top && row.top - venueRow.top <= 300 &&
          admissionText(row.text)
        ) || null;

        let score = 1000 - dateIndex;
        if (dateIcon.test(dateRow.tokens)) score += 100;
        if (timeIcon.test(timeRow.tokens)) score += 100;
        if (placeIcon.test(venueRow.tokens)) score += 140;
        if (admissionRow && ticketIcon.test(admissionRow.tokens)) score += 60;
        if (/^asian civilisations museum$/i.test(venueRow.text)) score += 100;
        score -= Math.round(timeRow.top - dateRow.top);
        score -= Math.round(venueRow.top - timeRow.top);
        groups.push({
          score,
          date: dateRow.text,
          time: timeRow.text,
          venue: venueRow.text,
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
      let timeIndex = -1;
      for (let index = dateIndex + 1; index <= Math.min(lines.length - 1, dateIndex + 6); index += 1) {
        if (timeText(lines[index])) { timeIndex = index; break; }
      }
      if (timeIndex < 0) continue;
      let venueIndex = -1;
      for (let index = timeIndex + 1; index <= Math.min(lines.length - 1, timeIndex + 6); index += 1) {
        if (venueText(lines[index])) { venueIndex = index; break; }
      }
      if (venueIndex < 0) continue;
      const admission = lines.slice(venueIndex + 1, venueIndex + 5).find(admissionText) || "";
      facts = normaliseFacts({
        date: lines[dateIndex],
        time: lines[timeIndex],
        venue: lines[venueIndex],
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
  add("Location");
  add(facts.venue);
  if (facts.admission) {
    add("Admission");
    add(facts.admission);
  }
  add(base.summary);
  for (const value of base.lines || base.text_lines || []) add(value);

  return {
    ...base,
    dates: [when],
    venues: [facts.venue],
    primary_facts: facts,
    lines,
    text_lines: lines,
    text: lines.join("\n"),
  };
}
'''
    )


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _facts(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    for value in (
        raw.get("detail_primary_facts"),
        raw.get("primary_facts"),
        (raw.get("detail_evidence") or {}).get("primary_facts")
        if isinstance(raw.get("detail_evidence"), dict)
        else None,
    ):
        if not isinstance(value, dict):
            continue
        facts = {
            "date": _clean(value.get("date")),
            "time": _clean(value.get("time")),
            "venue": _clean(value.get("venue")),
            "admission": _clean(value.get("admission") or value.get("ticket")),
        }
        if facts["date"] and facts["time"] and facts["venue"]:
            return facts
    return {}


def _when(facts: dict[str, str]) -> str:
    if not facts:
        return ""
    return _clean(f"{facts['date']} · {facts['time']}")


def merge_detail_payload(card: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(_BASE_BROWSER_MERGE(card, detail))
    facts = _facts(detail)
    if not facts:
        return merged
    merged["detail_primary_facts"] = facts
    merged["detail_dates"] = [_when(facts)]
    merged["detail_venues"] = [facts["venue"]]
    return merged


def merge_source_detail(
    source: dict[str, Any],
    card: dict[str, Any],
    payload: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    merged = dict(_BASE_SOURCE_MERGE(source, card, payload, index))
    facts = _facts(payload)
    if not facts:
        return merged
    evidence = dict(merged.get("detail_evidence") or {})
    evidence["primary_facts"] = facts
    evidence["date_candidates"] = [_when(facts)]
    evidence["venue_candidates"] = [facts["venue"]]
    merged["detail_evidence"] = evidence
    merged["detail_primary_facts"] = facts
    return merged


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
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
    facts = _facts(card)
    if facts.get("venue"):
        return facts["venue"]
    return _BASE_PICK_VENUE(source, card, when, when_line)


def apply() -> None:
    """Install ACM parent fact grouping after the generic detail-field authorities."""

    global _APPLIED, _BASE_BROWSER_MERGE, _BASE_SOURCE_MERGE
    global _BASE_PICK_WHEN, _BASE_PICK_VENUE
    if _APPLIED:
        return

    _BASE_BROWSER_MERGE = _browser.merge_detail_payload
    _BASE_SOURCE_MERGE = _source_overrides._merge_detail
    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_PICK_VENUE = _extract.pick_venue

    _detail_dates.ACTIVITY_DETAIL_JS = _wrap_script(_detail_dates.ACTIVITY_DETAIL_JS)
    _browser.DETAIL_CARD_JS = _wrap_script(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _wrap_script(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )
    _browser.merge_detail_payload = merge_detail_payload
    _source_overrides._merge_detail = merge_source_detail
    _extract.pick_when = pick_when
    _extract.pick_venue = pick_venue
    _APPLIED = True


__all__ = [
    "apply",
    "merge_detail_payload",
    "merge_source_detail",
    "pick_venue",
    "pick_when",
    "_facts",
    "_when",
    "_wrap_script",
]
