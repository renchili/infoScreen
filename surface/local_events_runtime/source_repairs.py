from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds

_APPLIED = False

NON_EVENT_PATH_SEGMENT_RE = re.compile(
    r"^(?:plan-your-itinerary|visitor-information|museum-map|accessibility|group-visits|getting-here|"
    r"shop-dine-relax|venue-rental|filming-photography|contact-us|image-requests|book-a-venue|"
    r"amenities-services|opening-hours-closures|itinerary-planner|gardens-map|information-guides|"
    r"visiting-guidelines|mobile-apps-travel-guide|privacy|terms-of-use|about-us)$",
    re.I,
)
SYNTHETIC_FRAGMENT_RE = re.compile(r"#(?:nhb(?:-json)?|structured)-", re.I)
OPEN_ENDED_RE = re.compile(r"\b(?:ongoing|permanent|from|since)\b", re.I)
DATEISH_RE = re.compile(
    r"\b20\d{2}\b|\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|"
    r"jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
    re.I,
)

_DETAIL_CARD_JS = r"""
() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const rawText = (value) => String(value || "").replace(/\r/g, "\n");
  const root = document.querySelector("main") || document.querySelector("article") || document.body;

  function scalar(value) {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    if (Array.isArray(value)) return clean(value.map(scalar).filter(Boolean).join(" "));
    if (typeof value === "object") {
      for (const key of ["name", "title", "label", "value", "text", "address", "streetAddress"]) {
        if (value[key] != null) {
          const text = scalar(value[key]);
          if (text) return text;
        }
      }
    }
    return "";
  }

  function eventType(value) {
    const values = Array.isArray(value) ? value : [value];
    return values.some(item => /(?:^|\b)(?:event|festival|exhibition|course|screening)(?:\b|$)/i.test(String(item || "")));
  }

  function findJsonEvent(value, depth = 0) {
    if (value == null || depth > 12) return null;
    if (Array.isArray(value)) {
      for (const child of value) {
        const found = findJsonEvent(child, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof value !== "object") return null;
    if (eventType(value["@type"] || value.type)) return value;
    for (const child of Object.values(value)) {
      const found = findJsonEvent(child, depth + 1);
      if (found) return found;
    }
    return null;
  }

  let structured = null;
  for (const script of Array.from(document.querySelectorAll("script[type='application/ld+json'], script[type*='json']"))) {
    const raw = String(script.textContent || "").trim();
    if (!raw || raw.length > 1500000) continue;
    try {
      structured = findJsonEvent(JSON.parse(raw));
    } catch (e) {}
    if (structured) break;
  }

  function locationText(value) {
    if (!value) return "";
    if (typeof value === "string") return clean(value);
    if (Array.isArray(value)) return clean(value.map(locationText).filter(Boolean).join(", "));
    if (typeof value === "object") {
      const parts = [
        scalar(value.name),
        scalar(value.address && value.address.name),
        scalar(value.address && value.address.streetAddress),
        scalar(value.address && value.address.addressLocality),
      ].filter(Boolean);
      return clean(Array.from(new Set(parts)).join(", "));
    }
    return "";
  }

  let lines = rawText(root ? (root.innerText || root.textContent || "") : "")
    .split("\n")
    .map(clean)
    .filter(Boolean);

  const stopAt = lines.findIndex(line => /^(?:other events?|explore more|recommended for you|you may also like|related events?|past events?)$/i.test(line));
  if (stopAt > 0) lines = lines.slice(0, stopAt);

  const ogTitle = clean(document.querySelector("meta[property='og:title']")?.getAttribute("content"));
  const headingTitle = Array.from(document.querySelectorAll("main h1, article h1, h1, main h2, article h2"))
    .map(el => clean(el.innerText || el.textContent))
    .find(text => text && !/^(?:what'?s on|calendar of events|events?|exhibitions?|programmes?)$/i.test(text));
  let title = scalar(structured && (structured.name || structured.headline)) || headingTitle || ogTitle || clean(document.title);
  title = title.replace(/\s+[|–—-]\s+(?:National Gallery Singapore|Gardens by the Bay|Science Centre Singapore|National Museum of Singapore|Sentosa)$/i, "").trim();

  const labelStops = new Set([
    "date", "date & time", "date and time", "event date", "opening hours", "time", "location", "venue", "where",
    "admission", "admission fee", "ticket price", "cost", "perfect for", "recommended time", "programme fee",
  ]);

  function afterLabel(labels, predicate) {
    const wanted = new Set(labels.map(value => value.toLowerCase()));
    for (let index = 0; index < lines.length; index += 1) {
      const lower = lines[index].toLowerCase().replace(/:$/, "");
      if (!wanted.has(lower)) continue;
      const values = [];
      for (let offset = index + 1; offset < Math.min(lines.length, index + 7); offset += 1) {
        const candidate = lines[offset];
        const candidateLower = candidate.toLowerCase().replace(/:$/, "");
        if (labelStops.has(candidateLower)) break;
        if (predicate(candidate)) values.push(candidate);
        else if (values.length) break;
      }
      if (values.length) return clean(values.join(" "));
    }
    return "";
  }

  const dateish = (value) => /\b20\d{2}\b|\b(?:ongoing|permanent)\b|\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i.test(value)
    && !/last admission|copyright|updated/i.test(value);
  const locationish = (value) => value.length <= 180
    && !dateish(value)
    && !/^(?:free|admission|ticket|buy tickets?|find out more|read more)$/i.test(value);

  let dateText = scalar(structured && (structured.startDate || structured.startTime));
  const structuredEnd = scalar(structured && (structured.endDate || structured.endTime));
  if (dateText && structuredEnd && structuredEnd !== dateText) dateText = `${dateText} - ${structuredEnd}`;
  if (!dateText) {
    dateText = afterLabel(["Date & Time", "Date and Time", "Date", "Event Date", "Opening Hours", "When"], dateish);
  }
  if (!dateText) {
    dateText = lines.slice(0, 60).find(dateish) || "";
  }

  let location = locationText(structured && structured.location);
  if (!location) {
    for (const line of lines.slice(0, 80)) {
      const match = line.match(/^(?:location|venue|where)\s*:\s*(.+)$/i);
      if (match && locationish(match[1])) {
        location = clean(match[1]);
        break;
      }
    }
  }
  if (!location) {
    location = afterLabel(["Location", "Venue", "Where"], locationish);
  }

  const structuredSummary = scalar(structured && structured.description);
  let summary = structuredSummary;
  if (!summary && title) {
    const titleIndex = lines.findIndex(line => clean(line).toLowerCase() === clean(title).toLowerCase());
    const scan = lines.slice(titleIndex >= 0 ? titleIndex + 1 : 0, titleIndex >= 0 ? titleIndex + 10 : 20);
    summary = scan.find(line => line.length >= 35 && !dateish(line) && !labelStops.has(line.toLowerCase().replace(/:$/, ""))) || "";
  }

  const textLines = [title, dateText, location, summary, ...lines].filter(Boolean);
  const deduped = [];
  const seen = new Set();
  for (const line of textLines) {
    const key = clean(line).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(clean(line));
  }

  return {
    title,
    date_text: dateText,
    location,
    start_date: scalar(structured && structured.startDate),
    end_date: scalar(structured && structured.endDate),
    summary,
    text: deduped.slice(0, 120).join("\n"),
    text_lines: deduped.slice(0, 120),
    headings: title ? [title] : [],
    image_alts: Array.from(document.querySelectorAll("main img[alt], article img[alt], img[alt]"))
      .map(img => clean(img.getAttribute("alt")))
      .filter(Boolean)
      .slice(0, 8),
  };
}
"""

