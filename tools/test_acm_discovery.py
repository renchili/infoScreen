#!/usr/bin/env python3
"""Debug ACM event discovery from a listing page.

This script is intentionally separate from the production local-event crawler.
It tests whether a crawler can discover event detail URLs from ACM's listing page
without hardcoding the event into the crawler output.

Usage:
  python3 tools/test_acm_discovery.py \
    --list-url https://www.acm.nhb.gov.sg/whats-on/view-all \
    --expect-url https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents-masterpieces-of-mughal-safavid-and-ottoman-art-from-the-musee-du-louvre
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
A_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', re.I)
JSON_URL_FIELD_RE = re.compile(r'["\'](?:href|url|link|path|slug|canonicalUrl|pageUrl)["\']\s*:\s*["\']([^"\']+)["\']', re.I)
RAW_PATH_RE = re.compile(r'/(?:whats-on|events|exhibitions|programmes|activities|happenings|courses)/[^"\'<>\s\\]+', re.I)
ABS_URL_RE = re.compile(r'https?://[^"\'<>\s\\]+', re.I)
DATE_RE = re.compile(
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(?:-|to|–|—|until|till)?\s*\d{0,2}\s*(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)?[a-z]*\s*\d{0,4}\b|"
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+\d{1,2},?\s*\d{0,4}\b",
    re.I,
)
EVENT_ROUTE_RE = re.compile(r"/(?:whats-on|events)/(?:exhibitions|programmes|events|activities|happenings|courses)/", re.I)


@dataclass(frozen=True)
class Candidate:
    url: str
    source: str
    label: str
    score: int


def decode_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\\/", "/")
    value = value.replace("\\u002F", "/").replace("\\u002f", "/")
    return value


def clean(value: str) -> str:
    value = decode_text(value)
    value = TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(3_000_000)
        m = re.search(r"charset=([\w.-]+)", resp.headers.get("Content-Type", ""), re.I)
        return raw.decode(m.group(1) if m else "utf-8", "replace")


def normalize_url(raw: str, base_url: str) -> str:
    raw = decode_text(raw).strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    raw = urljoin(base_url, raw)
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", urllib.parse.urlencode(query), p.fragment))


def same_site(url: str, base_url: str) -> bool:
    u = urlparse(url).netloc.lower().replace("www.", "")
    b = urlparse(base_url).netloc.lower().replace("www.", "")
    return u == b or u.endswith("." + b) or b.endswith("." + u)


def page_title(page: str) -> str:
    for pattern in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r"<h1[^>]*>([\s\S]*?)</h1>",
        r"<title[^>]*>([\s\S]*?)</title>",
    ):
        m = re.search(pattern, page, re.I | re.S)
        if m:
            title = clean(m.group(1))
            if title:
                return title
    return ""


def extract_json_objects(page: str) -> list[object]:
    objects: list[object] = []
    for m in re.finditer(r'<script[^>]+type=["\']application/(?:ld\+)?json["\'][^>]*>([\s\S]*?)</script>', page, re.I):
        raw = decode_text(m.group(1)).strip()
        try:
            objects.append(json.loads(raw))
        except Exception:
            pass
    # Next.js-style payloads often use id="__NEXT_DATA__" with application/json;
    # the regex above already catches most, but leave generic URL extraction below as fallback.
    return objects


def walk_json(value: object):
    stack = [value]
    while stack:
        item = stack.pop()
        yield item
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def score_url(url: str, label: str, context: str, base_url: str) -> int:
    if not same_site(url, base_url):
        return -999
    p = urlparse(url)
    route = p.path.lower()
    text = clean(label + " " + context[:1200]).lower()
    score = 0
    if EVENT_ROUTE_RE.search(route):
        score += 80
    if any(part in route for part in ("/exhibitions/", "/programmes/", "/activities/", "/events/")):
        score += 40
    if DATE_RE.search(text):
        score += 20
    if re.search(r"\b(exhibition|programme|workshop|tour|talk|event|activity|festival|performance)\b", text, re.I):
        score += 20
    if route.rstrip("/") in {"/whats-on", "/whats-on/view-all", "/events"}:
        score -= 40
    return score


def discover_candidates(page: str, base_url: str) -> list[Candidate]:
    found: dict[str, Candidate] = {}

    def add(raw_url: str, source: str, label: str, context: str) -> None:
        url = normalize_url(raw_url, base_url)
        if not url or not same_site(url, base_url):
            return
        score = score_url(url, label, context, base_url)
        if score < 40:
            return
        key = url.lower().rstrip("/")
        candidate = Candidate(url=url, source=source, label=clean(label)[:120], score=score)
        if key not in found or candidate.score > found[key].score:
            found[key] = candidate

    for m in A_RE.finditer(page):
        context = page[max(0, m.start() - 900): min(len(page), m.end() + 1200)]
        add(m.group(1), "html-anchor", m.group(2), context)

    for m in JSON_URL_FIELD_RE.finditer(page):
        add(m.group(1), "json-field", m.group(1), page[max(0, m.start() - 600): min(len(page), m.end() + 900)])

    for m in RAW_PATH_RE.finditer(decode_text(page)):
        add(m.group(0), "raw-path", m.group(0), page[max(0, m.start() - 600): min(len(page), m.end() + 900)])

    for m in ABS_URL_RE.finditer(decode_text(page)):
        add(m.group(0), "raw-absolute", m.group(0), page[max(0, m.start() - 600): min(len(page), m.end() + 900)])

    for obj in extract_json_objects(page):
        for node in walk_json(obj):
            if isinstance(node, str) and (node.startswith("/") or node.startswith("http")):
                add(node, "json-walk-string", node, "")
            elif isinstance(node, dict):
                label = clean(node.get("title") or node.get("name") or node.get("headline") or "")
                for key in ("href", "url", "link", "path", "slug", "canonicalUrl", "pageUrl"):
                    if key in node:
                        add(str(node.get(key) or ""), f"json-walk-{key}", label or str(node.get(key)), json.dumps(node, ensure_ascii=False)[:1200])

    return sorted(found.values(), key=lambda x: -x.score)


def extract_detail_event(page: str, detail_url: str) -> dict:
    title = page_title(page)
    dates = []
    for m in DATE_RE.finditer(clean(page[:200000])):
        label = clean(m.group(0))
        if label not in dates:
            dates.append(label)
        if len(dates) >= 8:
            break
    json_event_titles = []
    for obj in extract_json_objects(page):
        for node in walk_json(obj):
            if isinstance(node, dict):
                typ = node.get("@type") or node.get("type")
                types = typ if isinstance(typ, list) else [typ]
                if any(str(t).lower() == "event" for t in types):
                    name = clean(node.get("name") or node.get("headline") or "")
                    if name:
                        json_event_titles.append(name)
    return {
        "url": detail_url,
        "title": json_event_titles[0] if json_event_titles else title,
        "dates": dates,
        "json_ld_event_titles": json_event_titles[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-url", default="https://www.acm.nhb.gov.sg/whats-on/view-all")
    ap.add_argument("--expect-url", default="")
    ap.add_argument("--limit", type=int, default=80)
    args = ap.parse_args()

    page = fetch(args.list_url)
    print(f"list_url={args.list_url}")
    print(f"list_html_bytes={len(page.encode('utf-8'))}")

    candidates = discover_candidates(page, args.list_url)
    print(f"candidates={len(candidates)}")
    for c in candidates[: args.limit]:
        print(f"{c.score:3d} {c.source:18s} {c.url}  label={c.label}")

    if args.expect_url:
        expected = normalize_url(args.expect_url, args.list_url).lower().rstrip("/")
        matched = [c for c in candidates if c.url.lower().rstrip("/") == expected]
        print(f"target_found={bool(matched)}")
        if matched:
            detail_page = fetch(matched[0].url)
            print(json.dumps(extract_detail_event(detail_page, matched[0].url), ensure_ascii=False, indent=2))
            return 0
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
