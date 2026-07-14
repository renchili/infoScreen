#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from local_events_runtime import browser as browser_runtime

SURFACE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SURFACE_DIR / "conf" / "event_sources.json"
OUTPUT_DIR = SURFACE_DIR / ".env" / "local_event_input_probe"

MATCH_PROBE_JS = r"""
(args) => {
  const needle = String(args.match || "").trim().toLowerCase();
  const maxOuterHtml = Number(args.maxOuterHtml || 30000);

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function attrs(el) {
    const out = {};
    if (!el || !el.attributes) return out;
    for (const attr of Array.from(el.attributes)) {
      out[attr.name] = attr.value;
    }
    return out;
  }

  function nodeInfo(el) {
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      tag: el.tagName,
      text: clean(el.innerText || el.textContent || "").slice(0, 5000),
      attrs: attrs(el),
      rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      outer_html: String(el.outerHTML || "").slice(0, maxOuterHtml),
    };
  }

  function clickableInfo(root) {
    if (!root) return [];
    const selectors = "a[href], button, [role='button'], [onclick], [routerlink], [data-href], [data-url], [data-link], [data-route]";
    const nodes = [];
    if (root.matches && root.matches(selectors)) nodes.push(root);
    nodes.push(...Array.from(root.querySelectorAll(selectors)));
    const seen = new Set();
    const out = [];
    for (const el of nodes) {
      const key = `${el.tagName}|${el.getAttribute('href') || ''}|${el.getAttribute('data-href') || ''}|${el.getAttribute('data-url') || ''}|${clean(el.innerText || el.textContent || '')}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        tag: el.tagName,
        text: clean(el.innerText || el.textContent || el.getAttribute("aria-label") || "").slice(0, 1000),
        attrs: attrs(el),
        href: el.href || "",
      });
      if (out.length >= 80) break;
    }
    return out;
  }

  const all = Array.from(document.querySelectorAll("body *"));
  const matching = needle
    ? all.filter(el => clean(el.innerText || el.textContent || "").toLowerCase().includes(needle))
    : [];
  const leaves = matching.filter(el => !Array.from(el.children || []).some(child => clean(child.innerText || child.textContent || "").toLowerCase().includes(needle)));
  const selected = (leaves.length ? leaves : matching).slice(0, 20);

  const matches = selected.map((el) => {
    const ancestors = [];
    let current = el;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      ancestors.push({
        depth,
        node: nodeInfo(current),
        clickables: clickableInfo(current),
      });
    }
    return {leaf: nodeInfo(el), ancestors};
  });

  const directAnchors = Array.from(document.querySelectorAll("a[href]"))
    .filter(a => {
      const text = clean(a.innerText || a.textContent || a.getAttribute("aria-label") || "");
      const alt = clean(Array.from(a.querySelectorAll("img[alt]")).map(img => img.getAttribute("alt")).join(" "));
      return needle && `${text} ${alt}`.toLowerCase().includes(needle);
    })
    .slice(0, 50)
    .map(a => ({
      text: clean(a.innerText || a.textContent || a.getAttribute("aria-label") || ""),
      attrs: attrs(a),
      href: a.href || "",
      outer_html: String(a.outerHTML || "").slice(0, maxOuterHtml),
    }));

  const bodyText = clean(document.body ? document.body.innerText : "");
  const bodyLower = bodyText.toLowerCase();
  const position = needle ? bodyLower.indexOf(needle) : -1;
  const contextStart = Math.max(0, position - 1500);
  const contextEnd = position >= 0 ? Math.min(bodyText.length, position + needle.length + 3000) : 0;

  return {
    page_url: document.location.href,
    page_title: document.title,
    match: args.match,
    matching_element_count: matching.length,
    leaf_match_count: leaves.length,
    direct_anchor_count: directAnchors.length,
    body_text_context: position >= 0 ? bodyText.slice(contextStart, contextEnd) : "",
    direct_anchors: directAnchors,
    matches,
  };
}
"""


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "source"


def load_source(source_id: str) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for source in config.get("sources") or []:
        if str(source.get("id") or "").lower() == source_id.lower():
            return source
    available = ", ".join(str(item.get("id")) for item in config.get("sources") or [])
    raise SystemExit(f"unknown source {source_id!r}; available: {available}")


def probe(source: dict[str, Any], match: str) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit("missing playwright: python3 -m pip install --user playwright") from exc

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_id = slug(source.get("id") or source.get("name"))
    results: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = browser_runtime.launch_chromium(playwright)
        try:
            for index, listing_url in enumerate(source.get("listing_urls") or []):
                page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
                response = None
                navigation_error = ""
                try:
                    try:
                        response = page.goto(listing_url, wait_until="networkidle", timeout=browser_runtime.NAV_TIMEOUT_MS)
                    except Exception as exc:
                        navigation_error = f"networkidle:{type(exc).__name__}:{exc}"
                        response = page.goto(listing_url, wait_until="domcontentloaded", timeout=browser_runtime.DOM_TIMEOUT_MS)
                    page.wait_for_timeout(max(browser_runtime.LOAD_WAIT_MS, 1200))
                    prepare = page.evaluate(
                        browser_runtime.PREPARE_PAGE_JS,
                        {"maxRounds": int(source.get("load_more_rounds", browser_runtime.LOAD_MORE_ROUNDS))},
                    )
                    page.wait_for_timeout(500)

                    prefix = f"{source_id}-{index}"
                    html_path = OUTPUT_DIR / f"{prefix}-page.html"
                    json_path = OUTPUT_DIR / f"{prefix}-match.json"
                    screenshot_path = OUTPUT_DIR / f"{prefix}-page.png"

                    html_path.write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    evidence = page.evaluate(MATCH_PROBE_JS, {"match": match, "maxOuterHtml": 30000})
                    evidence.update(
                        {
                            "source_id": source.get("id"),
                            "source_name": source.get("name"),
                            "requested_url": listing_url,
                            "final_url": page.url,
                            "http_status": response.status if response is not None else None,
                            "response_url": response.url if response is not None else "",
                            "navigation_error": navigation_error,
                            "prepare": prepare,
                            "html_path": str(html_path),
                            "screenshot_path": str(screenshot_path),
                        }
                    )
                    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                    results.append(
                        {
                            "source": source.get("name"),
                            "requested_url": listing_url,
                            "final_url": page.url,
                            "http_status": evidence.get("http_status"),
                            "matching_element_count": evidence.get("matching_element_count"),
                            "leaf_match_count": evidence.get("leaf_match_count"),
                            "direct_anchor_count": evidence.get("direct_anchor_count"),
                            "html": str(html_path),
                            "evidence": str(json_path),
                            "screenshot": str(screenshot_path),
                        }
                    )
                finally:
                    page.close()
        finally:
            browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the exact rendered input used to diagnose a local-event source.")
    parser.add_argument("--source", required=True, help="event source id from surface/conf/event_sources.json")
    parser.add_argument("--match", required=True, help="event title or unique text to locate in the rendered page")
    args = parser.parse_args()

    source = load_source(args.source)
    print(json.dumps(probe(source, args.match), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
