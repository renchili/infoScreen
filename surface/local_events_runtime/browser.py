from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class MissingPlaywright(RuntimeError):
    pass


CARD_JS = r"""
(args) => {
  const allowedDomains = args.allowedDomains || [];
  const maxCards = args.maxCards || 80;
  const sourceId = args.sourceId || "source";

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 80 && r.height >= 50 && r.bottom >= 0 && r.right >= 0;
  }

  function sameDomain(raw) {
    let u;
    try { u = new URL(raw, document.location.href); } catch { return false; }
    const h = u.hostname.replace(/^www\./, "").toLowerCase();
    return allowedDomains.some(d => h === String(d).replace(/^www\./, "").toLowerCase() || h.endsWith("." + String(d).replace(/^www\./, "").toLowerCase()));
  }

  function pathRole(raw) {
    let u;
    try { u = new URL(raw, document.location.href); } catch { return "other"; }
    const path = decodeURIComponent(u.pathname.toLowerCase()).replace(/\/$/, "");
    const parts = path.split("/").filter(Boolean);
    const leaf = (parts[parts.length - 1] || "").replace(/\.html$/, "");
    const generic = new Set(["", "whats-on", "whatson", "overview", "view-all", "events", "event", "exhibition", "exhibitions", "programme", "programmes", "program", "programs", "activities", "activity", "guided-tours"]);
    if (/[?&](category|filter|time|date|type|page)=/i.test(u.search)) return "listing";
    if (generic.has(leaf)) return "listing";
    if (/\/(whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|guided-tours|discover-mandai\/events)\//i.test(path + "/")) return "detail";
    return "other";
  }

  function scoreContainer(el, anchor) {
    if (!el || !visible(el)) return -999;
    const r = el.getBoundingClientRect();
    const text = clean(el.innerText || el.textContent || "");
    if (text.length < 8 || r.width < 100 || r.height < 60) return -999;
    let score = 0;
    const attrs = clean([el.className, el.id, el.getAttribute("role"), el.getAttribute("aria-label")].join(" "));
    if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs)) score += 40;
    if (/^(ARTICLE|LI)$/i.test(el.tagName)) score += 30;
    if (el.querySelector("h1,h2,h3,h4")) score += 25;
    if (/\b20\d{2}\b|\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)/i.test(text)) score += 50;
    if (/\b\d{1,2}(:|\.)\d{2}\s*(am|pm)?\b|\b\d{1,2}\s*(am|pm)\b/i.test(text)) score += 8;
    if (r.height > 1200 || text.length > 4000) score -= 60;
    if (anchor && !el.contains(anchor)) score -= 200;
    return score;
  }

  function bestCard(anchor) {
    const candidates = [];
    let el = anchor;
    for (let depth = 0; el && depth < 8; depth++, el = el.parentElement) {
      candidates.push(el);
    }
    const closest = anchor.closest("article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]");
    if (closest) candidates.push(closest);
    candidates.sort((a, b) => scoreContainer(b, anchor) - scoreContainer(a, anchor));
    return candidates[0] || anchor;
  }

  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));

  for (const a of anchors) {
    const abs = new URL(a.getAttribute("href"), document.location.href).href;
    if (!sameDomain(abs) || pathRole(abs) !== "detail") continue;

    const card = bestCard(a);
    const r = card.getBoundingClientRect();
    const text = clean(card.innerText || card.textContent || "");
    const headings = Array.from(card.querySelectorAll("h1,h2,h3,h4")).map(h => clean(h.innerText || h.textContent)).filter(Boolean);
    const imgAlts = Array.from(card.querySelectorAll("img[alt]")).map(img => clean(img.getAttribute("alt"))).filter(Boolean);
    const linkText = clean(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    const key = abs + "\n" + text.slice(0, 500);
    if (seen.has(key)) continue;
    seen.add(key);

    const id = `${sourceId}-${out.length}-${Math.random().toString(36).slice(2)}`;
    card.setAttribute("data-infoscreen-card-id", id);
    out.push({
      id,
      url: abs,
      link_text: linkText,
      headings,
      image_alts: imgAlts,
      text,
      rect: {x: r.x, y: r.y, width: r.width, height: r.height},
      role: pathRole(abs)
    });
    if (out.length >= maxCards) break;
  }
  return out;
}
"""


def render_listing_cards(source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 80) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment image
        raise MissingPlaywright("missing_playwright: install python package 'playwright' and browser runtime") from exc

    debug_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^a-z0-9]+", "-", str(source.get("id") or source.get("name") or "source").lower()).strip("-") or "source"
    allowed = [str(item).lower().replace("www.", "") for item in source.get("allowed_domains") or []]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1800)

        cards = page.evaluate(CARD_JS, {"allowedDomains": allowed, "maxCards": max_cards, "sourceId": source_id})
        screenshot_path = debug_dir / f"{source_id}-{hashlib.sha1(url.encode()).hexdigest()[:10]}-page.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        for card in cards:
            cid = card.get("id")
            if not cid:
                continue
            crop_path = debug_dir / f"{source_id}-{len(card.get('text', ''))}-{hashlib.sha1((card.get('url', '') + cid).encode()).hexdigest()[:10]}.png"
            try:
                page.locator(f"[data-infoscreen-card-id='{cid}']").first.screenshot(path=str(crop_path), timeout=2500)
                card["screenshot"] = str(crop_path)
            except Exception:
                card["screenshot"] = ""

        browser.close()
        return {"ok": True, "url": url, "screenshot": str(screenshot_path), "cards": cards}