_PREPARE_PAGE_JS = r"""
async (args) => {
  const maxRounds = Number(args.maxRounds || 0);
  const waitMs = Number(args.waitMs || 850);
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 40 && r.height >= 20;
  }

  function clickableText(el) {
    return String(el.innerText || el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
  }

  function contentState() {
    const selectors = "article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]";
    return {
      height: document.body.scrollHeight,
      count: document.querySelectorAll(selectors).length,
      textLength: String(document.body.innerText || "").length,
    };
  }

  let clicks = 0;
  let stableRounds = 0;
  let previous = contentState();

  for (let round = 0; round < maxRounds; round += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(waitMs);

    const controls = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs)\b/i.test(clickableText(el)));

    if (controls.length) {
      try {
        controls[0].scrollIntoView({block: "center"});
        await sleep(180);
        controls[0].click();
        clicks += 1;
        await sleep(waitMs);
      } catch (e) {}
    }

    const current = contentState();
    const changed = current.height > previous.height + 20
      || current.count > previous.count
      || current.textLength > previous.textLength + 50;
    stableRounds = changed ? 0 : stableRounds + 1;
    previous = current;
    if (!controls.length && stableRounds >= 2) break;
  }

  window.scrollTo(0, 0);
  await sleep(180);
  return {...previous, clicks, stableRounds};
}
"""


