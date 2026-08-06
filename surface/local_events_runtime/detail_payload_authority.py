from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_DETAIL_JS = _detail_dates.ACTIVITY_DETAIL_JS
_BASE_PICK_WHEN = None
_BASE_PICK_VENUE = None
_BASE_PICK_SUMMARY = None
FIELD_AUTHORITY_VERSION = "detail-provenance-v2"
_SUBVENUE_RE = re.compile(
    r"\b(?:gallery|galleries|level|room|hall|theatre|theater|foyer|atrium|"
    r"concourse|stadium|arena|auditorium|lawn|green)\b",
    re.I,
)
_SUMMARY_CTA_RE = re.compile(
    r"\b(?:book\s+(?:your\s+)?tickets?|buy\s+tickets?|book\s+now|"
    r"visit\s+.{0,100}?\s+today|plan\s+your\s+visit|find\s+out\s+more|"
    r"learn\s+more|read\s+more|explore\s+more|register\s+now|sign\s+up|"
    r"get\s+your\s+tickets?|ticket\s+information)\b",
    re.I,
)
_SUMMARY_SHELL_RE = re.compile(
    r"\b(?:privacy|cookie|newsletter|copyright|breadcrumb|navigation|"
    r"previous\s+(?:event|programme)|next\s+(?:event|programme))\b",
    re.I,
)

