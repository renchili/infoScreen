from __future__ import annotations

import os
import re
import sys
from datetime import date
from typing import Any
from urllib.parse import unquote, urlparse

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds

GENERIC_LEAF_RE = re.compile(
    r"^(?:whats?-on|whatson|events?|overview|view-all|calendar|programmes?|programs?|"
    r"activities?|exhibitions?|workshops?|tours?|shows?|performances?)$",
    re.I,
)
MEDIA_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$", re.I)
SYNTHETIC_FRAGMENT_RE = re.compile(r"^(?:nhb|nhb-json|structured)-", re.I)
NARRATIVE_VENUE_RE = re.compile(
    r"\b(?:presents?|explore|discover|celebrates?|considers?|invites?|journey|"
    r"exhibition|performance|co-curated|newly revamped|find out|learn more)\b",
    re.I,
)
DETAIL_LIMIT = max(1, int(os.environ.get("LOCAL_EVENTS_DETAIL_LIMIT", "24")))
DETAIL_TIMEOUT_MS = int(os.environ.get("LOCAL_EVENTS_DETAIL_TIMEOUT_MS", "16000"))

DEEP_SCROLL_JS = r"""
async (args) => {
  const maxRounds = Math.max(Number(args.maxRounds || 0), 24);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) !== 0 && r.width >= 20 && r.height >= 18;
  };
  const state = () => {
    const links = Array.from(document.querySelectorAll("a[href]")).filter(visible).map(a => a.href).filter(Boolean);
    return [document.body.scrollHeight, document.body.innerText.length, new Set(links).size].join(":");
  };
  let previous = "", stableRounds = 0, clicks = 0, rounds = 0;
  for (let round = 0; round < maxRounds; round += 1) {
    rounds = round + 1;
    scrollTo(0, document.body.scrollHeight);
    await sleep(650);
    const controls = Array.from(document.querySelectorAll("button,a[href],[role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs|see more)\b/i.test(
        String(el.innerText || el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim()
      ));
    if (controls.length) {
      try { controls[0].click(); clicks += 1; await sleep(850); } catch (e) {}
    }
    const current = state();
    stableRounds = current === previous ? stableRounds + 1 : 0;
    previous = current;
    if (stableRounds >= 3) break;
  }
  scrollTo(0, 0);
  return {clicks, rounds, stableRounds, height: document.body.scrollHeight};
}
"""

AUTHORITATIVE_DETAIL_JS = r"""
() => {
  const clean = value => String(value || "").replace(/\s+/g, " ").trim();
  const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) !== 0 && r.width >= 20 && r.height >= 12;
  };
  const first = selector => Array.from(document.querySelectorAll(selector)).filter(visible)
    .map(el => clean(el.innerText || el.textContent)).find(Boolean) || "";
  const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
  const site = clean(document.querySelector('meta[property="og:site_name"]')?.content);
  let title = first("main h1,article h1,h1") || clean(document.querySelector('meta[property="og:title"]')?.content) || clean(document.title);
  if (site) title = title.replace(new RegExp("\\s+[|–—-]\\s+" + site.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&") + "$", "i"), "").trim();

  const eventObjects = [];
  const visit = (value, depth = 0) => {
    if (!value || typeof value !== "object" || depth > 10 || eventObjects.length >= 20) return;
    if (Array.isArray(value)) { value.forEach(item => visit(item, depth + 1)); return; }
    const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"] || value.type];
    if (types.some(item => /(^|:)event$/i.test(String(item || "")))) eventObjects.push(value);
    Object.values(value).forEach(item => visit(item, depth + 1));
  };
  for (const script of document.querySelectorAll('script[type*="ld+json" i]')) {
    try { visit(JSON.parse(script.textContent || "")); } catch (e) {}
  }

  const dates = [];
  for (const el of document.querySelectorAll("time[datetime],time,[class*='date' i],[id*='date' i],[class*='time' i],[id*='time' i]")) {
    const value = clean(el.getAttribute("datetime") || el.innerText || el.textContent);
    if (visible(el) && value && !dates.includes(value)) dates.push(value);
    if (dates.length >= 20) break;
  }
  const venues = [];
  for (const el of document.querySelectorAll("address,[class*='venue' i],[id*='venue' i],[class*='location' i],[id*='location' i],[itemprop='location']")) {
    const value = clean(el.innerText || el.textContent);
    if (visible(el) && value && !venues.includes(value)) venues.push(value);
    if (venues.length >= 12) break;
  }
  const root = document.querySelector("main") || document.querySelector("article") || document.body;
  const lines = String(root.innerText || root.textContent || "").split(/\n+/).map(clean).filter(Boolean).slice(0, 120);
  const summary = clean(document.querySelector('meta[name="description"]')?.content) || clean(document.querySelector('meta[property="og:description"]')?.content);
  return {canonical, title, eventObjects, dates, venues, lines, summary};
}
"""

