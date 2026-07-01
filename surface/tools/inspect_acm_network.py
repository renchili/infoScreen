#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_URL = "https://www.acm.nhb.gov.sg/whats-on/overview?category=Exhibitions%2CLectures%2CProgrammes%2CGuided+Tours&time=Today%2CUpcoming"
SURFACE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SURFACE_DIR.parent
OUT = SURFACE_DIR / ".env" / "acm_network_debug.json"

if str(SURFACE_DIR) not in sys.path:
    sys.path.insert(0, str(SURFACE_DIR))

from local_events_runtime.browser import launch_chromium  # noqa: E402

JSON_HINT_RE = re.compile(r"(?:/api/|graphql|search|event|events|programme|programmes|exhibition|exhibitions|whatson|whats-on|_next/data|sitecore|jss)", re.I)


BUTTONS_JS = r"""
() => Array.from(document.querySelectorAll('button,a,[role=button]')).map(el => ({
  tag: el.tagName,
  text: String(el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim(),
  href: el.href || '',
  cls: String(el.className || '')
})).filter(x => x.text || x.href).slice(0, 200)
"""


SCRIPTS_JS = r"""
() => Array.from(document.querySelectorAll('script[src],script[type*=json],script#__NEXT_DATA__')).map(s => ({
  id: s.id || '',
  type: s.type || '',
  src: s.src || '',
  size: (s.textContent || '').length,
  preview: String(s.textContent || '').slice(0, 500)
})).slice(0, 80)
"""


def short(text: str, limit: int = 800) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect ACM/NHB network calls used by the official listing page.")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--seconds", type=float, default=12.0)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"missing playwright: {exc}")

    target = args.url
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    captured: list[dict] = []
    failed: list[dict] = []

    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})

        def on_response(resp):
            url = resp.url
            ctype = (resp.headers.get("content-type") or "").lower()
            if not ("json" in ctype or JSON_HINT_RE.search(url)):
                return
            item = {
                "url": url,
                "status": resp.status,
                "content_type": ctype,
                "method": resp.request.method,
                "resource_type": resp.request.resource_type,
                "query": parse_qs(urlparse(url).query),
                "preview": "",
                "json_keys": [],
            }
            try:
                body = resp.text(timeout=2500)
                item["preview"] = short(body)
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        item["json_keys"] = sorted(list(parsed.keys()))[:60]
                    elif isinstance(parsed, list):
                        item["json_keys"] = [f"list[{len(parsed)}]"]
                except Exception:
                    pass
            except Exception as exc:
                item["preview_error"] = f"{type(exc).__name__}:{exc}"
            captured.append(item)

        def on_request_failed(req):
            if JSON_HINT_RE.search(req.url):
                failed.append({"url": req.url, "method": req.method, "resource_type": req.resource_type, "failure": str(req.failure)})

        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)

        try:
            page.goto(target, wait_until="networkidle", timeout=20000)
        except Exception:
            page.goto(target, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(int(args.seconds * 1000))

        buttons = page.evaluate(BUTTONS_JS)
        scripts = page.evaluate(SCRIPTS_JS)
        text_preview = page.evaluate("() => document.body ? document.body.innerText.slice(0, 5000) : ''")
        browser.close()

    payload = {
        "target": target,
        "captured_count": len(captured),
        "captured": captured,
        "failed": failed,
        "buttons": buttons,
        "scripts": scripts,
        "text_preview": text_preview,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"captured_count={len(captured)}")
    for item in captured[:30]:
        print(item["status"], item["method"], item["resource_type"], item["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
