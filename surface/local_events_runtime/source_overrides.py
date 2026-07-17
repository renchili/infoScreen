from __future__ import annotations

import re
import sys
from datetime import date
from typing import Any
from urllib.parse import urlparse

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds

NON_EVENT_PATH_SEGMENTS = {
    "plan-your-itinerary",
    "visitor-information",
    "museum-map",
    "accessibility",
    "group-visits",
    "getting-here",
    "shop-dine-relax",
    "venue-rental",
    "filming-photography",
    "contact-us",
    "image-requests",
    "book-a-venue",
    "amenities-services",
    "opening-hours-closures",
    "itinerary-planner",
    "gardens-map",
    "information-guides",
    "visiting-guidelines",
    "mobile-apps-travel-guide",
}
SYNTHETIC_URL_RE = re.compile(r"#(?:nhb(?:-json)?|structured)-", re.I)
GENERIC_DETAIL_LEAVES = {
    "",
    "whats-on",
    "whatson",
    "overview",
    "view-all",
    "events",
    "event",
    "exhibitions",
    "exhibition",
    "programmes",
    "programme",
    "programs",
    "program",
    "activities",
    "activity",
}

_applied = False
_base_render_listing_cards = None
_base_event_from_card = None
_base_event_looks_wrong = None
_base_collect_events = None


DEEP_SCROLL_JS = r"""
async (args) => {
  const maxRounds = Number(args.maxRounds || 0);
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 40 && r.height >= 20;
  }

  function text(el) {
    return String(el.innerText || el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
  }

  function state() {
    const selectors = "article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]";
    return {
      height: document.body.scrollHeight,
      cards: document.querySelectorAll(selectors).length,
      textLength: String(document.body.innerText || "").length,
    };
  }

  let clicks = 0;
  let stableRounds = 0;
  let previous = state();

  for (let round = 0; round < maxRounds; round += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(900);

    const controls = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs)\b/i.test(text(el)));

    if (controls.length) {
      try {
        controls[0].scrollIntoView({block: "center"});
        await sleep(180);
        controls[0].click();
        clicks += 1;
        await sleep(900);
      } catch (e) {}
    }

    const current = state();
    const changed = current.height > previous.height + 20
      || current.cards > previous.cards
      || current.textLength > previous.textLength + 50;
    stableRounds = changed ? 0 : stableRounds + 1;
    previous = current;

    // Infinite-scroll pages often have no button. Two unchanged rounds are
    // required before collection stops, so one slow network response cannot
    // make the collector treat the first viewport as the complete listing.
    if (!controls.length && stableRounds >= 2) break;
  }

  window.scrollTo(0, 0);
  await sleep(180);
  return {...previous, clicks, stableRounds};
}
"""