def _segments(url: object) -> list[str]:
    return [segment.lower() for segment in urlparse(_extract.clean(url)).path.split("/") if segment]


def _known_non_event_url(url: object) -> bool:
    return any(NON_EVENT_PATH_SEGMENT_RE.fullmatch(segment) for segment in _segments(url))


def _source_excluded_url(source: dict[str, Any], url: object) -> bool:
    text = _extract.clean(url).lower()
    return any(str(pattern).lower() in text for pattern in source.get("exclude_url_patterns") or [])


def _canonical_detail_url(url: object) -> bool:
    text = _extract.clean(url)
    if not text.startswith(("http://", "https://")) or SYNTHETIC_FRAGMENT_RE.search(text):
        return False
    if _known_non_event_url(text):
        return False
    path = urlparse(text).path.rstrip("/")
    leaf = path.split("/")[-1].lower().removesuffix(".html")
    if leaf in {"", "whats-on", "whatson", "overview", "view-all", "events", "event", "exhibitions", "exhibition", "programmes", "programs", "activities", "activity"}:
        return False
    return True


def _patch_card_js(value: str) -> str:
    old_generic = 'const generic = new Set(["", "whats-on", "whatson", "overview", "view-all", "events", "event", "exhibition", "exhibitions", "programme", "programmes", "program", "programs", "activities", "activity", "guided-tours"]);'
    new_generic = 'const generic = new Set(["", "whats-on", "whatson", "overview", "view-all", "events", "event", "exhibition", "exhibitions", "programme", "programmes", "program", "programs", "activities", "activity", "guided-tours", "plan-your-itinerary", "visitor-information", "museum-map", "accessibility", "group-visits", "getting-here", "shop-dine-relax", "venue-rental", "filming-photography", "contact-us", "image-requests"]);'
    value = value.replace(old_generic, new_generic)
    old_loop = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new_loop = 'for (const a of [...(el.matches("a[href]") ? [el] : []), ...Array.from(el.querySelectorAll("a[href]"))]) {'
    return value.replace(old_loop, new_loop)


def _parse_iso(value: object) -> date | None:
    text = _extract.clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _detail_dates(card: dict[str, Any]) -> tuple[date | None, date | None, str]:
    detail_when = _extract.clean(card.get("detail_when"))
    start = _parse_iso(card.get("detail_start_date"))
    end = _parse_iso(card.get("detail_end_date"))
    parsed = _extract.label_dates(detail_when)
    if not start and parsed:
        start = min(parsed)
    if not end and parsed:
        end = max(parsed)
    return start, end, detail_when


def _valid_detail_title(value: object) -> str:
    title = _extract.normalise_title(value)
    if not title or _extract.GENERIC_TITLE_RE.match(title) or _extract.FAKE_TITLE_RE.match(title):
        return ""
    if _extract.DATE_LINE_RE.search(title):
        return ""
    return _extract.short(title, 140)


def _valid_detail_venue(value: object) -> str:
    venue = _extract.clean(value)
    if not venue or len(venue) > 180 or _extract.DATE_LINE_RE.search(venue) or _extract.TIME_RE.search(venue):
        return ""
    if venue.lower() in {"location", "venue", "where", "admission", "date", "date & time"}:
        return ""
    return _extract.short(venue, 180)


