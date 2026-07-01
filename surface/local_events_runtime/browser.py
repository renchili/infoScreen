from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any


class MissingPlaywright(RuntimeError):
    pass


MAX_LISTING_PAGES = int(os.environ.get("LOCAL_EVENTS_MAX_LISTING_PAGES", "1"))
LOAD_MORE_ROUNDS = int(os.environ.get("LOCAL_EVENTS_LOAD_MORE_ROUNDS", "0"))
NAV_TIMEOUT_MS = int(os.environ.get("LOCAL_EVENTS_NAV_TIMEOUT_MS", "12000"))
DOM_TIMEOUT_MS = int(os.environ.get("LOCAL_EVENTS_DOM_TIMEOUT_MS", "12000"))
LOAD_WAIT_MS = int(os.environ.get("LOCAL_EVENTS_LOAD_WAIT_MS", "550"))
NEXT_WAIT_MS = int(os.environ.get("LOCAL_EVENTS_NEXT_WAIT_MS", "700"))
PAGE_SCREENSHOTS = os.environ.get("LOCAL_EVENTS_PAGE_SCREENSHOTS", "0") == "1"
CARD_SCREENSHOTS = os.environ.get("LOCAL_EVENTS_CARD_SCREENSHOTS", "0") == "1"


PREPARE_PAGE_JS = r"""
async (args) => {
  const maxRounds = args.maxRounds || 0;
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
    await sleep(450);

    const controls = Array.from(document.querySelectorAll("button, a[href], [role='button']"))
      .filter(visible)
      .filter(el => /\b(load more|show more|view more|more events|more programmes|more programs)\b/i.test(clickableText(el)));

    if (controls.length) {
      try {
        controls[0].scrollIntoView({block: "center"});
        await sleep(150);
        controls[0].click();
        clicks += 1;
        await sleep(650);
      } catch (e) {}
    }

    const height = document.body.scrollHeight;
    if (!controls.length && Math.abs(height - lastHeight) < 20) break;
    lastHeight = height;
  }
  window.scrollTo(0, 0);
  await sleep(150);
  return {clicks, height: document.body.scrollHeight};
}
"""


CLICK_NEXT_PAGE_JS = r"""
async (args) => {
  const allowedDomains = args.allowedDomains || [];
  const pageIndex = args.pageIndex || 0;
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  function oneLine(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 20 && r.height >= 18 && r.bottom >= 0 && r.right >= 0;
  }

  function disabled(el) {
    const cls = oneLine(el.className).toLowerCase();
    return el.disabled || el.getAttribute("aria-disabled") === "true" || cls.includes("disabled") || cls.includes("is-disabled");
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

  function controlText(el) {
    return oneLine([el.innerText, el.textContent, el.getAttribute("aria-label"), el.getAttribute("title")].join(" "));
  }

  function safeListingHref(el) {
    if (el.tagName !== "A") return true;
    const href = el.getAttribute("href") || "";
    if (!href || href === "#" || href.startsWith("javascript:")) return true;
    const abs = new URL(href, document.location.href).href;
    if (!sameDomain(abs)) return false;
    return pathRole(abs) !== "detail";
  }

  function isNextControl(el) {
    if (!visible(el) || disabled(el) || !safeListingHref(el)) return false;
    const text = controlText(el);
    if (!text) return false;
    if (/\b(next programme|next program|next exhibition|next event|next article)\b/i.test(text)) return false;
    return /^(next|>|›|»|→)$/i.test(text) || /\b(next page|go to next|page next|next results?)\b/i.test(text) || /下一页|下一頁/.test(text);
  }

  function isNumericNextControl(el) {
    if (!visible(el) || disabled(el) || !safeListingHref(el)) return false;
    const text = controlText(el);
    if (!/^\d+$/.test(text)) return false;
    const n = Number(text);
    return n === pageIndex + 2;
  }

  function score(el) {
    let score = 0;
    const text = controlText(el);
    const attrs = oneLine([el.className, el.id, el.getAttribute("role"), el.closest("nav,[class*='pager' i],[class*='pagination' i],[class*='page' i]")?.className].join(" "));
    if (/\b(pager|pagination|page|next)\b/i.test(attrs)) score += 50;
    if (/^(next|>|›|»|→)$/i.test(text)) score += 25;
    if (/^\d+$/.test(text)) score += 15;
    const r = el.getBoundingClientRect();
    score += Math.max(0, 1200 - r.top) / 100;
    return score;
  }

  const candidates = Array.from(document.querySelectorAll("a[href], button, [role='button']"))
    .filter(el => isNextControl(el) || isNumericNextControl(el))
    .sort((a, b) => score(b) - score(a));

  if (!candidates.length) return {clicked: false, reason: "next_control_not_found", expectedNumericPage: pageIndex + 2};
  const el = candidates[0];
  const beforeHref = document.location.href;
  const beforeTextLength = oneLine(document.body.innerText).length;
  const text = controlText(el);
  try {
    el.scrollIntoView({block: "center"});
    await sleep(180);
    el.click();
    await sleep(700);
    return {clicked: true, text, expectedNumericPage: pageIndex + 2, beforeHref, afterHref: document.location.href, beforeTextLength, afterTextLength: oneLine(document.body.innerText).length};
  } catch (e) {
    return {clicked: false, text, reason: String(e), expectedNumericPage: pageIndex + 2};
  }
}
"""


