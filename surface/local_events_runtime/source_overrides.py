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
    "plan-your-itinerary", "visitor-information", "museum-map", "accessibility",
    "group-visits", "getting-here", "shop-dine-relax", "venue-rental",
    "filming-photography", "contact-us", "image-requests", "book-a-venue",
    "amenities-services", "opening-hours-closures", "itinerary-planner",
    "gardens-map", "information-guides", "visiting-guidelines",
    "mobile-apps-travel-guide",
}
SYNTHETIC_URL_RE = re.compile(r"#(?:nhb(?:-json)?|structured)-", re.I)
GENERIC_DETAIL_LEAVES = {
    "", "whats-on", "whatson", "overview", "view-all", "events", "event",
    "exhibitions", "exhibition", "programmes", "programme", "programs",
    "program", "activities", "activity",
}

_applied = False
_base_render_listing_cards = None
_base_event_from_card = None
_base_event_looks_wrong = None
_base_collect_events = None

DEEP_SCROLL_JS = r"""
async (args) => {
  const maxRounds = Number(args.maxRounds || 0);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = el => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0 && rect.width >= 40 && rect.height >= 20;
  };
  const label = el => String(el.innerText || el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
  const state = () => {
    const selectors = "article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]";
    return {height: document.body.scrollHeight, cards: document.querySelectorAll(selectors).length, textLength: String(document.body.innerText || "").length};
  };

  let previous = state();
  let stableRounds = 0;
  let clicks = 0;
  for (let round = 0; round < maxRounds; round += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(900);
    const controls = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs)\b/i.test(label(el)));
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
    const changed = current.height > previous.height + 20 || current.cards > previous.cards || current.textLength > previous.textLength + 50;
    stableRounds = changed ? 0 : stableRounds + 1;
    previous = current;
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
  let lines = String(root ? (root.innerText || root.textContent || "") : "").replace(/\r/g, "\n").split("\n").map(clean).filter(Boolean);
  const stop = lines.findIndex(line => /^(?:other events?|explore more|recommended for you|you may also like|related events?|past events?)$/i.test(line));
  if (stop > 0) lines = lines.slice(0, stop);

  function scalar(value) {
    if (value == null) return "";
    if (typeof value === "string" || typeof value === "number") return clean(value);
    if (Array.isArray(value)) return clean(value.map(scalar).filter(Boolean).join(" "));
    if (typeof value === "object") {
      for (const key of ["name", "title", "label", "value", "text", "address", "streetAddress"]) {
        const found = scalar(value[key]);
        if (found) return found;
      }
    }
    return "";
  }

  function isEventType(value) {
    return (Array.isArray(value) ? value : [value]).some(item => /(?:^|\b)(?:event|festival|exhibition|course|screening)(?:\b|$)/i.test(String(item || "")));
  }
  function findEvent(value, depth = 0) {
    if (value == null || depth > 12) return null;
    if (Array.isArray(value)) {
      for (const child of value) { const found = findEvent(child, depth + 1); if (found) return found; }
      return null;
    }
    if (typeof value !== "object") return null;
    if (isEventType(value["@type"] || value.type)) return value;
    for (const child of Object.values(value)) { const found = findEvent(child, depth + 1); if (found) return found; }
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
    const parts = [scalar(value.name), scalar(value.address && value.address.name), scalar(value.address && value.address.streetAddress), scalar(value.address && value.address.addressLocality)].filter(Boolean);
    return clean(Array.from(new Set(parts)).join(", "));
  }

  const dateLike = value => /\b20\d{2}\b|\b(?:ongoing|permanent)\b|\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i.test(value) && !/last admission|copyright|updated/i.test(value);
  const allLabels = new Set(["date", "date & time", "date and time", "event date", "opening hours", "time", "when", "location", "venue", "where", "admission", "admission fee", "ticket price", "cost", "perfect for", "recommended time", "programme fee"]);
  function labeledValue(names, predicate) {
    const wanted = names.map(name => name.toLowerCase());
    for (let index = 0; index < lines.length; index += 1) {
      const current = lines[index];
      const lower = current.toLowerCase();
      for (const name of wanted) {
        if (lower.startsWith(name + ":") || lower.startsWith(name + " ")) {
          const value = clean(current.slice(name.length).replace(/^\s*:?\s*/, ""));
          if (value && predicate(value)) return value;
        }
      }
      const normalized = lower.replace(/:$/, "");
      if (!wanted.includes(normalized)) continue;
      const values = [];
      for (let offset = index + 1; offset < Math.min(lines.length, index + 8); offset += 1) {
        const candidate = lines[offset];
        if (allLabels.has(candidate.toLowerCase().replace(/:$/, ""))) break;
        if (predicate(candidate)) values.push(candidate); else if (values.length) break;
      }
      if (values.length) return clean(values.join(" "));
    }
    return "";
  }

  const genericTitle = /^(?:what'?s on|calendar of events|events?|exhibitions?|programmes?|programs?)$/i;
  const heading = Array.from(document.querySelectorAll("main h1, article h1, h1, main h2, article h2")).map(el => clean(el.innerText || el.textContent)).find(value => value && !genericTitle.test(value));
  const ogTitle = clean(document.querySelector("meta[property='og:title']")?.getAttribute("content"));
  let title = scalar(structured && (structured.name || structured.headline)) || heading || ogTitle || clean(document.title);
  title = title.replace(/\s+[|–—-]\s+(?:National Gallery Singapore|Gardens by the Bay|Science Centre Singapore|National Museum of Singapore|Sentosa)$/i, "").trim();

  let dateText = scalar(structured && structured.startDate);
  const endText = scalar(structured && structured.endDate);
  if (dateText && endText && endText !== dateText) dateText = `${dateText} - ${endText}`;
  if (!dateText) dateText = labeledValue(["date & time", "date and time", "event date", "opening hours", "date", "when"], dateLike);

  let location = locationText(structured && structured.location);
  if (!location) location = labeledValue(["location", "venue", "where"], value => value.length <= 180 && !dateLike(value) && !/^(?:free|admission|ticket|buy tickets?|find out more|read more)$/i.test(value));

  let summary = scalar(structured && structured.description);
  if (!summary && title) {
    const titleIndex = lines.findIndex(line => line.toLowerCase() === title.toLowerCase());
    summary = lines.slice(titleIndex >= 0 ? titleIndex + 1 : 0, titleIndex >= 0 ? titleIndex + 12 : 24).find(line => line.length >= 35 && !dateLike(line) && !allLabels.has(line.toLowerCase().replace(/:$/, ""))) || "";
  }

  const deduped = [];
  const seen = new Set();
  for (const line of [title, dateText, location, summary, ...lines].filter(Boolean)) {
    const key = clean(line).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(clean(line));
  }
  return {
    title, date_text: dateText, location,
    start_date: scalar(structured && structured.startDate),
    end_date: scalar(structured && structured.endDate),
    summary,
    text: deduped.slice(0, 120).join("\n"),
    text_lines: deduped.slice(0, 120),
    headings: title ? [title] : [],
    image_alts: Array.from(document.querySelectorAll("main img[alt], article img[alt], img[alt]")).map(img => clean(img.getAttribute("alt"))).filter(Boolean).slice(0, 8),
  };
}
"""