# The base detail extractor identifies the primary activity boundary. This wrapper
# supplements semantic date/venue fields and selects an activity description from
# structured Event data or visible content paragraphs. Site-wide metadata and CTA
# blocks are only fallbacks after structural candidates have been rejected.
ENRICHED_DETAIL_JS = rf"""
() => {{
  const base = ({_BASE_DETAIL_JS})();
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const visible = element => {{
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) !== 0 && rect.width >= 1 && rect.height >= 1;
  }};
  const rejected = value => /\b(last updated|updated on|page updated|copyright|privacy|cookie|newsletter|previous programme|next programme|previous event|next event|presale|ticket sale|registration opens?)\b/i.test(clean(value));
  const dateLike = value => /\b20\d{{2}}-\d{{1,2}}-\d{{1,2}}\b|\b\d{{1,2}}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+20\d{{2}}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s+20\d{{2}}\b/i.test(clean(value));
  const timeLike = value => /\b\d{{1,2}}(?:[.:]\d{{2}})?\s*(?:am|pm)\s*[-–—]\s*\d{{1,2}}(?:[.:]\d{{2}})?\s*(?:am|pm)\b/i.test(clean(value));
  const summaryCta = value => /\b(book\s+(?:your\s+)?tickets?|buy\s+tickets?|book\s+now|visit\s+.{{0,100}}?\s+today|plan\s+your\s+visit|find\s+out\s+more|learn\s+more|read\s+more|explore\s+more|register\s+now|sign\s+up|get\s+your\s+tickets?|ticket\s+information)\b/i.test(clean(value));
  const shellText = value => /\b(privacy|cookie|newsletter|copyright|breadcrumb|navigation|previous\s+(?:event|programme)|next\s+(?:event|programme))\b/i.test(clean(value));
  const add = (rows, value) => {{
    const text = clean(value);
    if (text && !rows.includes(text)) rows.push(text);
  }};
  const ownText = element => {{
    const clone = element.cloneNode(true);
    for (const child of Array.from(clone.children || [])) child.remove();
    const direct = clean(clone.textContent || element.getAttribute("aria-label") || "");
    if (direct) return direct;
    const full = clean(element.innerText || element.textContent || "");
    return full.length <= 80 ? full : "";
  }};
  const fieldValue = element => {{
    for (const attribute of [
      "datetime", "content", "data-date", "data-start-date", "data-end-date",
      "data-location", "data-venue", "aria-label"
    ]) {{
      const value = clean(element.getAttribute && element.getAttribute(attribute));
      if (value) return value;
    }}
    return clean(element.innerText || element.textContent || "");
  }};
  const contextRejected = element => {{
    const own = fieldValue(element);
    if (rejected(own)) return true;
    const parent = element.parentElement;
    const parentText = clean(parent ? (parent.innerText || parent.textContent || "") : "");
    return parentText.length <= 240 && rejected(parentText);
  }};
  const summaryUseful = value => {{
    const text = clean(value);
    if (text.length < 40 || text.length > 1800) return false;
    if (rejected(text) || shellText(text)) return false;
    const words = text.split(/\s+/).filter(Boolean);
    if (summaryCta(text) && (text.length < 360 || words.length < 45)) return false;
    const letters = text.replace(/[^A-Za-z]/g, "");
    const uppercase = letters.replace(/[^A-Z]/g, "").length;
    if (letters.length >= 20 && uppercase / letters.length > 0.82 && words.length < 24) return false;
    return true;
  }};

  const dates = [...(Array.isArray(base.dates) ? base.dates : [])];
  const times = [...(Array.isArray(base.times) ? base.times : [])];
  const venues = [...(Array.isArray(base.venues) ? base.venues : [])];
  const labeledDates = [];
  const labeledTimes = [];
  const labeledVenues = [];
  const structuredDates = [];
  const structuredTimes = [];
  const structuredVenues = [];
  const structuredEvent = Array.isArray(base.eventObjects) ? base.eventObjects[0] : null;
  if (structuredEvent && typeof structuredEvent === "object") {{
    const start = clean(structuredEvent.startDate || structuredEvent.start);
    const end = clean(structuredEvent.endDate || structuredEvent.end);
    add(structuredDates, start && end && start !== end ? start + " - " + end : (start || end));
    for (const value of [
      structuredEvent.doorTime,
      structuredEvent.startTime,
      structuredEvent.endTime
    ]) {{
      if (timeLike(value)) add(structuredTimes, value);
    }}
    const location = structuredEvent.location ||
      structuredEvent.venue || structuredEvent.place;
    if (typeof location === "string") {{
      add(structuredVenues, location);
    }} else if (location && typeof location === "object") {{
      add(structuredVenues, location.name || location.title);
    }}
  }}

  const dateSelectors = [
    "time[datetime]", "time", "[itemprop='startDate']", "[itemprop='endDate']",
    "[data-start-date]", "[data-end-date]", "[data-date]",
    "[class*='event-date' i]", "[class*='event_date' i]",
    "[class*='date-range' i]", "[class*='daterange' i]",
    "[class*='start-date' i]", "[class*='end-date' i]",
    "[class*='event-info' i] [class*='date' i]",
    "[class*='programme-info' i] [class*='date' i]"
  ].join(",");
  for (const element of document.querySelectorAll(dateSelectors)) {{
    if (!visible(element) || contextRejected(element)) continue;
    const value = fieldValue(element);
    if (value && dateLike(value)) add(dates, value);
  }}

  const venueSelectors = [
    "address", "[itemprop='location']", "[data-location]", "[data-venue]",
    "[class*='event-location' i]", "[class*='event_location' i]",
    "[class*='event-venue' i]", "[class*='event_venue' i]",
    "[class*='venue-name' i]", "[class*='location-name' i]",
    "[class*='event-info' i] [class*='location' i]",
    "[class*='event-info' i] [class*='venue' i]",
    "[class*='programme-info' i] [class*='location' i]"
  ].join(",");
  for (const element of document.querySelectorAll(venueSelectors)) {{
    if (!visible(element) || contextRejected(element)) continue;
    const value = fieldValue(element);
    if (value && value.length <= 220 && !dateLike(value)) add(venues, value);
  }}

  const labelHeadings = Array.from(document.querySelectorAll(
    "main h1, main h2, main h3, main h4, main h5, main h6, " +
    "article h1, article h2, article h3, article h4, article h5, article h6, " +
    "h1, h2, h3, h4, h5, h6"
  )).filter(visible);
  const normalizedHeading = value => clean(value)
    .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const expectedTitle = normalizedHeading(base.title);
  const labelHeading = labelHeadings.find(element => {{
    const candidate = normalizedHeading(element.innerText || element.textContent);
    return Boolean(candidate && expectedTitle && (
      candidate === expectedTitle ||
      candidate.includes(expectedTitle) ||
      expectedTitle.includes(candidate)
    ));
  }}) || labelHeadings[0] || null;
  const labelRoot = (labelHeading && labelHeading.closest("main")) ||
    document.querySelector("main") ||
    (labelHeading && labelHeading.closest("article")) ||
    document.querySelector("article") ||
    document.body;
  const labelElements = Array.from(labelRoot ? labelRoot.querySelectorAll("*") : []);
  const labelHeadingIndex = labelHeading ? labelElements.indexOf(labelHeading) : -1;
  const detailTail = labelElements.slice(labelHeadingIndex + 1);
  const labelBoundaryIndex = detailTail.findIndex(element =>
    visible(element) &&
    /^(?:(?:other|related)\s+events?|you\s+may\s+also\s+like)$/i.test(ownText(element))
  );
  const labels = (labelBoundaryIndex >= 0
    ? detailTail.slice(0, labelBoundaryIndex)
    : detailTail
  ).filter(visible);
  for (const label of labels) {{
    const name = ownText(label);
    const isSchedule = /^(?:opening\s+hours?|hours?)\s*:?$/i.test(name);
    const isCombinedSchedule = /^(?:event\s+)?date\s*(?:&|and)\s*time\s*:?$/i.test(name);
    const isDate = isSchedule || isCombinedSchedule ||
      /^(?:event\s+)?(?:date|dates|when)\s*:?$/i.test(name);
    const isTime = isSchedule || isCombinedSchedule ||
      /^(?:event\s+)?(?:time|times)\s*:?$/i.test(name);
    const isVenue = /^(?:location|venue|where)\s*:?$/i.test(name);
    if (!isDate && !isTime && !isVenue) continue;

    const candidates = [];
    let foundVenue = false;
    if (label.nextElementSibling) candidates.push(label.nextElementSibling);
    const parent = label.parentElement;
    if (parent) {{
      const children = Array.from(parent.children || []);
      const index = children.indexOf(label);
      candidates.push(...children.slice(index + 1, index + 5));
    }}
    for (const candidate of candidates) {{
      if (!visible(candidate) || contextRejected(candidate)) continue;
      const candidateName = ownText(candidate);
      if (/^(?:(?:event\s+)?(?:date|dates|when|time|times|date\s*(?:&|and)\s*time)|opening\s+hours?|hours?|location|venue|where)\s*:?$/i.test(candidateName)) break;
      const rows = String(candidate.innerText || candidate.textContent || "")
        .split(/\n+/).map(clean).filter(Boolean);
      if (!rows.length) rows.push(fieldValue(candidate));
      for (const value of rows) {{
        if (!value) continue;
        if (isDate && dateLike(value)) add(labeledDates, value);
        if (isTime && timeLike(value)) add(labeledTimes, value);
        if (isVenue && !dateLike(value) && !timeLike(value) && value.length <= 220) {{
          add(labeledVenues, value);
          foundVenue = true;
          break;
        }}
      }}
      if (foundVenue) break;
    }}
  }}

  const orderedDates = [];
  labeledDates.forEach(value => add(orderedDates, value));
  structuredDates.forEach(value => add(orderedDates, value));
  dates.forEach(value => add(orderedDates, value));
  const orderedTimes = [];
  labeledTimes.forEach(value => add(orderedTimes, value));
  structuredTimes.forEach(value => add(orderedTimes, value));
  times.forEach(value => add(orderedTimes, value));
  const orderedVenues = [];
  labeledVenues.forEach(value => add(orderedVenues, value));
  structuredVenues.forEach(value => add(orderedVenues, value));
  venues.forEach(value => add(orderedVenues, value));

  const title = clean(base.title);
  const primaryHeading = Array.from(document.querySelectorAll("main h1, article h1, h1"))
    .find(visible) || null;
  const summaryRoot = primaryHeading && primaryHeading.closest(
    "article, [class*='event-detail' i], [class*='eventDetail' i], " +
    "[class*='detail-page' i], [class*='content-detail' i], main"
  ) || document.querySelector("main") || document.querySelector("article") || document.body;
  const summaryRows = [];
  const pushSummary = (value, score, origin) => {{
    const text = clean(value);
    if (!summaryUseful(text) || text === title) return;
    const existing = summaryRows.find(row => row.text === text);
    if (existing) {{ existing.score = Math.max(existing.score, score); return; }}
    summaryRows.push({{text, score, origin}});
  }};

  if (structuredEvent && typeof structuredEvent === "object") {{
    pushSummary(structuredEvent.description || structuredEvent.summary, 1000, "structured_event");
  }}

  const summarySelector = [
    "[itemprop='description']", "p",
    "[class*='event-description' i]", "[class*='event_description' i]",
    "[class*='programme-description' i]", "[class*='description' i]",
    "[class*='intro' i]", "[class*='rich-text' i]", "[class*='richtext' i]"
  ].join(",");
  for (const element of Array.from(summaryRoot.querySelectorAll(summarySelector))) {{
    if (!visible(element)) continue;
    if (element.closest(
      "nav,header,footer,aside,form,dialog," +
      "[class*='breadcrumb' i],[class*='navigation' i],[class*='footer' i]," +
      "[class*='cta' i],[class*='ticket' i],[class*='booking' i]," +
      "[class*='banner' i],[class*='promo' i],[class*='share' i]"
    )) continue;
    const text = clean(element.innerText || element.textContent || "");
    let score = element.matches("[itemprop='description']") ? 900 : 600;
    if (element.tagName === "P") score += 80;
    if (/\b(?:description|intro|rich-text|richtext)\b/i.test(String(element.className || ""))) score += 50;
    if (text.length >= 80 && text.length <= 700) score += 80;
    if (/[.!?](?:\s|$)/.test(text)) score += 20;
    pushSummary(text, score, "detail_dom");
  }}

  pushSummary(base.summary, 150, "page_metadata");
  const metadataSummary = clean(document.querySelector('meta[name="description"]')?.content) ||
    clean(document.querySelector('meta[property="og:description"]')?.content);
  pushSummary(metadataSummary, 100, "page_metadata");
  summaryRows.sort((left, right) => right.score - left.score || left.text.length - right.text.length);
  const summaryCandidates = summaryRows.map(row => row.text);
  const summary = summaryCandidates[0] || "";

  const originalLines = Array.isArray(base.lines)
    ? base.lines
    : (Array.isArray(base.text_lines) ? base.text_lines : []);
  const lines = [];
  add(lines, title);
  originalLines.forEach(value => add(lines, value));
  add(lines, summary);

  return {{
    ...base,
    dates: orderedDates,
    times: orderedTimes,
    venues: orderedVenues,
    labeled_dates: labeledDates,
    labeled_times: labeledTimes,
    labeled_venues: labeledVenues,
    structured_dates: structuredDates,
    structured_times: structuredTimes,
    structured_venues: structuredVenues,
    field_authority_version: "detail-provenance-v2",
    summary,
    summary_candidates: summaryCandidates,
    lines,
    text_lines: lines,
    text: lines.join("\n")
  }};
}}
"""


