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

MEDIA_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$", re.I)
SYNTHETIC_FRAGMENT_RE = re.compile(r"^(?:nhb|nhb-json|structured)-", re.I)
NARRATIVE_VENUE_RE = re.compile(
    r"\b(?:presents?|explore|discover|celebrates?|considers?|invites?|journey|"
    r"exhibition|performance|co-curated|newly revamped|find out|learn more)\b",
    re.I,
)
LISTING_EVIDENCE = "official_activity_listing_card"
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
_base_collect = None


def _host(value: str) -> str:
    return value.lower().removeprefix("www.")


def canonical_detail_url(source: dict[str, Any], value: object) -> bool:
    """Return true for a real official detail URL, independent of title semantics."""
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
    return bool(path and path not in listing_paths and not MEDIA_RE.search(path))


def _patch_browser() -> None:
    """Restrict discovery to isolated dated cards on the configured listing page."""
    old_loop = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new_loop = 'for (const a of [...(el.matches && el.matches("a[href]") ? [el] : []), ...Array.from(el.querySelectorAll("a[href]"))]) {'
    _browser.CARD_JS = _browser.CARD_JS.replace(old_loop, new_loop)

    old_anchor = '''    const card = bestCard(a);
    const linkText = oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    push(out, seen, card, abs, linkText, "detail_link");'''
    new_anchor = '''    const card = bestCard(a);
    const listingDetailUrls = detailUrls(card);
    if (listingDetailUrls.length !== 1 || listingDetailUrls[0] !== abs) continue;
    if (!hasDateText(textLines(card).join(" "))) continue;
    const linkText = oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    push(out, seen, card, abs, linkText, "detail_link");'''
    _browser.CARD_JS = _browser.CARD_JS.replace(old_anchor, new_anchor)

    old_nhb = r'''      const text = textLines(el).join("\n");
      const base = officialHome || document.location.origin;
      const url = detailUrls(el)[0] || sameDomainNonListingUrls(el)[0] || (base.replace(/\/$/, '') + '#nhb-' + textHash(text.slice(0, 600)));
      push(out, seen, el, url, "", "nhb_dom_card");'''
    new_nhb = '''      const listingDetailUrls = detailUrls(el);
      if (listingDetailUrls.length !== 1) continue;
      const url = listingDetailUrls[0];
      push(out, seen, el, url, "", "nhb_dom_card");'''
    _browser.CARD_JS = _browser.CARD_JS.replace(old_nhb, new_nhb)
    _browser.PREPARE_PAGE_JS = DEEP_SCROLL_JS


def _candidate_url(source: dict[str, Any], card: dict[str, Any]) -> str:
    for value in [card.get("url"), *(card.get("detail_urls") or [])]:
        if canonical_detail_url(source, value):
            return _extract.clean(value)
    return ""


def _listing_card(source: dict[str, Any], card: dict[str, Any], listing_url: str) -> dict[str, Any] | None:
    """Admit only a real, isolated activity card rendered by the official list."""
    mode = _extract.clean(card.get("extraction_mode"))
    if mode not in {"detail_link", "nhb_dom_card"}:
        return None
    if int(card.get("detail_url_count") or 0) != 1:
        return None
    if not _browser.card_has_date(card) or not _official_feeds.card_title(card):
        return None
    canonical = _candidate_url(source, card)
    if not canonical:
        return None
    admitted = dict(card)
    admitted.update(
        url=canonical,
        page_url=canonical,
        listing_evidence=LISTING_EVIDENCE,
        listing_url=listing_url,
        listing_card_id=_extract.clean(card.get("id")),
        listing_extraction_mode=mode,
    )
    return admitted


def _merge_structured_with_listing(structured: dict[str, Any], listing: dict[str, Any]) -> dict[str, Any]:
    merged = dict(structured)
    canonical = _extract.clean(listing.get("url"))
    merged.update(
        url=canonical,
        page_url=canonical,
        detail_urls=[canonical],
        detail_url_count=1,
        listing_evidence=LISTING_EVIDENCE,
        listing_url=listing.get("listing_url") or "",
        listing_card_id=listing.get("listing_card_id") or "",
        listing_extraction_mode=listing.get("listing_extraction_mode") or "",
        screenshot=listing.get("screenshot") or "",
    )
    if isinstance(merged.get("structured_event"), dict):
        event = dict(merged["structured_event"])
        event["url"] = canonical
        merged["structured_event"] = event
    return merged


def _same_candidate(structured: dict[str, Any], listing: dict[str, Any]) -> bool:
    structured_url = _extract.clean(structured.get("url"))
    listing_url = _extract.clean(listing.get("url"))
    if structured_url == listing_url and structured_url.startswith(("http://", "https://")):
        return True
    structured_title = _official_feeds.card_title(structured)
    listing_title = _official_feeds.card_title(listing)
    return bool(structured_title and structured_title == listing_title)