AUTHORITATIVE_DETAIL_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const root = document.querySelector("main") || document.querySelector("article") || document.body;
  let lines = String(root ? (root.innerText || root.textContent || "") : "")
    .replace(/\r/g, "\n")
    .split("\n")
    .map(clean)
    .filter(Boolean);

  const stopIndex = lines.findIndex(line => /^(?:other events?|explore more|recommended for you|you may also like|related events?|past events?)$/i.test(line));
  if (stopIndex > 0) lines = lines.slice(0, stopIndex);

  function scalar(value) {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    if (Array.isArray(value)) return clean(value.map(scalar).filter(Boolean).join(" "));
    if (typeof value === "object") {
      for (const key of ["name", "title", "label", "value", "text", "address", "streetAddress"]) {
        if (value[key] != null) {
          const candidate = scalar(value[key]);
          if (candidate) return candidate;
        }
      }
    }
    return "";
  }

  function eventType(value) {
    const values = Array.isArray(value) ? value : [value];
    return values.some(item => /(?:^|\b)(?:event|festival|exhibition|course|screening)(?:\b|$)/i.test(String(item || "")));
  }

  function findEvent(value, depth = 0) {
    if (value == null || depth > 12) return null;
    if (Array.isArray(value)) {
      for (const child of value) {
        const found = findEvent(child, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof value !== "object") return null;
    if (eventType(value["@type"] || value.type)) return value;
    for (const child of Object.values(value)) {
      const found = findEvent(child, depth + 1);
      if (found) return found;
    }
    return null;
  }

  let structured = null;
  for (const script of Array.from(document.querySelectorAll("script[type='application/ld+json'], script[type*='json']"))) {
    const raw = String(script.textContent || "").trim();
    if (!raw || raw.length > 1500000) continue;
    try { structured = findEvent(JSON.parse(raw)); } catch (e) {}
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

  const datePattern = /\b20\d{2}\b|\b(?:ongoing|permanent)\b|\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i;
  const labels = new Set([
    "date", "date & time", "date and time", "event date", "opening hours", "time", "when",
    "location", "venue", "where", "admission", "admission fee", "ticket price", "cost",
    "perfect for", "recommended time", "programme fee",
  ]);

  function labeledValue(names, predicate) {
    const wanted = names.map(name => name.toLowerCase());
    for (let index = 0; index < lines.length; index += 1) {
      const current = lines[index];
      const lower = current.toLowerCase();
      for (const name of wanted) {
        const inline = lower.match(new RegExp("^" + name.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&") + "\\s*:?\\s*(.+)$", "i"));
        if (inline && clean(inline[1]) && predicate(clean(inline[1]))) return clean(inline[1]);
      }
      const normalized = lower.replace(/:$/, "");
      if (!wanted.includes(normalized)) continue;
      const values = [];
      for (let offset = index + 1; offset < Math.min(lines.length, index + 8); offset += 1) {
        const candidate = lines[offset];
        if (labels.has(candidate.toLowerCase().replace(/:$/, ""))) break;
        if (predicate(candidate)) values.push(candidate);
        else if (values.length) break;
      }
      if (values.length) return clean(values.join(" "));
    }
    return "";
  }

  const genericTitle = /^(?:what'?s on|calendar of events|events?|exhibitions?|programmes?|programs?)$/i;
  const headingTitle = Array.from(document.querySelectorAll("main h1, article h1, h1, main h2, article h2"))
    .map(el => clean(el.innerText || el.textContent))
    .find(value => value && !genericTitle.test(value));
  const ogTitle = clean(document.querySelector("meta[property='og:title']")?.getAttribute("content"));
  let title = scalar(structured && (structured.name || structured.headline)) || headingTitle || ogTitle || clean(document.title);
  title = title.replace(/\s+[|–—-]\s+(?:National Gallery Singapore|Gardens by the Bay|Science Centre Singapore|National Museum of Singapore|Sentosa)$/i, "").trim();

  let dateText = scalar(structured && structured.startDate);
  const endText = scalar(structured && structured.endDate);
  if (dateText && endText && endText !== dateText) dateText = `${dateText} - ${endText}`;
  if (!dateText) {
    dateText = labeledValue(["date & time", "date and time", "event date", "opening hours", "date", "when"], value => datePattern.test(value) && !/last admission|copyright|updated/i.test(value));
  }

  let location = locationText(structured && structured.location);
  if (!location) {
    location = labeledValue(["location", "venue", "where"], value => value.length <= 180 && !datePattern.test(value) && !/^(?:free|admission|ticket|buy tickets?|find out more|read more)$/i.test(value));
  }

  let summary = scalar(structured && structured.description);
  if (!summary && title) {
    const titleIndex = lines.findIndex(line => line.toLowerCase() === title.toLowerCase());
    const candidates = lines.slice(titleIndex >= 0 ? titleIndex + 1 : 0, titleIndex >= 0 ? titleIndex + 12 : 24);
    summary = candidates.find(line => line.length >= 35 && !datePattern.test(line) && !labels.has(line.toLowerCase().replace(/:$/, ""))) || "";
  }

  const combined = [title, dateText, location, summary, ...lines].filter(Boolean);
  const deduped = [];
  const seen = new Set();
  for (const line of combined) {
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


def _segments(url: object) -> list[str]:
    return [segment.lower() for segment in urlparse(_extract.clean(url)).path.split("/") if segment]


def _known_non_event_url(url: object) -> bool:
    return any(segment in NON_EVENT_PATH_SEGMENTS for segment in _segments(url))


def _source_excluded_url(source: dict[str, Any], url: object) -> bool:
    value = _extract.clean(url).lower()
    return any(str(pattern).lower() in value for pattern in source.get("exclude_url_patterns") or [])


def _canonical_detail_url(url: object) -> bool:
    value = _extract.clean(url)
    if not value.startswith(("http://", "https://")) or SYNTHETIC_URL_RE.search(value):
        return False
    if _known_non_event_url(value):
        return False
    path = urlparse(value).path.rstrip("/")
    leaf = path.split("/")[-1].lower().removesuffix(".html")
    return leaf not in GENERIC_DETAIL_LEAVES


def _patch_card_js() -> None:
    old_loop = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new_loop = 'for (const a of [...(el.matches && el.matches("a[href]") ? [el] : []), ...Array.from(el.querySelectorAll("a[href]"))]) {'
    _browser.CARD_JS = _browser.CARD_JS.replace(old_loop, new_loop)

    old_generic = '"guided-tours"]);'
    additions = ', "plan-your-itinerary", "visitor-information", "museum-map", "accessibility", "group-visits", "getting-here", "shop-dine-relax", "venue-rental", "filming-photography", "contact-us", "image-requests"]);'
    _browser.CARD_JS = _browser.CARD_JS.replace(old_generic, additions)
    _browser.CLICK_NEXT_PAGE_JS = _browser.CLICK_NEXT_PAGE_JS.replace(old_generic, additions)


def _parse_iso(value: object) -> date | None:
    text = _extract.clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _valid_title(value: object) -> str:
    title = _extract.normalise_title(value)
    if not title or _extract.GENERIC_TITLE_RE.match(title) or _extract.FAKE_TITLE_RE.match(title):
        return ""
    if _extract.DATE_LINE_RE.search(title):
        return ""
    return _extract.short(title, 140)


def _valid_venue(value: object) -> str:
    venue = _extract.clean(value)
    if not venue or len(venue) > 180 or _extract.DATE_LINE_RE.search(venue) or _extract.TIME_RE.search(venue):
        return ""
    if venue.lower() in {"location", "venue", "where", "admission", "date", "date & time"}:
        return ""
    return _extract.short(venue, 180)


def _detail_dates(card: dict[str, Any]) -> tuple[date | None, date | None, str]:
    label = _extract.clean(card.get("detail_when"))
    start = _parse_iso(card.get("detail_start_date"))
    end = _parse_iso(card.get("detail_end_date"))
    parsed = _extract.label_dates(label)
    if not start and parsed:
        start = min(parsed)
    if not end and parsed:
        end = max(parsed)
    return start, end, label


def _merge_detail(card: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(card)
    title = _valid_title(detail.get("title"))
    when = _extract.clean(detail.get("date_text"))
    where = _valid_venue(detail.get("location"))
    summary = _extract.clean(detail.get("summary"))
    start = _parse_iso(detail.get("start_date"))
    end = _parse_iso(detail.get("end_date"))

    detail_text = str(detail.get("text") or "").strip()
    if detail_text:
        merged["text"] = detail_text
        merged["text_lines"] = detail.get("text_lines") or detail_text.splitlines()
        merged["detail_enriched"] = True
        merged["extraction_mode"] = f"{card.get('extraction_mode') or 'card'}+authoritative_detail"
    if title:
        merged["detail_title"] = title
        merged["headings"] = [title]
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
            range_start = start or end
            range_end = end or start
            structured["when"] = _official_feeds.format_date_range(range_start, range_end, when)
            structured["start_date"] = range_start.isoformat() if range_start else ""
            structured["end_date"] = range_end.isoformat() if range_end else ""
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


def _enrich_details(source: dict[str, Any], cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not source.get("detail_enrichment") or not cards:
        return cards
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return cards

    limit = max(0, int(source.get("detail_limit", 24)))
    timeout = int(source.get("detail_timeout_ms", _browser.NHB_DETAIL_TIMEOUT_MS))
    force = bool(source.get("detail_authoritative"))
    enriched: list[dict[str, Any]] = []
    reads = 0

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            for card in cards:
                url = _extract.clean(card.get("url"))
                needs_detail = force or not _browser.card_has_date(card)
                if reads >= limit or not needs_detail or not _canonical_detail_url(url):
                    enriched.append(card)
                    continue

                page = None
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout)
                    except Exception:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(650)
                    detail = page.evaluate(_browser.DETAIL_CARD_JS) or {}
                    reads += 1
                    enriched.append(_merge_detail(card, detail))
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
    return enriched


def _repair_structured_url(structured_card: dict[str, Any], dom_card: dict[str, Any]) -> dict[str, Any]:
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
        if title:
            structured_titles.add(title)
            matching_dom = dom_by_title.get(title)
            if matching_dom:
                card = _repair_structured_url(card, matching_dom)
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


def _render_listing_cards(source: dict[str, Any], url: str, debug_dir, max_cards: int = 60):
    source_limit = max(max_cards, int(source.get("max_cards", max_cards)))
    rendered = _base_render_listing_cards(source, url, debug_dir, max_cards=source_limit)
    cards = rendered.get("cards") or []
    if source.get("detail_enrichment") and cards:
        rendered = dict(rendered)
        rendered["cards"] = _enrich_details(source, cards)
        rendered["detail_enrichment"] = {
            "enabled": True,
            "authoritative": bool(source.get("detail_authoritative")),
            "limit": int(source.get("detail_limit", 24)),
        }
    return rendered


def _event_looks_wrong(source: dict[str, Any], card: dict[str, Any], title: str, when: str) -> str:
    reason = _base_event_looks_wrong(source, card, title, when)
    if reason:
        return reason
    url = card.get("url") or ""
    if _known_non_event_url(url) or _source_excluded_url(source, url):
        return "non_event_information_page"
    return ""


def _event_from_card(source: dict[str, Any], card: dict[str, Any]):
    working = dict(card)
    title = _valid_title(working.get("detail_title"))
    when = _extract.clean(working.get("detail_when"))
    where = _valid_venue(working.get("detail_where"))
    summary = _extract.clean(working.get("detail_summary"))

    if title:
        working["headings"] = [title]
        working["link_text"] = title
    detail_lines = [item for item in (title, when, where, summary) if item]
    if detail_lines:
        existing = working.get("text_lines") or _extract.lines(working.get("text") or "")
        working["text_lines"] = detail_lines + list(existing)
        working["text"] = "\n".join(str(item) for item in working["text_lines"] if str(item).strip())

    event, reason = _base_event_from_card(source, working)
    if not event:
        return event, reason
    if _known_non_event_url(event.get("url")) or _source_excluded_url(source, event.get("url")):
        return None, "non_event_information_page"

    repaired = dict(event)
    if title:
        repaired["title"] = title

    start, end, date_label = _detail_dates(working)
    if start or end:
        range_start = start or end
        range_end = end or start
        if range_end and range_end < _extract.TODAY:
            return None, "past_date"
        repaired["when"] = _official_feeds.format_date_range(range_start, range_end, date_label)
        repaired["start_date"] = range_start.isoformat() if range_start else repaired.get("start_date", "")
        repaired["end_date"] = range_end.isoformat() if range_end else ""
    elif date_label:
        parsed = _extract.label_dates(date_label)
        if parsed and max(parsed) < _extract.TODAY:
            return None, "past_date"
        repaired["when"] = date_label

    if where:
        repaired["where"] = where
    if summary:
        repaired["summary"] = summary
    return repaired, reason


def apply() -> None:
    global _applied, _base_render_listing_cards, _base_event_from_card, _base_event_looks_wrong, _base_collect_events
    if _applied:
        return

    package = sys.modules.get(__package__)
    _base_render_listing_cards = _extract.render_listing_cards
    _base_event_from_card = _extract.event_from_card
    _base_event_looks_wrong = _extract.event_looks_wrong
    _base_collect_events = getattr(package, "collect_events", None)

    _patch_card_js()
    _browser.PREPARE_PAGE_JS = DEEP_SCROLL_JS
    _browser.DETAIL_CARD_JS = AUTHORITATIVE_DETAIL_JS
    _extract.PAST_GRACE_DAYS = 0
    _extract.MAX_EVENTS_PER_SOURCE = max(_extract.MAX_EVENTS_PER_SOURCE, 40)
    _extract.SOURCE_TIMEOUT_SECONDS = max(_extract.SOURCE_TIMEOUT_SECONDS, 160)
    _official_feeds.prefer_structured_cards = _prefer_structured_cards
    _extract.render_listing_cards = _render_listing_cards
    _extract.event_looks_wrong = _event_looks_wrong
    _extract.event_from_card = _event_from_card

    if package is not None:
        package.event_from_card = _extract.event_from_card
        if callable(_base_collect_events):
            def collect_events(*args, **kwargs):
                payload = dict(_base_collect_events(*args, **kwargs))
                payload["version"] = 50
                payload["extractor"] = "structured-first-v50-source-overrides"
                return payload
            package.collect_events = collect_events

    _applied = True


__all__ = ["apply", "NON_EVENT_PATH_SEGMENTS"]