def _merge_detail_payload(card: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(card)
    detail_text = _extract.clean(detail.get("text"))
    if detail_text:
        merged["text"] = str(detail.get("text") or "")
        merged["text_lines"] = detail.get("text_lines") or str(detail.get("text") or "").splitlines()
        merged["detail_enriched"] = True
        merged["extraction_mode"] = f"{card.get('extraction_mode') or 'card'}+authoritative_detail"

    title = _valid_detail_title(detail.get("title"))
    when = _extract.clean(detail.get("date_text"))
    where = _valid_detail_venue(detail.get("location"))
    summary = _extract.clean(detail.get("summary"))
    start = _parse_iso(detail.get("start_date"))
    end = _parse_iso(detail.get("end_date"))

    if title:
        merged["detail_title"] = title
        merged["headings"] = [title, *[item for item in merged.get("headings") or [] if _extract.norm_key(item) != _extract.norm_key(title)]]
        merged["link_text"] = title
    if when:
        merged["detail_when"] = when
    if where:
        merged["detail_where"] = where
    if summary:
        merged["detail_summary"] = summary
    if start:
        merged["detail_start_date"] = start.isoformat()
    if end:
        merged["detail_end_date"] = end.isoformat()

    structured = merged.get("structured_event")
    if isinstance(structured, dict):
        structured = dict(structured)
        if title:
            structured["title"] = title
        if start or end:
            start_value = start or end
            end_value = end or start
            structured["when"] = _official_feeds.format_date_range(start_value, end_value, when)
            structured["start_date"] = start_value.isoformat() if start_value else ""
            structured["end_date"] = end_value.isoformat() if end_value else ""
        elif when:
            structured["when"] = when
        if where:
            structured["where"] = where
        if summary:
            structured["summary"] = summary
        if _canonical_detail_url(merged.get("url")):
            structured["url"] = merged["url"]
        merged["structured_event"] = structured
    return merged


def _force_detail_enrichment(source: dict[str, Any], cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not source.get("detail_enrichment"):
        return cards
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return cards

    limit = max(0, int(source.get("detail_limit", 24)))
    timeout_ms = int(source.get("detail_timeout_ms", _browser.NHB_DETAIL_TIMEOUT_MS))
    force_all = bool(source.get("detail_authoritative"))
    enriched: list[dict[str, Any]] = []
    reads = 0

    try:
        playwright_context = sync_playwright()
        playwright = playwright_context.__enter__()
        browser = _browser.launch_chromium(playwright)
    except Exception:
        return cards

    try:
        try:
            for card in cards:
                url = _extract.clean(card.get("url"))
                needs_detail = force_all or not _browser.card_has_date(card) or not _valid_detail_venue(card.get("detail_where"))
                if reads >= limit or not needs_detail or not _canonical_detail_url(url):
                    enriched.append(card)
                    continue
                page = None
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    except Exception:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(650)
                    payload = page.evaluate(_browser.DETAIL_CARD_JS)
                    reads += 1
                    enriched.append(_merge_detail_payload(card, payload or {}))
                except Exception as exc:
                    failed = dict(card)
                    failed["detail_enrich_error"] = f"{type(exc).__name__}:{exc}"
                    enriched.append(failed)
                finally:
                    if page is not None:
                        try:
                            page.close()
                        except Exception:
                            pass
        finally:
            browser.close()
    finally:
        playwright_context.__exit__(None, None, None)
    return enriched


def _repair_structured_card_url(structured_card: dict[str, Any], dom_card: dict[str, Any]) -> dict[str, Any]:
    canonical = _extract.clean(dom_card.get("url"))
    if not _canonical_detail_url(canonical):
        return structured_card
    repaired = dict(structured_card)
    repaired["url"] = canonical
    repaired["page_url"] = canonical
    structured = repaired.get("structured_event")
    if isinstance(structured, dict):
        structured = dict(structured)
        structured["url"] = canonical
        repaired["structured_event"] = structured
    return repaired


def _prefer_structured_cards(structured_cards: list[dict[str, Any]], dom_cards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    dom_by_title: dict[str, dict[str, Any]] = {}
    for card in dom_cards:
        title = _official_feeds.card_title(card)
        if title and title not in dom_by_title:
            dom_by_title[title] = card

    merged: list[dict[str, Any]] = []
    structured_titles: set[str] = set()
    for card in structured_cards:
        title = _official_feeds.card_title(card)
        structured_titles.add(title)
        if title and title in dom_by_title:
            card = _repair_structured_card_url(card, dom_by_title[title])
        merged.append(card)
        if len(merged) >= limit:
            return merged[:limit]

    for card in dom_cards:
        title = _official_feeds.card_title(card)
        if title and title in structured_titles:
            continue
        merged.append(card)
        if len(merged) >= limit:
            break
    return merged[:limit]


def _event_looks_wrong(base, source: dict[str, Any], card: dict[str, Any], title: str, when: str) -> str:
    reason = base(source, card, title, when)
    if reason:
        return reason
    url = card.get("url") or ""
    if _known_non_event_url(url) or _source_excluded_url(source, url):
        return "non_event_information_page"
    if NON_EVENT_PATH_SEGMENT_RE.fullmatch(_extract.norm_key(title).replace(" ", "-")):
        return "non_event_information_title"
    return ""


def _event_from_card(base, source: dict[str, Any], card: dict[str, Any]):
    working = dict(card)
    detail_title = _valid_detail_title(working.get("detail_title"))
    detail_when = _extract.clean(working.get("detail_when"))
    detail_where = _valid_detail_venue(working.get("detail_where"))
    detail_summary = _extract.clean(working.get("detail_summary"))

    if detail_title:
        working["headings"] = [detail_title, *[item for item in working.get("headings") or [] if _extract.norm_key(item) != _extract.norm_key(detail_title)]]
        working["link_text"] = detail_title
    prefix = [detail_title, detail_when, detail_where, detail_summary]
    if any(prefix):
        existing_lines = working.get("text_lines") or _extract.lines(working.get("text") or "")
        working["text_lines"] = [item for item in prefix if item] + list(existing_lines)
        working["text"] = "\n".join(str(item) for item in working["text_lines"] if str(item).strip())

    event, reason = base(source, working)
    if not event:
        return event, reason
    if _known_non_event_url(event.get("url")) or _source_excluded_url(source, event.get("url")):
        return None, "non_event_information_page"

    repaired = dict(event)
    if detail_title:
        repaired["title"] = detail_title

    start, end, detail_label = _detail_dates(working)
    if start or end:
        start_value = start or end
        end_value = end or start
        if end_value and end_value < _extract.TODAY:
            return None, "past_date"
        repaired["when"] = _official_feeds.format_date_range(start_value, end_value, detail_label)
        repaired["start_date"] = start_value.isoformat() if start_value else repaired.get("start_date", "")
        repaired["end_date"] = end_value.isoformat() if end_value else ""
    elif detail_label:
        parsed = _extract.label_dates(detail_label)
        if parsed and max(parsed) < _extract.TODAY:
            return None, "past_date"
        repaired["when"] = detail_label

    if detail_where:
        repaired["where"] = detail_where
    if detail_summary:
        repaired["summary"] = detail_summary
    return repaired, reason


def _render_listing_cards(base, source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 60):
    source_max_cards = max(max_cards, int(source.get("max_cards", max_cards)))
    rendered = base(source, url, debug_dir, max_cards=source_max_cards)
    cards = rendered.get("cards") or []
    if source.get("detail_enrichment") and cards:
        rendered = dict(rendered)
        rendered["cards"] = _force_detail_enrichment(source, cards)
        rendered["detail_enrichment"] = {
            "enabled": True,
            "authoritative": bool(source.get("detail_authoritative")),
            "limit": int(source.get("detail_limit", 24)),
        }
    return rendered


def apply_source_repairs() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    package = sys.modules.get(__package__)
    base_collect = getattr(package, "collect_events") if package is not None else None
    base_event_looks_wrong = _extract.event_looks_wrong
    base_event_from_card = _extract.event_from_card
    base_render_listing_cards = _extract.render_listing_cards

    _browser.CARD_JS = _patch_card_js(_browser.CARD_JS)
    _browser.CLICK_NEXT_PAGE_JS = _patch_card_js(_browser.CLICK_NEXT_PAGE_JS)
    _browser.PREPARE_PAGE_JS = _PREPARE_PAGE_JS
    _browser.DETAIL_CARD_JS = _DETAIL_CARD_JS
    _extract.PAST_GRACE_DAYS = 0
    _extract.MAX_EVENTS_PER_SOURCE = max(_extract.MAX_EVENTS_PER_SOURCE, 60)
    _extract.SOURCE_TIMEOUT_SECONDS = max(_extract.SOURCE_TIMEOUT_SECONDS, 160)
    _official_feeds.prefer_structured_cards = _prefer_structured_cards
    _extract.event_looks_wrong = lambda source, card, title, when: _event_looks_wrong(base_event_looks_wrong, source, card, title, when)
    _extract.event_from_card = lambda source, card: _event_from_card(base_event_from_card, source, card)
    _extract.render_listing_cards = lambda source, url, debug_dir, max_cards=60: _render_listing_cards(base_render_listing_cards, source, url, debug_dir, max_cards)

    if package is not None:
        package.event_from_card = _extract.event_from_card
        if callable(base_collect):
            def collect_events(*args, **kwargs):
                payload = dict(base_collect(*args, **kwargs))
                payload["version"] = 50
                payload["extractor"] = "structured-first-v50-source-repairs"
                return payload
            package.collect_events = collect_events


__all__ = ["apply_source_repairs"]