def _segments(url: object) -> list[str]:
    return [part.lower() for part in urlparse(_extract.clean(url)).path.split("/") if part]


def _known_non_event_url(url: object) -> bool:
    return any(part in NON_EVENT_PATH_SEGMENTS for part in _segments(url))


def _source_excluded_url(source: dict[str, Any], url: object) -> bool:
    value = _extract.clean(url).lower()
    return any(str(pattern).lower() in value for pattern in source.get("exclude_url_patterns") or [])


def _canonical_detail_url(url: object) -> bool:
    value = _extract.clean(url)
    if not value.startswith(("http://", "https://")) or SYNTHETIC_URL_RE.search(value) or _known_non_event_url(value):
        return False
    leaf = urlparse(value).path.rstrip("/").split("/")[-1].lower().removesuffix(".html")
    return leaf not in GENERIC_DETAIL_LEAVES


def _patch_browser_scripts() -> None:
    old_loop = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new_loop = 'for (const a of [...(el.matches && el.matches("a[href]") ? [el] : []), ...Array.from(el.querySelectorAll("a[href]"))]) {'
    _browser.CARD_JS = _browser.CARD_JS.replace(old_loop, new_loop)
    generic = '"guided-tours"]);'
    expanded = '"guided-tours", "plan-your-itinerary", "visitor-information", "museum-map", "accessibility", "group-visits", "getting-here", "shop-dine-relax", "venue-rental", "filming-photography", "contact-us", "image-requests"]);'
    _browser.CARD_JS = _browser.CARD_JS.replace(generic, expanded)
    _browser.CLICK_NEXT_PAGE_JS = _browser.CLICK_NEXT_PAGE_JS.replace(generic, expanded)
    _browser.PREPARE_PAGE_JS = DEEP_SCROLL_JS
    _browser.DETAIL_CARD_JS = AUTHORITATIVE_DETAIL_JS


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
    if not title or _extract.GENERIC_TITLE_RE.match(title) or _extract.FAKE_TITLE_RE.match(title) or _extract.DATE_LINE_RE.search(title):
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
    return start or (min(parsed) if parsed else None), end or (max(parsed) if parsed else None), label


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
        merged.update(text=detail_text, text_lines=detail.get("text_lines") or detail_text.splitlines(), detail_enriched=True, extraction_mode=f"{card.get('extraction_mode') or 'card'}+authoritative_detail")
    if title:
        merged.update(detail_title=title, headings=[title], link_text=title)
    if when: merged["detail_when"] = when
    if where: merged["detail_where"] = where
    if summary: merged["detail_summary"] = summary
    if start: merged["detail_start_date"] = start.isoformat()
    if end: merged["detail_end_date"] = end.isoformat()

    structured = merged.get("structured_event")
    if isinstance(structured, dict):
        structured = dict(structured)
        if title: structured["title"] = title
        if start or end:
            range_start, range_end = start or end, end or start
            structured.update(when=_official_feeds.format_date_range(range_start, range_end, when), start_date=range_start.isoformat(), end_date=range_end.isoformat())
        elif when:
            structured["when"] = when
        if where: structured["where"] = where
        if summary: structured["summary"] = summary
        if _canonical_detail_url(merged.get("url")): structured["url"] = merged["url"]
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
    output = []
    reads = 0
    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            for card in cards:
                url = _extract.clean(card.get("url"))
                if reads >= limit or not (force or not _browser.card_has_date(card)) or not _canonical_detail_url(url):
                    output.append(card)
                    continue
                page = None
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
                    try: page.goto(url, wait_until="networkidle", timeout=timeout)
                    except Exception: page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(650)
                    output.append(_merge_detail(card, page.evaluate(_browser.DETAIL_CARD_JS) or {}))
                    reads += 1
                except Exception as exc:
                    failed = dict(card)
                    failed["detail_enrich_error"] = f"{type(exc).__name__}:{exc}"
                    output.append(failed)
                finally:
                    if page is not None:
                        try: page.close()
                        except Exception: pass
        finally:
            browser.close()
    return output