def _clean_rows(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    output: list[str] = []
    for value in raw:
        text = " ".join(str(value or "").split())
        if text and text not in output:
            output.append(text)
    return output


def useful_event_summary(value: object) -> str:
    """Return a narrative activity description, never a site CTA or shell label."""

    text = _extract.clean(value)
    if len(text) < 40 or len(text) > 1800:
        return ""
    if _SUMMARY_SHELL_RE.search(text):
        return ""
    words = text.split()
    if _SUMMARY_CTA_RE.search(text) and (len(text) < 360 or len(words) < 45):
        return ""
    letters = "".join(character for character in text if character.isalpha())
    if letters:
        uppercase = sum(1 for character in letters if character.isupper())
        if uppercase / len(letters) > 0.82 and len(words) < 24:
            return ""
    return text


def _detail_rows(card: dict[str, Any], key: str, evidence_key: str) -> list[str]:
    direct = _clean_rows(card.get(key))
    evidence = card.get("detail_evidence")
    if isinstance(evidence, dict):
        for value in _clean_rows(evidence.get(evidence_key)):
            if value not in direct:
                direct.append(value)
    return direct


def _format_date(value: date) -> str:
    return f"{value.day} {value.strftime('%b')} {value.year}"


def _field_authority_enabled(card: dict[str, Any]) -> bool:
    return _extract.clean(card.get("detail_field_authority_version")) == FIELD_AUTHORITY_VERSION


def _authoritative_when(card: dict[str, Any]) -> str:
    rows = _clean_rows(card.get("detail_labeled_dates"))
    if not rows:
        rows = _clean_rows(card.get("detail_structured_dates"))
    if not rows and not _field_authority_enabled(card):
        rows = _detail_rows(card, "detail_dates", "date_candidates")
    if not rows:
        return ""

    dated: list[tuple[str, list[date]]] = []
    all_dates: list[date] = []
    for row in rows:
        parsed = _extract.label_dates(row)
        if not parsed:
            continue
        dated.append((row, parsed))
        for item in parsed:
            if item not in all_dates:
                all_dates.append(item)

    selected = ""
    ranges = [item for item in dated if len(item[1]) >= 2]
    if ranges:
        ranges.sort(key=lambda item: (-len(item[1]), len(item[0])))
        selected = ranges[0][0]
    elif len(all_dates) >= 2:
        start, end = min(all_dates), max(all_dates)
        selected = f"{_format_date(start)} – {_format_date(end)}"
    elif dated:
        selected = dated[0][0]

    times = _clean_rows(card.get("detail_labeled_times"))
    if not times:
        times = _clean_rows(card.get("detail_structured_times"))
    if not times and not _field_authority_enabled(card):
        times = _detail_rows(card, "detail_times", "time_candidates")
    time = next((value for value in times if _extract.TIME_RE.search(value)), "")
    if selected and time and time not in selected:
        return f"{selected} · {time}"
    return selected


def _authoritative_venue(card: dict[str, Any]) -> str:
    rows = _clean_rows(card.get("detail_labeled_venues"))
    if not rows:
        rows = _clean_rows(card.get("detail_structured_venues"))
    if not rows and not _field_authority_enabled(card):
        rows = _detail_rows(card, "detail_venues", "venue_candidates")
    valid = [
        row
        for row in rows
        if _detail_dates._valid_labeled_venue(row)
    ]
    if not valid:
        return ""
    valid.sort(
        key=lambda value: (
            0 if _SUBVENUE_RE.search(value) else 1,
            len(value),
        )
    )
    return valid[0]


def _authoritative_summary(card: dict[str, Any]) -> str:
    candidates = [
        *_clean_rows(card.get("detail_summary_candidates")),
        _extract.clean(card.get("detail_summary")),
    ]
    evidence = card.get("detail_evidence")
    if isinstance(evidence, dict):
        candidates.extend(_clean_rows(evidence.get("summary_candidates")))
        candidates.append(_extract.clean(evidence.get("summary")))
    for candidate in candidates:
        summary = useful_event_summary(candidate)
        if summary:
            return summary
    return ""


def _pick_when(card: dict[str, Any]) -> tuple[str, str]:
    value = _authoritative_when(card)
    if value:
        return _extract.short(value, 180), value
    if _field_authority_enabled(card):
        return "", ""
    return _BASE_PICK_WHEN(card)


def _pick_venue(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    when_line: str,
) -> str:
    value = _authoritative_venue(card)
    if value:
        return value
    if _field_authority_enabled(card):
        return ""
    return _BASE_PICK_VENUE(source, card, when, when_line)


def _pick_summary(
    card: dict[str, Any],
    title: str,
    when: str,
    where: str,
) -> str:
    value = _authoritative_summary(card)
    if value:
        return _extract.short(value, 260)
    fallback = useful_event_summary(_BASE_PICK_SUMMARY(card, title, when, where))
    return _extract.short(fallback, 260) if fallback else "Open the official page for details."


def merge_detail_payload(
    card: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Merge authoritative detail fields into the parser's ordered evidence."""

    if not isinstance(detail, dict):
        return dict(card)

    merged = dict(card)
    title = " ".join(str(detail.get("title") or "").split())
    dates = _clean_rows(detail.get("dates"))
    times = _clean_rows(detail.get("times"))
    venues = _clean_rows(detail.get("venues"))
    labeled_dates = _clean_rows(detail.get("labeled_dates"))
    labeled_times = _clean_rows(detail.get("labeled_times"))
    labeled_venues = _clean_rows(detail.get("labeled_venues"))
    structured_dates = _clean_rows(detail.get("structured_dates"))
    structured_times = _clean_rows(detail.get("structured_times"))
    structured_venues = _clean_rows(detail.get("structured_venues"))
    authority_version = _extract.clean(detail.get("field_authority_version"))
    trusted_dates = [*labeled_dates, *(value for value in structured_dates if value not in labeled_dates)]
    trusted_times = [*labeled_times, *(value for value in structured_times if value not in labeled_times)]
    trusted_venues = [*labeled_venues, *(value for value in structured_venues if value not in labeled_venues)]
    dates = [*trusted_dates, *(value for value in dates if value not in trusted_dates)]
    times = [*trusted_times, *(value for value in times if value not in trusted_times)]
    venues = [*trusted_venues, *(value for value in venues if value not in trusted_venues)]
    summary_candidates = _clean_rows(detail.get("summary_candidates"))
    summary = useful_event_summary(detail.get("summary"))
    if summary and summary not in summary_candidates:
        summary_candidates.insert(0, summary)
    if not summary:
        summary = next(
            (value for value in summary_candidates if useful_event_summary(value)),
            "",
        )
    detail_lines = _clean_rows(detail.get("lines") or detail.get("text_lines"))
    if not detail_lines:
        detail_lines = [
            " ".join(line.split())
            for line in str(detail.get("text") or "").splitlines()
            if " ".join(line.split())
        ]

    ordered: list[str] = []
    if authority_version == FIELD_AUTHORITY_VERSION:
        field_values = [title, *detail_lines, summary]
    else:
        field_values = [title]
        if dates:
            field_values.extend(["Date", *dates])
        if times:
            field_values.extend(["Time", *times])
        if venues:
            field_values.extend(["Location", *venues])
        field_values.extend([summary, *detail_lines])
    for value in field_values:
        text = " ".join(str(value or "").split())
        if text and text not in ordered:
            ordered.append(text)

    if not ordered:
        return merged

    headings = _clean_rows(detail.get("headings"))
    if title and title not in headings:
        headings.insert(0, title)
    image_alts = _clean_rows(detail.get("image_alts"))

    merged["text"] = "\n".join(ordered)
    merged["text_lines"] = ordered
    if headings:
        merged["headings"] = headings
        merged["link_text"] = headings[0]
    elif title:
        merged["headings"] = [title]
        merged["link_text"] = title
    if image_alts:
        merged["image_alts"] = image_alts

    merged["detail_dates"] = dates
    merged["detail_times"] = times
    merged["detail_venues"] = venues
    merged["detail_labeled_dates"] = labeled_dates
    merged["detail_labeled_times"] = labeled_times
    merged["detail_labeled_venues"] = labeled_venues
    merged["detail_structured_dates"] = structured_dates
    merged["detail_structured_times"] = structured_times
    merged["detail_structured_venues"] = structured_venues
    merged["detail_field_authority_version"] = authority_version
    merged["detail_summary"] = summary
    merged["detail_summary_candidates"] = summary_candidates
    merged["detail_event_objects"] = detail.get("eventObjects") or []
    merged["detail_canonical"] = str(detail.get("canonical") or "")
    merged["detail_enriched"] = True
    merged["extraction_mode"] = (
        f"{card.get('extraction_mode') or 'card'}+authoritative_detail"
    )
    return merged


def apply() -> None:
    """Install field-preserving detail extraction for Review and formal collection."""

    global _APPLIED, _BASE_PICK_WHEN, _BASE_PICK_VENUE, _BASE_PICK_SUMMARY
    if _APPLIED:
        return

    _detail_dates.apply()
    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_PICK_VENUE = _extract.pick_venue
    _BASE_PICK_SUMMARY = _extract.pick_summary

    _detail_dates.ACTIVITY_DETAIL_JS = ENRICHED_DETAIL_JS
    _browser.DETAIL_CARD_JS = ENRICHED_DETAIL_JS
    _browser.merge_detail_payload = merge_detail_payload
    _source_overrides.AUTHORITATIVE_DETAIL_JS = ENRICHED_DETAIL_JS
    _extract.pick_when = _pick_when
    _extract.pick_venue = _pick_venue
    _extract.pick_summary = _pick_summary

    try:
        from . import event_review as review

        review.DETAIL_CARD_JS = ENRICHED_DETAIL_JS
        review.merge_detail_payload = merge_detail_payload
    except ImportError:
        pass

    _APPLIED = True


__all__ = [
    "ENRICHED_DETAIL_JS",
    "apply",
    "merge_detail_payload",
    "useful_event_summary",
    "FIELD_AUTHORITY_VERSION",
    "_authoritative_summary",
    "_authoritative_venue",
    "_authoritative_when",
    "_field_authority_enabled",
]