CARD_JS = r"""
(args) => {
  const allowedDomains = args.allowedDomains || [];
  const maxCards = args.maxCards || 60;
  const sourceId = args.sourceId || "source";
  const pageIndex = args.pageIndex || 0;
  const adapter = args.adapter || "rendered_dom_card";
  const officialHome = args.officialHome || "";

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

  function sameDomainNonListingUrls(el) {
    const urls = [];
    for (const a of Array.from(el.querySelectorAll("a[href]"))) {
      let abs = "";
      try { abs = new URL(a.getAttribute("href"), document.location.href).href; } catch { continue; }
      if (!sameDomain(abs)) continue;
      if (pathRole(abs) === "listing") continue;
      if (!urls.includes(abs)) urls.push(abs);
    }
    return urls;
  }

  function textHash(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(16);
  }

  function hasDateText(text) {
    return /\b20\d{2}\b|\b\d{1,2}\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/i.test(text);
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
    if (hasDateText(text)) score += 55;
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

  function cardPayload(el, url, linkText, extractionMode) {
    const r = el.getBoundingClientRect();
    const lines = textLines(el);
    const text = lines.join("\n");
    const headings = Array.from(el.querySelectorAll("h1,h2,h3,h4")).map(h => oneLine(h.innerText || h.textContent)).filter(Boolean);
    const imgAlts = Array.from(el.querySelectorAll("img[alt]")).map(img => oneLine(img.getAttribute("alt"))).filter(Boolean);
    const cardDetailUrls = detailUrls(el);
    const id = `${sourceId}-${pageIndex}-${textHash(url + text.slice(0, 500))}`;
    el.setAttribute("data-infoscreen-card-id", id);
    return {
      id,
      url,
      link_text: linkText || "",
      headings,
      image_alts: imgAlts,
      text,
      text_lines: lines,
      detail_url_count: cardDetailUrls.length,
      detail_urls: cardDetailUrls.slice(0, 8),
      page_index: pageIndex,
      page_url: document.location.href,
      rect: {x: r.x, y: r.y, width: r.width, height: r.height},
      role: pathRole(url),
      extraction_mode: extractionMode
    };
  }

  function push(out, seen, el, url, linkText, extractionMode) {
    if (!el || out.length >= maxCards) return;
    const text = textLines(el).join("\n");
    const key = (url || "") + "\n" + text.slice(0, 500);
    if (!text.trim() || seen.has(key)) return;
    seen.add(key);
    out.push(cardPayload(el, url, linkText, extractionMode));
  }

  function nhbCard(el) {
    if (!el || !visible(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.height > 900 || r.width < 120) return false;
    const lines = textLines(el);
    const text = lines.join(" ");
    if (text.length < 25 || text.length > 1800 || lines.length < 2) return false;
    if (!hasDateText(text)) return false;
    const attrs = oneLine([el.className, el.id, el.getAttribute("role"), el.getAttribute("aria-label")].join(" "));
    if (/\b(filter|breadcrumb|pagination|pager|header|footer|nav|menu|modal|cookie|newsletter|search)\b/i.test(attrs)) return false;
    if (/^(HEADER|FOOTER|NAV|FORM|SELECT|OPTION)$/i.test(el.tagName)) return false;
    const childCards = Array.from(el.querySelectorAll("article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]")).filter(child => child !== el && visible(child) && hasDateText(textLines(child).join(' ')));
    if (childCards.length >= 2) return false;
    return true;
  }

  function pushNhbCards(out, seen) {
    const selectors = "article, li, [class*='card' i], [class*='tile' i], [class*='event' i], [class*='programme' i], [class*='program' i], [class*='exhibition' i], [class*='listing' i], [class*='result' i]";
    const candidates = Array.from(document.querySelectorAll(selectors))
      .filter(nhbCard)
      .sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        return ar.top - br.top || ar.left - br.left;
      });
    for (const el of candidates) {
      const text = textLines(el).join("\n");
      const base = officialHome || document.location.origin;
      const url = detailUrls(el)[0] || sameDomainNonListingUrls(el)[0] || (base.replace(/\/$/, '') + '#nhb-' + textHash(text.slice(0, 600)));
      push(out, seen, el, url, "", "nhb_dom_card");
      if (out.length >= maxCards) break;
    }
  }

  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll("a[href]")).filter(a => visible(a));

  for (const a of anchors) {
    const abs = new URL(a.getAttribute("href"), document.location.href).href;
    if (!sameDomain(abs) || pathRole(abs) !== "detail") continue;
    const card = bestCard(a);
    const linkText = oneLine(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
    push(out, seen, card, abs, linkText, "detail_link");
    if (out.length >= maxCards) break;
  }

  if (adapter === "nhb" && out.length < maxCards) {
    pushNhbCards(out, seen);
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


def render_listing_cards(source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 60) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment image
        raise MissingPlaywright("missing_playwright_python_package: python3 -m pip install --user playwright") from exc

    debug_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^a-z0-9]+", "-", str(source.get("id") or source.get("name") or "source").lower()).strip("-") or "source"
    allowed = [str(item).lower().replace("www.", "") for item in source.get("allowed_domains") or []]
    adapter = str(source.get("adapter") or "rendered_dom_card")
    official_home = str(source.get("official_home") or "")
    load_more_rounds = int(source.get("load_more_rounds", 1 if adapter == "nhb" else LOAD_MORE_ROUNDS))

    with sync_playwright() as p:
        browser = launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
            try:
                page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=DOM_TIMEOUT_MS)
            page.wait_for_timeout(LOAD_WAIT_MS)

            all_cards: list[dict[str, Any]] = []
            seen_cards = set()
            screenshots: list[str] = []
            pagination: list[dict[str, Any]] = []
            rendered_pages = 0

            for page_index in range(MAX_LISTING_PAGES):
                prepare = page.evaluate(PREPARE_PAGE_JS, {"maxRounds": load_more_rounds})
                page_cards = page.evaluate(CARD_JS, {"allowedDomains": allowed, "maxCards": max_cards, "sourceId": source_id, "pageIndex": page_index, "adapter": adapter, "officialHome": official_home})
                if PAGE_SCREENSHOTS:
                    page_screenshot = debug_dir / f"{source_id}-{hashlib.sha1((url + str(page_index)).encode()).hexdigest()[:10]}-page-{page_index}.png"
                    page.screenshot(path=str(page_screenshot), full_page=True)
                    screenshots.append(str(page_screenshot))
                rendered_pages += 1
                new_count = 0

                for card in page_cards:
                    key = (card.get("url") or "") + "\n" + (card.get("text") or "")[:500]
                    if not key.strip() or key in seen_cards:
                        continue
                    seen_cards.add(key)
                    cid = card.get("id")
                    if CARD_SCREENSHOTS and cid:
                        crop_path = debug_dir / f"{source_id}-{page_index}-{len(card.get('text', ''))}-{hashlib.sha1((card.get('url', '') + cid).encode()).hexdigest()[:10]}.png"
                        try:
                            page.locator(f"[data-infoscreen-card-id='{cid}']").first.screenshot(path=str(crop_path), timeout=2000)
                            card["screenshot"] = str(crop_path)
                        except Exception:
                            card["screenshot"] = ""
                    else:
                        card["screenshot"] = ""
                    all_cards.append(card)
                    new_count += 1
                    if len(all_cards) >= max_cards:
                        break

                pagination.append({"page_index": page_index, "url": page.url, "prepare": prepare, "cards": len(page_cards), "new_cards": new_count})
                if len(all_cards) >= max_cards or page_index >= MAX_LISTING_PAGES - 1:
                    break

                next_result = page.evaluate(CLICK_NEXT_PAGE_JS, {"allowedDomains": allowed, "pageIndex": page_index})
                pagination[-1]["next"] = next_result
                if not next_result.get("clicked"):
                    break
                try:
                    page.wait_for_load_state("networkidle", timeout=NEXT_WAIT_MS)
                except Exception:
                    page.wait_for_timeout(NEXT_WAIT_MS)
                page.wait_for_timeout(300)

            return {"ok": True, "url": url, "rendered_pages": rendered_pages, "pagination": pagination, "screenshot": screenshots[0] if screenshots else "", "screenshots": screenshots, "cards": all_cards}
        finally:
            browser.close()