def _repair_structured_url(card: dict[str, Any], dom: dict[str, Any]) -> dict[str, Any]:
    canonical = _extract.clean(dom.get("url"))
    if not _canonical_detail_url(canonical):
        return card
    repaired = dict(card)
    repaired.update(url=canonical, page_url=canonical)
    if isinstance(repaired.get("structured_event"), dict):
        structured = dict(repaired["structured_event"])
        structured["url"] = canonical
        repaired["structured_event"] = structured
    return repaired


def _prefer_structured_cards(structured: list[dict[str, Any]], dom: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    dom_by_title = {}
    for card in dom:
        title = _official_feeds.card_title(card)
        if title and title not in dom_by_title: dom_by_title[title] = card
    merged = []
    structured_titles = set()
    for card in structured:
        title = _official_feeds.card_title(card)
        if title:
            structured_titles.add(title)
            if title in dom_by_title: card = _repair_structured_url(card, dom_by_title[title])
        merged.append(card)
        if len(merged) >= limit: return merged[:limit]
    for card in dom:
        title = _official_feeds.card_title(card)
        if title and title in structured_titles: continue
        merged.append(card)
        if len(merged) >= limit: break
    return merged[:limit]


def _render_listing_cards(source: dict[str, Any], url: str, debug_dir, max_cards: int = 60):
    rendered = _base_render_listing_cards(source, url, debug_dir, max_cards=max(max_cards, int(source.get("max_cards", max_cards))))
    cards = rendered.get("cards") or []
    if source.get("detail_enrichment") and cards:
        rendered = dict(rendered)
        rendered["cards"] = _enrich_details(source, cards)
        rendered["detail_enrichment"] = {"enabled": True, "authoritative": bool(source.get("detail_authoritative")), "limit": int(source.get("detail_limit", 24))}
    return rendered


def _event_looks_wrong(source: dict[str, Any], card: dict[str, Any], title: str, when: str) -> str:
    reason = _base_event_looks_wrong(source, card, title, when)
    if reason: return reason
    if _known_non_event_url(card.get("url")) or _source_excluded_url(source, card.get("url")):
        return "non_event_information_page"
    return ""


def _event_from_card(source: dict[str, Any], card: dict[str, Any]):
    working = dict(card)
    title = _valid_title(working.get("detail_title"))
    when = _extract.clean(working.get("detail_when"))
    where = _valid_venue(working.get("detail_where"))
    summary = _extract.clean(working.get("detail_summary"))
    if title: working.update(headings=[title], link_text=title)
    detail_lines = [item for item in (title, when, where, summary) if item]
    if detail_lines:
        existing = working.get("text_lines") or _extract.lines(working.get("text") or "")
        working["text_lines"] = detail_lines + list(existing)
        working["text"] = "\n".join(str(item) for item in working["text_lines"] if str(item).strip())

    event, reason = _base_event_from_card(source, working)
    if not event: return event, reason
    if _known_non_event_url(event.get("url")) or _source_excluded_url(source, event.get("url")):
        return None, "non_event_information_page"
    repaired = dict(event)
    if title: repaired["title"] = title
    start, end, label = _detail_dates(working)
    if start or end:
        range_start, range_end = start or end, end or start
        if range_end < _extract.TODAY: return None, "past_date"
        repaired.update(when=_official_feeds.format_date_range(range_start, range_end, label), start_date=range_start.isoformat(), end_date=range_end.isoformat())
    elif label:
        parsed = _extract.label_dates(label)
        if parsed and max(parsed) < _extract.TODAY: return None, "past_date"
        repaired["when"] = label
    if where: repaired["where"] = where
    if summary: repaired["summary"] = summary
    return repaired, reason


def apply() -> None:
    global _applied, _base_render_listing_cards, _base_event_from_card, _base_event_looks_wrong, _base_collect_events
    if _applied: return
    package = sys.modules.get(__package__)
    _base_render_listing_cards = _extract.render_listing_cards
    _base_event_from_card = _extract.event_from_card
    _base_event_looks_wrong = _extract.event_looks_wrong
    _base_collect_events = getattr(package, "collect_events", None)
    _patch_browser_scripts()
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
                payload.update(version=50, extractor="structured-first-v50-source-overrides")
                return payload
            package.collect_events = collect_events
    _applied = True


__all__ = ["apply", "NON_EVENT_PATH_SEGMENTS"]
