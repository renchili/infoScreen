from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_DETAIL_JS = _detail_dates.ACTIVITY_DETAIL_JS

# The base detail extractor already identifies the primary activity and excludes
# page metadata. This wrapper supplements it with semantic DOM fields used by NHB
# pages, then puts dates, venue, and description into the same ordered text payload
# consumed by event_from_card().
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
  const add = (rows, value) => {{
    const text = clean(value);
    if (text && !rows.includes(text)) rows.push(text);
  }};
  const ownText = element => {{
    const clone = element.cloneNode(true);
    for (const child of Array.from(clone.children || [])) child.remove();
    return clean(clone.textContent || element.getAttribute("aria-label") || "");
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

  const dates = [...(Array.isArray(base.dates) ? base.dates : [])];
  const venues = [...(Array.isArray(base.venues) ? base.venues : [])];

  const dateSelectors = [
    "time[datetime]", "time", "[itemprop='startDate']", "[itemprop='endDate']",
    "[data-start-date]", "[data-end-date]", "[data-date]",
    "[class*='event-date' i]", "[class*='event_date' i]",
    "[class*='date-range' i]", "[class*='daterange' i]",
    "[class*='start-date' i]", "[class*='end-date' i]"
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
    "[class*='venue-name' i]", "[class*='location-name' i]"
  ].join(",");
  for (const element of document.querySelectorAll(venueSelectors)) {{
    if (!visible(element) || contextRejected(element)) continue;
    const value = fieldValue(element);
    if (value && value.length <= 220 && !dateLike(value)) add(venues, value);
  }}

  const labels = Array.from(document.querySelectorAll("main *, article *")).filter(visible);
  for (const label of labels) {{
    const name = ownText(label);
    const isDate = /^(?:event\s+)?(?:date|dates|when)\s*:?$/i.test(name);
    const isVenue = /^(?:location|venue|where)\s*:?$/i.test(name);
    if (!isDate && !isVenue) continue;

    const candidates = [];
    if (label.nextElementSibling) candidates.push(label.nextElementSibling);
    const parent = label.parentElement;
    if (parent) {{
      const children = Array.from(parent.children || []);
      const index = children.indexOf(label);
      candidates.push(...children.slice(index + 1, index + 4));
    }}
    for (const candidate of candidates) {{
      if (!visible(candidate) || contextRejected(candidate)) continue;
      const value = fieldValue(candidate);
      if (!value) continue;
      if (isDate && dateLike(value)) {{ add(dates, value); break; }}
      if (isVenue && !dateLike(value) && value.length <= 220) {{ add(venues, value); break; }}
    }}
  }}

  const title = clean(base.title);
  const summary = clean(base.summary);
  const originalLines = Array.isArray(base.lines)
    ? base.lines
    : (Array.isArray(base.text_lines) ? base.text_lines : []);
  const lines = [];
  add(lines, title);
  dates.forEach(value => add(lines, value));
  venues.forEach(value => add(lines, value));
  add(lines, summary);
  originalLines.forEach(value => add(lines, value));

  return {{
    ...base,
    dates,
    venues,
    summary,
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


def merge_detail_payload(
    card: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Merge every authoritative detail field into the parser's ordered evidence."""

    if not isinstance(detail, dict):
        return dict(card)

    merged = dict(card)
    title = " ".join(str(detail.get("title") or "").split())
    dates = _clean_rows(detail.get("dates"))
    venues = _clean_rows(detail.get("venues"))
    summary = " ".join(str(detail.get("summary") or "").split())
    detail_lines = _clean_rows(detail.get("lines") or detail.get("text_lines"))
    if not detail_lines:
        detail_lines = [
            " ".join(line.split())
            for line in str(detail.get("text") or "").splitlines()
            if " ".join(line.split())
        ]

    ordered: list[str] = []
    for value in [title, *dates, *venues, summary, *detail_lines]:
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
    merged["detail_venues"] = venues
    merged["detail_summary"] = summary
    merged["detail_event_objects"] = detail.get("eventObjects") or []
    merged["detail_canonical"] = str(detail.get("canonical") or "")
    merged["detail_enriched"] = True
    merged["extraction_mode"] = (
        f"{card.get('extraction_mode') or 'card'}+authoritative_detail"
    )
    return merged


def apply() -> None:
    """Install field-preserving detail extraction for Review and formal collection."""

    global _APPLIED
    if _APPLIED:
        return

    _detail_dates.ACTIVITY_DETAIL_JS = ENRICHED_DETAIL_JS
    _browser.DETAIL_CARD_JS = ENRICHED_DETAIL_JS
    _browser.merge_detail_payload = merge_detail_payload
    _source_overrides.AUTHORITATIVE_DETAIL_JS = ENRICHED_DETAIL_JS

    try:
        from . import event_review as review

        review.DETAIL_CARD_JS = ENRICHED_DETAIL_JS
        review.merge_detail_payload = merge_detail_payload
    except ImportError:
        pass

    _APPLIED = True


__all__ = ["ENRICHED_DETAIL_JS", "apply", "merge_detail_payload"]