_applied = False
_base_render = None
_base_event = None
_base_collect = None


def _host(value: str) -> str:
    return value.lower().removeprefix("www.")


def canonical_detail_url(source: dict[str, Any], value: object) -> bool:
    url = _extract.clean(value)
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urlparse(url)
    host = _host(parsed.hostname or "")
    allowed = [_host(str(item)) for item in source.get("allowed_domains") or []]
    if not host or not any(host == item or host.endswith("." + item) for item in allowed):
        return False
    if parsed.fragment and SYNTHETIC_FRAGMENT_RE.match(parsed.fragment):
        return False
    path = unquote(parsed.path).rstrip("/").lower()
    listing_paths = {urlparse(str(item)).path.rstrip("/").lower() for item in source.get("listing_urls") or []}
    if not path or path in listing_paths or MEDIA_RE.search(path):
        return False
    leaf = path.rsplit("/", 1)[-1].removesuffix(".html")
    return bool(leaf and not GENERIC_LEAF_RE.fullmatch(leaf))


def _patch_browser() -> None:
    old = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new = 'for (const a of [...(el.matches && el.matches("a[href]") ? [el] : []), ...Array.from(el.querySelectorAll("a[href]"))]) {'
    _browser.CARD_JS = _browser.CARD_JS.replace(old, new)
    _browser.PREPARE_PAGE_JS = DEEP_SCROLL_JS


def _candidate_url(source: dict[str, Any], card: dict[str, Any]) -> str:
    for value in [card.get("url"), *(card.get("detail_urls") or [])]:
        if canonical_detail_url(source, value):
            return _extract.clean(value)
    return ""


def _merge_detail(source: dict[str, Any], card: dict[str, Any], payload: dict[str, Any], index: int) -> dict[str, Any]:
    canonical = _extract.clean(payload.get("canonical"))
    if not canonical_detail_url(source, canonical):
        canonical = _candidate_url(source, card)
    events = _official_feeds.extract_structured_events(
        payload.get("eventObjects") or [], canonical,
        str(source.get("default_venue") or source.get("name") or ""), limit=1,
    )
    evidence = {
        "canonical_url": canonical,
        "title": _extract.clean(payload.get("title")),
        "date_candidates": [_extract.clean(item) for item in payload.get("dates") or [] if _extract.clean(item)],
        "venue_candidates": [_extract.clean(item) for item in payload.get("venues") or [] if _extract.clean(item)],
    }
    if events:
        event = dict(events[0]); event["url"] = canonical
        merged = _official_feeds.event_card(event, str(source.get("id") or "source"), index)
    else:
        title = evidence["title"] or _extract.clean(card.get("link_text"))
        lines = [title, *evidence["date_candidates"], *evidence["venue_candidates"]]
        summary = _extract.clean(payload.get("summary"))
        if summary: lines.append(summary)
        lines.extend(_extract.clean(item) for item in (payload.get("lines") or [])[:80])
        deduped = []
        for item in lines:
            if item and item not in deduped: deduped.append(item)
        merged = dict(card)
        merged.update(url=canonical, detail_urls=[canonical], detail_url_count=1, link_text=title,
                      headings=[title] if title else list(card.get("headings") or []),
                      text_lines=deduped, text="\n".join(deduped))
    merged["detail_enriched"] = True
    merged["detail_evidence"] = evidence
    merged["screenshot"] = card.get("screenshot") or ""
    return merged


