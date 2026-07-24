from __future__ import annotations

import re
from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import detail_payload_authority as _detail_payload
from . import extract as _extract
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_DETAIL_JS = _detail_payload.ENRICHED_DETAIL_JS

_OPERATION_BOUNDARY_RE = re.compile(
    r"(?:\bterms?\s*(?:&|and)\s*conditions?\b|"
    r"\bterms?\s+of\s+(?:use|participation)\b|"
    r"\bfor\s+(?:further\s+)?enquir(?:y|ies)\b|"
    r"\bfurther\s+enquir(?:y|ies)\b|"
    r"\bplease\s+email\b|"
    r"\bfirst[-\s]?come[-\s]?first[-\s]?served\b|"
    r"\b(?:no\s+)?pre[-\s]?registration\b|"
    r"\bregistration\s+(?:is|will|opens?|closes?|required|not\s+required)\b|"
    r"\bdonations?\s+are\s+encouraged\b|"
    r"\bfor\s+safety\b|"
    r"\bsafety\s+(?:requirements?|notes?|advisory)\b|"
    r"\brefund(?:s|\s+policy)?\b|"
    r"\bcancellations?\b|"
    r"\bparental\s+consent\b|"
    r"\bwaiver\b|"
    r"\badmission\s+(?:fee|fees|charges?)\b|"
    r"\bticket(?:ing)?\s+(?:details?|information)\b|"
    r"\bprogramme\s+is\s+free\b|"
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.I,
)
_CTA_RE = re.compile(
    r"\b(?:book\s+(?:your\s+)?tickets?|buy\s+tickets?|book\s+now|"
    r"visit\s+.{0,100}?\s+today|plan\s+your\s+visit|find\s+out\s+more|"
    r"learn\s+more|read\s+more|explore\s+more|register\s+now|sign\s+up|"
    r"get\s+your\s+tickets?)\b",
    re.I,
)
_SHELL_RE = re.compile(
    r"\b(?:privacy|cookie|newsletter|copyright|breadcrumb|navigation|"
    r"previous\s+(?:event|programme)|next\s+(?:event|programme))\b",
    re.I,
)


def useful_event_summary(value: object) -> str:
    """Return only the narrative portion of one activity-detail candidate.

    Detail pages frequently place registration rules, contact details, safety notes,
    and terms in the same rich-text container as the activity introduction. Those
    operational sections are evidence for attendance, not a description of the
    activity. When a candidate contains both, the narrative prefix is retained and
    the first operational boundary ends the summary.
    """

    text = _extract.clean(value)
    if not text:
        return ""

    boundary = _OPERATION_BOUNDARY_RE.search(text)
    if boundary:
        prefix = text[: boundary.start()].strip(" \t\r\n-–—:;,.|")
        text = prefix if len(prefix) >= 40 else ""

    if len(text) < 40 or len(text) > 1800:
        return ""
    if _SHELL_RE.search(text):
        return ""

    words = text.split()
    if _CTA_RE.search(text) and (len(text) < 360 or len(words) < 45):
        return ""

    letters = "".join(character for character in text if character.isalpha())
    if letters:
        uppercase = sum(1 for character in letters if character.isupper())
        if uppercase / len(letters) > 0.82 and len(words) < 24:
            return ""
    return text


