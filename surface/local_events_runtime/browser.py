from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any


class MissingPlaywright(RuntimeError):
    pass


PREPARE_PAGE_JS = r"""
async (args) => {
  const maxRounds = args.maxRounds || 8;
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

  let clicks = 0;
  let lastHeight = 0;
  for (let round = 0; round < maxRounds; round++) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(900);

    const controls = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs)\b/i.test(clickableText(el)));

    if (controls.length) {
      try {
        controls[0].scrollIntoView({block: "center"});
        await sleep(250);
        controls[0].click();
        clicks += 1;
        await sleep(1400);
      } catch (e) {}
    }

    const height = document.body.scrollHeight;
    if (!controls.length && Math.abs(height - lastHeight) < 20) break;
    lastHeight = height;
  }
  window.scrollTo(0, 0);
  await sleep(300);
  return {clicks, height: document.body.scrollHeight};
}
"""


CARD_JS = r"""
(args) => {
  const allowedDomains = args.allowedDomains || [];
  const maxCards = args.maxCards || 160;
  const sourceId = args.sourceId || "source";

  function clean(value) {
    return String(value || "").replace(/[ \t\f\v]+/g, " ").replace(/\n\s+/g, "\n").replace(/\s+\n/g, "\n").trim();
  }

  function oneLine(value) {
    return clean(value).replace(/\s+/g, " ").trim();
  }

  function textLines(el) {
    const raw = String((el && el.innerText) || (el && el.textContent) || "").replace(/\r/g, "\n");
    return raw.split("\n").map(oneLine).filter(Boolean);
  }

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 40 && r.height >= 18 && r.bottom >= 0 && r.right >= 0;
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

  function detailUrls(el) {
    const urls = [];
    for (const a of Array.from(el.querySelectorAll("a[href]"))) {
      let abs = "";
      try { abs = new URL(a.getAttribute("href"), document.location.href).href; } catch { continue; }
      if (sameDomain(abs) && pathRole(abs) === "detail" && !urls.includes(abs)) urls.push(abs);
    }
    return urls;
  }

  function scoreContainer(el, anchor) {
    if (!el || !visible(el)) return -999;
    const r = el.getBoundingClientRect();
    const lines = textLines(el);
    const text = lines.join(" ");
    if (text.length < 8 || r.width < 80 || r.height < 35) return -999;
    let score = 0;
    const attrs = oneLine([el.className, el.id, el.getAttribute("role"), el.getAttribute("aria-label")].join(" "));
    const detailCount = detailUrls(el).length;
    if (/\b(card|tile|item|event|programme|program|exhibition|listing|result)\b/i.test(attrs)) score += 45;
    if (/^(ARTICLE|LI)$/i.test(el.tagName)) score += 35;
    if (el.querySelector("h1,h2,h3,h4")) score += 25;
    if (/\b20\d{2}\b|\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)/i.test(text)) score += 55;
    if (/\b\d{1,2}(:|\.)\d{2}\s*(am|pm)?\b|\b\d{1,2}\s*(am|pm)\b|daily|selected dates/i.test(text)) score += 10;
    if (lines.length >= 3) score += 16;
    if (detailCount === 1) score += 35;
    if (detailCount > 1) score -= 120 * (detailCount - 1);
    if (r.height > 900 || text.length > 1800) score -= 55;
    if (r.height > 1600 || text.length > 5500) score -= 90;
    if (anchor && !el.contains(anchor)) score -= 200;
    return score;
  }

  function bestCard(anchor) {
    const candidates = [];
    let el = anchor;
    for (let depth = 0; el && depth < 10; depth++, el = el.parentElement) {
      candidates.push(el);
    }
    const closest = anchor.closest("article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]");
    if (closest) candidates.push(closest);
    candidates.sort((a, b) => scoreContainer(b, anchor) - scoreContainer(a, anchor));
    const singleDetail = candidates.find(el => detailUrls(el).length === 1 && scoreContainer(el, anchor) > -999);
    return singleDetail || candidates[0] || anchor;
  }

  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));

  for (const a of anchors) {
    const abs = new URL(a.getAttribute("href"), document.location.href).href;
    if (!sameDomain(abs) || pathRole(abs) !== "detail") continue;

    const card = bestCard(a);
    const r = card.getBoundingClientRect();
    const lines = textLines(card);
    const text = lines.join("\n");
    const headings = Array.from(card.querySelectorAll("h1,h2,h3,h4")).map(h => oneLine(h.innerText || h.textContent)).filter(Boolean);
    const imgAlts = Array.from(card.querySelectorAll("img[alt]")).map(img => oneLine(img.getAttribute("alt"))).filter(Boolean);
    const linkText = oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    const cardDetailUrls = detailUrls(card);
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
      text_lines: lines,
      detail_url_count: cardDetailUrls.length,
      detail_urls: cardDetailUrls.slice(0, 8),
      rect: {x: r.x, y: r.y, width: r.width, height: r.height},
      role: pathRole(abs)
    });
    if (out.length >= maxCards) break;
  }
  return out;
}
"""


def find_browser_executable() -> str:
    env_path = os.environ.get("INFOSCREEN_CHROMIUM_PATH") or os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    candidates = [
        env_path,
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("microsoft-edge"),
        shutil.which("microsoft-edge-stable"),
        shutil.which("brave-browser"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/snap/bin/chromium",
    ]
    for value in candidates:
        if value and Path(value).exists():
            return str(value)
    return ""


def launch_chromium(playwright):
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-background-networking",
    ]
    executable = find_browser_executable()
    if executable:
        return playwright.chromium.launch(headless=True, executable_path=executable, args=args)
    try:
        return playwright.chromium.launch(headless=True, args=args)
    except Exception as exc:
        raise MissingPlaywright(
            "missing_system_chromium: Playwright bundled Chromium is unavailable on this distro. "
            "Install a system browser and set INFOSCREEN_CHROMIUM_PATH if needed. "
            "Examples: sudo apt install chromium; or install Google Chrome and export INFOSCREEN_CHROMIUM_PATH=/usr/bin/google-chrome. "
            f"Original error: {exc}"
        ) from exc


def render_listing_cards(source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 160) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment image
        raise MissingPlaywright("missing_playwright_python_package: python3 -m pip install --user playwright") from exc

    debug_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^a-z0-9]+", "-", str(source.get("id") or source.get("name") or "source").lower()).strip("-") or "source"
    allowed = [str(item).lower().replace("www.", "") for item in source.get("allowed_domains") or []]

    with sync_playwright() as p:
        browser = launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)
            prepare = page.evaluate(PREPARE_PAGE_JS, {"maxRounds": 8})
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

            return {"ok": True, "url": url, "prepare": prepare, "screenshot": str(screenshot_path), "cards": cards}
        finally:
            browser.close()