def _enrich(source: dict[str, Any], cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = [(card, _candidate_url(source, card)) for card in cards]
    candidates = [(card, url) for card, url in candidates if url]
    debug = {"candidates": len(candidates), "enriched": 0, "errors": 0, "dropped_by_limit": max(0, len(candidates) - DETAIL_LIMIT)}
    if not candidates:
        return [], debug
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return [], {**debug, "errors": len(candidates)}

    output = []
    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            for index, (card, url) in enumerate(candidates[:DETAIL_LIMIT]):
                page = None
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
                    try: page.goto(url, wait_until="networkidle", timeout=DETAIL_TIMEOUT_MS)
                    except Exception: page.goto(url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
                    page.wait_for_timeout(650)
                    output.append(_merge_detail(source, card, page.evaluate(AUTHORITATIVE_DETAIL_JS) or {}, index))
                    debug["enriched"] += 1
                except Exception:
                    debug["errors"] += 1
                finally:
                    if page is not None:
                        try: page.close()
                        except Exception: pass
        finally:
            browser.close()
    return output, debug


def _repair_structured_url(source: dict[str, Any], card: dict[str, Any], dom: dict[str, Any]) -> dict[str, Any]:
    canonical = _candidate_url(source, dom)
    if not canonical: return card
    repaired = dict(card); repaired.update(url=canonical, page_url=canonical)
    if isinstance(repaired.get("structured_event"), dict):
        structured = dict(repaired["structured_event"]); structured["url"] = canonical; repaired["structured_event"] = structured
    return repaired


def _prefer_structured(structured: list[dict[str, Any]], dom: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    source = getattr(_prefer_structured, "source", {})
    dom_by_title = {_official_feeds.card_title(card): card for card in dom if _official_feeds.card_title(card)}
    merged, titles = [], set()
    for card in structured:
        title = _official_feeds.card_title(card)
        if title:
            titles.add(title)
            if title in dom_by_title: card = _repair_structured_url(source, card, dom_by_title[title])
        merged.append(card)
    merged.extend(card for card in dom if not _official_feeds.card_title(card) or _official_feeds.card_title(card) not in titles)
    return merged[:limit]


def _render(source: dict[str, Any], url: str, debug_dir, max_cards: int = 60):
    _prefer_structured.source = source
    rendered = dict(_base_render(source, url, debug_dir, max_cards=max(max_cards, 120)))
    cards, debug = _enrich(source, [card for card in rendered.get("cards") or [] if isinstance(card, dict)])
    rendered["cards"] = cards
    rendered["canonical_detail_evidence"] = debug
    return rendered


def _event_end(event: dict[str, Any]) -> date | None:
    for value in (event.get("end_date"), event.get("start_date")):
        try:
            if value: return date.fromisoformat(_extract.clean(value)[:10])
        except ValueError: pass
    dates = _extract.label_dates(_extract.clean(event.get("when")))
    return max(dates) if dates else None


def _venue(source: dict[str, Any], event: dict[str, Any], evidence: dict[str, Any]) -> str:
    for value in [*(evidence.get("venue_candidates") or []), event.get("where")]:
        venue = _extract.clean(value)
        if venue and len(venue) <= 140 and len(venue.split()) <= 16 and not NARRATIVE_VENUE_RE.search(venue):
            return venue
    return str(source.get("default_venue") or source.get("name") or "")


def _event(source: dict[str, Any], card: dict[str, Any]):
    evidence = card.get("detail_evidence") if isinstance(card.get("detail_evidence"), dict) else {}
    if not card.get("detail_enriched") or not evidence:
        return None, "detail_evidence_missing"
    if not card.get("structured_event") and not evidence.get("date_candidates"):
        return None, "detail_date_evidence_missing"
    event, reason = _base_event(source, card)
    if not event: return event, reason
    url = _extract.clean(event.get("url") or card.get("url"))
    if not canonical_detail_url(source, url):
        return None, "noncanonical_detail_url"
    end = _event_end(event)
    if end and end < _extract.TODAY:
        return None, "past_date"
    event = dict(event)
    detail_title = _extract.clean(evidence.get("title"))
    if detail_title and not _extract.GENERIC_TITLE_RE.match(detail_title): event["title"] = _extract.short(detail_title, 140)
    event.update(url=url, where=_venue(source, event, evidence), candidate_policy="canonical-detail-evidence-v1")
    return event, reason


def apply() -> None:
    global _applied, _base_render, _base_event, _base_collect
    if _applied: return
    package = sys.modules.get(__package__)
    _patch_browser()
    _base_render, _base_event = _extract.render_listing_cards, _extract.event_from_card
    _base_collect = getattr(package, "collect_events", None)
    _extract.PAST_GRACE_DAYS = 0
    _extract.MAX_EVENTS_PER_SOURCE = max(_extract.MAX_EVENTS_PER_SOURCE, 40)
    _extract.SOURCE_TIMEOUT_SECONDS = max(_extract.SOURCE_TIMEOUT_SECONDS, 160)
    _official_feeds.prefer_structured_cards = _prefer_structured
    _extract.render_listing_cards, _extract.event_from_card = _render, _event
    if package is not None:
        package.event_from_card = _extract.event_from_card
        if callable(_base_collect):
            def collect_events(*args, **kwargs):
                payload = dict(_base_collect(*args, **kwargs))
                payload.update(version=51, extractor="structured-first-v51-canonical-detail-evidence")
                return payload
            package.collect_events = collect_events
    _applied = True


__all__ = ["apply", "canonical_detail_url", "DEEP_SCROLL_JS", "_merge_detail"]
