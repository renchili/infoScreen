from __future__ import annotations

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import source_overrides as _source_overrides

_APPLIED = False
_MARKER = "infoscreen_acm_icon_fact_rows_v1"


def _wrap_script(script: str) -> str:
    """Read ACM's parent Date/Time/Location rows from their actual icon-row component."""

    if _MARKER in script:
        return script

    return (
        "() => {\n"
        f"  const base = ({script})();\n"
        r'''
  const infoscreen_acm_icon_fact_rows_v1 = true;
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
  const attrText = element => {
    if (!element || !element.getAttribute) return "";
    const values = [];
    for (const name of [
      "class", "id", "aria-label", "title", "alt", "src", "href",
      "xlink:href", "data-icon", "data-testid", "data-component", "data-module"
    ]) {
      const value = clean(element.getAttribute(name));
      if (value) values.push(value);
    }
    return clean(values.join(" ")).toLowerCase();
  };
  const iconText = element => {
    const values = [attrText(element)];
    for (const child of element.querySelectorAll?.("img,svg,use,i,[class*='icon' i]") || []) {
      values.push(attrText(child));
    }
    return clean(values.join(" ")).toLowerCase();
  };

  const month = "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|" +
    "jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|" +
    "nov(?:ember)?|dec(?:ember)?)";
  const dateRe = new RegExp(
    "(?:\\b\\d{1,2}\\s*(?:[-–—]\\s*\\d{1,2}\\s*)?" + month +
    "\\s+20\\d{2}\\b|\\b" + month +
    "\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,)?\\s+20\\d{2}\\b|" +
    "\\b20\\d{2}-\\d{1,2}-\\d{1,2}\\b|" +
    "^(?:now\\s+)?(?:till|until|through|thru|from)\\s+.*20\\d{2})",
    "i"
  );
  const timeRe = /\b\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b/i;
  const recurrenceRe = /\b(?:daily|weekdays?|weekends?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b/i;
  const admissionRe = /\b(?:free|admission|ticket|tickets|fees?|charges?|pricing|price|\$)\b/i;
  const venueRe = /\b(?:asian civilisations museum|museum|gallery|level|room|hall|foyer|green|hardcourt|courtyard|plaza|studio)\b/i;
  const narrativeRe = /\b(?:explore|experience|discover|join|learn|enjoy|featuring|presented|step into)\b/i;

  const stripLabel = (kind, value) => {
    const labels = {
      date: /^(?:date|when)\s*:?\s*/i,
      time: /^(?:time|hours?)\s*:?\s*/i,
      venue: /^(?:location|venue|where)\s*:?\s*/i,
      admission: /^(?:admission|tickets?|fees?|price)\s*:?\s*/i,
    };
    return clean(String(value || "").replace(labels[kind], ""));
  };
  const valid = (kind, value) => {
    const text = stripLabel(kind, value);
    if (!text) return false;
    if (kind === "date") return dateRe.test(text);
    if (kind === "time") {
      return timeRe.test(text) &&
        (recurrenceRe.test(text) || /[\/,&]/.test(text) || !dateRe.test(text));
    }
    if (kind === "venue") {
      return text.length <= 140 && !dateRe.test(text) && !timeRe.test(text) &&
        !admissionRe.test(text) && !narrativeRe.test(text) && venueRe.test(text);
    }
    return text.length <= 180 && admissionRe.test(text);
  };

  const iconKind = element => {
    const tokens = iconText(element);
    if (/\b(?:calendar|calender|event[-_ ]?date|icon[-_ ]?date|date[-_ ]?icon)\b/i.test(tokens)) return "date";
    if (/\b(?:clock|event[-_ ]?time|icon[-_ ]?time|time[-_ ]?icon)\b/i.test(tokens)) return "time";
    if (/\b(?:location|venue|map[-_ ]?pin|marker|pin[-_ ]?map|icon[-_ ]?(?:location|venue))\b/i.test(tokens)) return "venue";
    if (/\b(?:ticket|admission|price|fee)\b/i.test(tokens)) return "admission";
    return "";
  };

  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(visible) || null;
  if (!heading) return base;
  const root = heading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") || document.body;
  const headingRect = heading.getBoundingClientRect();

  const rowForIcon = (icon, kind) => {
    const candidates = [];
    let current = icon;
    for (let depth = 0; current && current !== root.parentElement && depth < 8; depth += 1) {
      current = current.parentElement;
      if (!current || !visible(current)) continue;
      const rect = current.getBoundingClientRect();
      if (rect.top < headingRect.bottom - 12 || rect.top > headingRect.bottom + 1100) continue;
      if (rect.height > 220 || rect.width < 80) continue;
      const text = stripLabel(kind, current.innerText || current.textContent || "");
      if (!valid(kind, text)) continue;
      candidates.push({
        kind,
        text,
        top: rect.top,
        left: rect.left,
        height: rect.height,
        area: rect.width * rect.height,
        element: current,
      });
    }
    candidates.sort((left, right) => left.area - right.area || left.height - right.height);
    return candidates[0] || null;
  };

  const rows = [];
  const seen = new Set();
  for (const icon of root.querySelectorAll(
    "img,svg,use,i,[class*='icon' i],[id*='icon' i],[data-icon]"
  )) {
    if (!visible(icon)) continue;
    const declaredKind = iconKind(icon);
    const kinds = declaredKind
      ? [declaredKind]
      : ["date", "time", "venue", "admission"];
    for (const kind of kinds) {
      const row = rowForIcon(icon, kind);
      if (!row) continue;
      const key = `${kind}\u0000${row.text}\u0000${Math.round(row.top / 3)}`;
      if (!seen.has(key)) {
        seen.add(key);
        rows.push(row);
      }
      break;
    }
  }

  const byKind = kind => rows.filter(row => row.kind === kind)
    .sort((left, right) => left.top - right.top || left.left - right.left);
  const dates = byKind("date");
  const times = byKind("time");
  const venues = byKind("venue");
  const admissions = byKind("admission");
  const groups = [];

  for (const date of dates) {
    const time = times.find(row => row.top >= date.top - 8 && row.top - date.top <= 360);
    if (!time) continue;
    const venue = venues.find(row => row.top >= time.top - 8 && row.top - time.top <= 420);
    if (!venue) continue;
    const admission = admissions.find(row => row.top >= venue.top - 8 && row.top - venue.top <= 320) || null;
    groups.push({
      date: date.text,
      time: time.text,
      venue: venue.text,
      admission: admission ? admission.text : "",
      top: date.top,
      gap: Math.max(0, time.top - date.top) + Math.max(0, venue.top - time.top),
    });
  }

  groups.sort((left, right) => left.top - right.top || left.gap - right.gap);
  const facts = groups[0];
  if (!facts) return base;

  const when = clean(`${facts.date} · ${facts.time}`);
  const lines = [];
  const add = value => {
    const text = clean(value);
    if (text && !lines.includes(text)) lines.push(text);
  };
  add(base.title);
  add(facts.date);
  add(facts.time);
  add(facts.venue);
  if (facts.admission) add(facts.admission);
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


def apply() -> None:
    """Install icon-row extraction after the generic ACM fact fallback."""

    global _APPLIED
    if _APPLIED:
        return

    _detail_dates.ACTIVITY_DETAIL_JS = _wrap_script(_detail_dates.ACTIVITY_DETAIL_JS)
    _browser.DETAIL_CARD_JS = _wrap_script(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _wrap_script(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )
    _APPLIED = True


__all__ = ["apply", "_wrap_script", "_MARKER"]