SECTIONED_DETAIL_JS = (
    r"""
() => {
  const base = (
"""
    + _BASE_DETAIL_JS
    + r"""
  )();
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const key = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  };
  const operationBoundary = value => /(?:\bterms?\s*(?:&|and)\s*conditions?\b|\bterms?\s+of\s+(?:use|participation)\b|\bfor\s+(?:further\s+)?enquir(?:y|ies)\b|\bfurther\s+enquir(?:y|ies)\b|\bplease\s+email\b|\bfirst[-\s]?come[-\s]?first[-\s]?served\b|\b(?:no\s+)?pre[-\s]?registration\b|\bregistration\s+(?:is|will|opens?|closes?|required|not\s+required)\b|\bdonations?\s+are\s+encouraged\b|\bfor\s+safety\b|\bsafety\s+(?:requirements?|notes?|advisory)\b|\brefund(?:s|\s+policy)?\b|\bcancellations?\b|\bparental\s+consent\b|\bwaiver\b|\badmission\s+(?:fee|fees|charges?)\b|\bticket(?:ing)?\s+(?:details?|information)\b|\bprogramme\s+is\s+free\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/i.exec(clean(value));
  const cta = value => /\b(book\s+(?:your\s+)?tickets?|buy\s+tickets?|book\s+now|visit\s+.{0,100}?\s+today|plan\s+your\s+visit|find\s+out\s+more|learn\s+more|read\s+more|explore\s+more|register\s+now|sign\s+up|get\s+your\s+tickets?)\b/i.test(clean(value));
  const shell = value => /\b(privacy|cookie|newsletter|copyright|breadcrumb|navigation|previous\s+(?:event|programme)|next\s+(?:event|programme))\b/i.test(clean(value));
  const trimSummary = value => {
    let text = clean(value);
    if (!text) return "";
    const boundary = operationBoundary(text);
    if (boundary) {
      const prefix = clean(text.slice(0, boundary.index)).replace(/[\s\-–—:;,.|]+$/g, "");
      text = prefix.length >= 40 ? prefix : "";
    }
    if (text.length < 40 || text.length > 1800 || shell(text)) return "";
    const words = text.split(/\s+/).filter(Boolean);
    if (cta(text) && (text.length < 360 || words.length < 45)) return "";
    const letters = text.replace(/[^A-Za-z]/g, "");
    const uppercase = letters.replace(/[^A-Z]/g, "").length;
    if (letters.length >= 20 && uppercase / letters.length > 0.82 && words.length < 24) return "";
    return text;
  };
  const fieldOrTaxonomy = value => /^(?:date|dates|when|time|location|venue|where|price|prices|fees?|admission|duration|language|age|ages|activities?|programmes?|programs?|events?|exhibitions?|free|ticketed|in[-\s]?museum)\b/i.test(clean(value));

  const title = clean(base.title);
  const primaryHeading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(visible) || null;
  const root = primaryHeading && primaryHeading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") || document.body;
  const allElements = Array.from(root ? root.querySelectorAll("*") : []);
  const elementIndex = new Map(allElements.map((element, index) => [element, index]));
  const headingIndex = primaryHeading && elementIndex.has(primaryHeading)
    ? elementIndex.get(primaryHeading)
    : 0;
  const sectionHeadings = Array.from(root ? root.querySelectorAll("h2,h3,h4,h5,h6") : [])
    .filter(visible);
  const operationalSection = element => {
    let previous = null;
    for (const heading of sectionHeadings) {
      if (heading === element || Boolean(heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING)) {
        previous = heading;
        continue;
      }
      break;
    }
    return previous && operationBoundary(previous.innerText || previous.textContent || "");
  };

  const rows = [];
  const push = (value, score, origin, position = 100000) => {
    const text = trimSummary(value);
    if (!text || text === title || key(text) === key(title)) return;
    const existing = rows.find(row => row.text === text);
    if (existing) {
      existing.score = Math.max(existing.score, score);
      existing.position = Math.min(existing.position, position);
      return;
    }
    rows.push({text, score, origin, position});
  };

  const structuredEvent = Array.isArray(base.eventObjects) ? base.eventObjects[0] : null;
  if (structuredEvent && typeof structuredEvent === "object") {
    push(structuredEvent.description || structuredEvent.summary, 2400, "structured_event", 0);
  }

  const narrativeLines = [];
  for (const raw of Array.isArray(base.lines) ? base.lines : []) {
    const line = clean(raw);
    if (!line || key(line) === key(title)) continue;
    if (operationBoundary(line)) break;
    if (fieldOrTaxonomy(line)) continue;
    if ((Array.isArray(base.dates) && base.dates.includes(line)) ||
        (Array.isArray(base.venues) && base.venues.includes(line))) continue;
    const trimmed = trimSummary(line);
    if (!trimmed) continue;
    narrativeLines.push(trimmed);
    if (narrativeLines.join(" ").length >= 700 || narrativeLines.length >= 3) break;
  }
  push(narrativeLines.join(" "), 1500, "activity_lines", 1);

  const selector = [
    "[itemprop='description']", "p",
    "[class*='event-description' i]", "[class*='event_description' i]",
    "[class*='programme-description' i]", "[class*='activity-description' i]",
    "[class*='description' i]", "[class*='intro' i]"
  ].join(",");
  for (const element of Array.from(root ? root.querySelectorAll(selector) : [])) {
    if (!visible(element) || operationalSection(element)) continue;
    if (element.closest(
      "nav,header,footer,aside,form,dialog," +
      "[class*='breadcrumb' i],[class*='navigation' i],[class*='footer' i]," +
      "[class*='cta' i],[class*='ticket' i],[class*='booking' i]," +
      "[class*='terms' i],[class*='condition' i],[class*='registration' i]," +
      "[class*='contact' i],[class*='safety' i],[class*='banner' i]," +
      "[class*='promo' i],[class*='share' i]"
    )) continue;
    if (element.tagName !== "P" && !element.matches("[itemprop='description']") &&
        element.querySelector("p,h2,h3,h4,h5,h6,li")) continue;

    const position = elementIndex.has(element) ? elementIndex.get(element) : 100000;
    const distance = Math.max(0, position - headingIndex);
    let score = element.matches("[itemprop='description']") ? 1800 : 1100;
    if (element.tagName === "P") score += 180;
    if (/\b(?:event-description|programme-description|activity-description|description|intro)\b/i.test(String(element.className || ""))) score += 140;
    score += Math.max(0, 420 - Math.min(distance, 420));
    const text = clean(element.innerText || element.textContent || "");
    if (text.length >= 80 && text.length <= 700) score += 120;
    if (/[.!?](?:\s|$)/.test(text)) score += 40;
    push(text, score, "detail_dom", position);
  }

  for (const value of Array.isArray(base.summary_candidates) ? base.summary_candidates : []) {
    push(value, 500, "base_candidate");
  }
  push(base.summary, 300, "base_summary");

  rows.sort((left, right) =>
    right.score - left.score || left.position - right.position || left.text.length - right.text.length
  );
  const summaryCandidates = rows.map(row => row.text);
  const summary = summaryCandidates[0] || "";
  const lines = [];
  const add = value => {
    const text = clean(value);
    if (text && !lines.includes(text)) lines.push(text);
  };
  add(title);
  if (Array.isArray(base.dates) && base.dates.length) add("Date");
  for (const value of Array.isArray(base.dates) ? base.dates : []) add(value);
  if (Array.isArray(base.venues) && base.venues.length) add("Location");
  for (const value of Array.isArray(base.venues) ? base.venues : []) add(value);
  add(summary);
  for (const value of Array.isArray(base.lines) ? base.lines : []) add(value);

  return {
    ...base,
    summary,
    summary_candidates: summaryCandidates,
    lines,
    text_lines: lines,
    text: lines.join("\n")
  };
}
"""
)


def apply() -> None:
    """Install section-aware activity-summary extraction across every entrypoint."""

    global _APPLIED
    if _APPLIED:
        return

    _detail_payload.apply()
    _detail_payload.ENRICHED_DETAIL_JS = SECTIONED_DETAIL_JS
    _detail_payload.useful_event_summary = useful_event_summary
    _detail_dates.ACTIVITY_DETAIL_JS = SECTIONED_DETAIL_JS
    _browser.DETAIL_CARD_JS = SECTIONED_DETAIL_JS
    _source_overrides.AUTHORITATIVE_DETAIL_JS = SECTIONED_DETAIL_JS

    try:
        from . import event_review as review

        review.DETAIL_CARD_JS = SECTIONED_DETAIL_JS
    except ImportError:
        pass

    try:
        from . import review_summary_authority as review_summary

        review_summary.useful_event_summary = useful_event_summary
    except ImportError:
        pass

    _APPLIED = True


__all__ = [
    "SECTIONED_DETAIL_JS",
    "apply",
    "useful_event_summary",
]