def _prefer_structured(structured: list[dict[str, Any]], dom: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Use structured data only when a rendered official-list card proves membership."""
    source = getattr(_prefer_structured, "source", {})
    listing_url = str(getattr(_prefer_structured, "listing_url", ""))
    listing_cards = [item for card in dom if (item := _listing_card(source, card, listing_url))]
    unused = set(range(len(structured)))
    output: list[dict[str, Any]] = []
    for listing in listing_cards:
        matched_index = next(
            (index for index in sorted(unused) if _same_candidate(structured[index], listing)),
            None,
        )
        if matched_index is None:
            output.append(listing)
        else:
            unused.remove(matched_index)
            output.append(_merge_structured_with_listing(structured[matched_index], listing))
        if len(output) >= limit:
            break
    return output[:limit]


def _merge_detail(source: dict[str, Any], card: dict[str, Any], payload: dict[str, Any], index: int) -> dict[str, Any]:
    canonical = _extract.clean(payload.get("canonical"))
    if not canonical_detail_url(source, canonical):
        canonical = _candidate_url(source, card)
    events = _official_feeds.extract_structured_events(
        payload.get("eventObjects") or [],
        canonical,
        str(source.get("default_venue") or source.get("name") or ""),
        limit=1,
    )
    evidence = {
        "canonical_url": canonical,
        "title": _extract.clean(payload.get("title")),
        "date_candidates": [_extract.clean(item) for item in payload.get("dates") or [] if _extract.clean(item)],
        "venue_candidates": [_extract.clean(item) for item in payload.get("venues") or [] if _extract.clean(item)],
    }
    if events:
        event = dict(events[0])
        event["url"] = canonical
        merged = _official_feeds.event_card(event, str(source.get("id") or "source"), index)
    else:
        title = evidence["title"] or _extract.clean(card.get("link_text"))
        lines = [title, *evidence["date_candidates"], *evidence["venue_candidates"]]
        summary = _extract.clean(payload.get("summary"))
        if summary:
            lines.append(summary)
        lines.extend(_extract.clean(item) for item in (payload.get("lines") or [])[:80])
        deduped: list[str] = []
        for item in lines:
            if item and item not in deduped:
                deduped.append(item)
        merged = dict(card)
        merged.update(
            url=canonical,
            detail_urls=[canonical],
            detail_url_count=1,
            link_text=title,
            headings=[title] if title else list(card.get("headings") or []),
            text_lines=deduped,
            text="\n".join(deduped),
        )
    for key in ("listing_evidence", "listing_url", "listing_card_id", "listing_extraction_mode"):
        merged[key] = card.get(key) or ""
    merged["detail_enriched"] = True
    merged["detail_evidence"] = evidence
    merged["screenshot"] = card.get("screenshot") or ""
    return merged


def _enrich(source: dict[str, Any], cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Supplement admitted list cards; detail failure never creates or removes membership."""
    debug = {"candidates": len(cards), "enriched": 0, "errors": 0, "skipped_by_limit": max(0, len(cards) - DETAIL_LIMIT)}
    if not cards:
        return [], debug
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return cards, {**debug, "errors": min(len(cards), DETAIL_LIMIT)}

    output: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            for index, card in enumerate(cards):
                url = _candidate_url(source, card)
                if index >= DETAIL_LIMIT or not url:
                    output.append(card)
                    continue
                page = None
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=DETAIL_TIMEOUT_MS)
                    except Exception:
                        page.goto(url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
                    page.wait_for_timeout(650)
                    output.append(_merge_detail(source, card, page.evaluate(AUTHORITATIVE_DETAIL_JS) or {}, index))
                    debug["enriched"] += 1
                except Exception as exc:
                    failed = dict(card)
                    failed["detail_enrich_error"] = f"{type(exc).__name__}:{exc}"
                    output.append(failed)
                    debug["errors"] += 1
                finally:
                    if page is not None:
                        try:
                            page.close()
                        except Exception:
                            pass
        finally:
            browser.close()
    return output, debug


def _render(source: dict[str, Any], url: str, debug_dir, max_cards: int = 60):
    _prefer_structured.source = source
    _prefer_structured.listing_url = url
    rendered = dict(_base_render(source, url, debug_dir, max_cards=max(max_cards, int(source.get("max_cards", max_cards)))))
    cards, debug = _enrich(source, [card for card in rendered.get("cards") or [] if isinstance(card, dict)])
    rendered["cards"] = cards
    rendered["listing_authority"] = {
        "policy": LISTING_EVIDENCE,
        "admitted": len(cards),
        "unmatched_structured_records_are_dropped": True,
        "detail_enrichment": debug,
    }
    return rendered


def _event_end(event: dict[str, Any]) -> date | None:
    for value in (event.get("end_date"), event.get("start_date")):
        try:
            if value:
                return date.fromisoformat(_extract.clean(value)[:10])
        except ValueError:
            pass
    dates = _extract.label_dates(_extract.clean(event.get("when")))
    return max(dates) if dates else None


def _valid_title(value: object) -> str:
    title = _extract.normalise_title(value)
    if not title or _extract.GENERIC_TITLE_RE.match(title) or _extract.DATE_LINE_RE.search(title):
        return ""
    return _extract.short(title, 140)


def _venue(source: dict[str, Any], event: dict[str, Any], evidence: dict[str, Any]) -> str:
    for value in [*(evidence.get("venue_candidates") or []), event.get("where")]:
        venue = _extract.clean(value)
        if venue and len(venue) <= 140 and len(venue.split()) <= 16 and not NARRATIVE_VENUE_RE.search(venue):
            return venue
    return str(source.get("default_venue") or source.get("name") or "")


def _structured_event(source: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
    structured = card.get("structured_event")
    if not isinstance(structured, dict):
        return None
    title = _valid_title(structured.get("title"))
    when = _extract.clean(structured.get("when"))
    if not title or not when:
        return None
    where = _extract.clean(structured.get("where")) or str(source.get("default_venue") or source.get("name") or "")
    summary = _extract.clean(structured.get("summary")) or "Open the official page for details."
    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": _extract.clean(card.get("url")),
        "summary": summary,
        "start_date": _extract.clean(structured.get("start_date")) or _extract.best_start_date(when),
        "end_date": _extract.clean(structured.get("end_date")),
        "kind": "event",
        "source_type": "official_structured_data_matched_to_listing",
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": card.get("detail_url_count", 0),
    }


def _dom_event(source: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
    title = _extract.pick_title(card)
    when, when_line = _extract.pick_when(card)
    if not title or not when:
        return None
    where = _extract.pick_venue(source, card, when, when_line)
    summary = _extract.pick_summary(card, title, when, where)
    dates = _extract.label_dates(when)
    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": _extract.clean(card.get("url")),
        "summary": summary,
        "start_date": _extract.best_start_date(when),
        "end_date": max(dates).isoformat() if len(dates) >= 2 else "",
        "kind": "event",
        "source_type": "official_listing_card",
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": card.get("detail_url_count", 0),
    }


def _event(source: dict[str, Any], card: dict[str, Any]):
    if card.get("listing_evidence") != LISTING_EVIDENCE:
        return None, "missing_official_listing_evidence"
    url = _candidate_url(source, card)
    if not url:
        return None, "official_detail_url_not_found"

    event = _structured_event(source, card) or _dom_event(source, card)
    if not event:
        return None, "listing_card_fields_incomplete"
    event["url"] = url
    end = _event_end(event)
    if end and end < _extract.TODAY:
        return None, "past_date"
    if not end and not _extract.current_date_label(_extract.clean(event.get("when"))):
        return None, "past_date"

    evidence = card.get("detail_evidence") if isinstance(card.get("detail_evidence"), dict) else {}
    detail_title = _valid_title(evidence.get("title"))
    if detail_title:
        event["title"] = detail_title
    event["where"] = _venue(source, event, evidence)
    event["candidate_policy"] = "official-listing-authority-v1"
    event["listing_url"] = card.get("listing_url") or ""
    event["listing_card_id"] = card.get("listing_card_id") or ""

    package = sys.modules.get(__package__)
    repair = getattr(package, "_apply_gardens_card_fields", None)
    if callable(repair):
        event = repair(source, card, event)
    return event, "accepted"


def apply() -> None:
    global _applied, _base_render, _base_collect
    if _applied:
        return
    package = sys.modules.get(__package__)
    _patch_browser()
    _base_render = _extract.render_listing_cards
    _base_collect = getattr(package, "collect_events", None)
    _extract.PAST_GRACE_DAYS = 0
    _extract.MAX_EVENTS_PER_SOURCE = max(_extract.MAX_EVENTS_PER_SOURCE, 40)
    _extract.SOURCE_TIMEOUT_SECONDS = max(_extract.SOURCE_TIMEOUT_SECONDS, 160)
    _official_feeds.prefer_structured_cards = _prefer_structured
    _extract.render_listing_cards = _render
    _extract.event_from_card = _event
    if package is not None:
        package.event_from_card = _extract.event_from_card
        if callable(_base_collect):
            def collect_events(*args, **kwargs):
                payload = dict(_base_collect(*args, **kwargs))
                payload.update(version=52, extractor="listing-authoritative-v52")
                return payload

            package.collect_events = collect_events
    _applied = True


__all__ = [
    "apply",
    "canonical_detail_url",
    "DEEP_SCROLL_JS",
    "LISTING_EVIDENCE",
    "_listing_card",
    "_merge_detail",
    "_prefer_structured",
]
