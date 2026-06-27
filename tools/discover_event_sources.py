#!/usr/bin/env python3
"""Discover official event source URLs from institution names.

This is the first stage of the local-event crawler:

  institution name
    -> discover likely official website
    -> discover likely event / what's-on listing pages
    -> write machine-readable source candidates

The script intentionally does NOT hardcode institution URLs or event detail URLs.
It accepts names from CLI or a text file and uses generic discovery signals:
web-search results, homepage content, robots/sitemap URLs, and same-site links.

Examples:
  python3 tools/discover_event_sources.py --name "Asian Civilisations Museum"

  cat institutions.txt | python3 tools/discover_event_sources.py --stdin \
    --out discovered_event_sources.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Iterable

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
MAX_FETCH_BYTES = 2_500_000

TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.I)
META_RE = re.compile(r"<meta[^>]+(?:name|property)=[\"']([^\"']+)[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I)
HREF_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", re.I)
LOC_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.I)
SITEMAP_RE = re.compile(r"^\s*Sitemap:\s*(\S+)\s*$", re.I | re.M)
DDG_RESULT_RE = re.compile(r"<a[^>]+class=[\"'][^\"']*result__a[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"']", re.I)
GENERIC_URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.I)

EVENT_ROUTE_WORDS = (
    "what", "whats", "whatson", "whats-on", "what-s-on", "events", "event",
    "exhibitions", "exhibition", "programmes", "programs", "programme", "program",
    "activities", "activity", "happenings", "courses", "workshops", "workshop",
    "calendar", "view-all",
)
EVENT_LABEL_WORDS = (
    "what's on", "whats on", "view all", "events", "exhibitions", "programmes",
    "programs", "activities", "happenings", "calendar", "workshops", "courses",
)
COMMON_NAME_WORDS = {"the", "and", "of", "for", "in", "at", "a", "an", "sg", "singapore", "museum", "gallery", "centre", "center", "library"}


@dataclass
class ListingCandidate:
    url: str
    score: int
    source: str
    label: str
    evidence: list[str]


@dataclass
class SiteCandidate:
    root_url: str
    score: int
    search_url: str
    title: str
    evidence: list[str]
    listing_candidates: list[ListingCandidate]


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_FETCH_BYTES)
        m = re.search(r"charset=([\w.-]+)", resp.headers.get("Content-Type", ""), re.I)
        return raw.decode(m.group(1) if m else "utf-8", "replace")


def normalize_url(raw: str, base: str = "") -> str:
    value = html.unescape(str(raw or "")).strip()
    value = value.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    if base:
        value = urllib.parse.urljoin(base, value)
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", urllib.parse.urlencode(query), ""))


def root_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return ""
    return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc, "/", "", "", ""))


def host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def same_site(url: str, root: str) -> bool:
    a = host(url)
    b = host(root)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def title_of(page: str) -> str:
    m = TITLE_RE.search(page)
    return clean(m.group(1)) if m else ""


def metas(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in META_RE.findall(page):
        out[clean(k).lower()] = clean(v)
    return out


def name_tokens(name: str) -> list[str]:
    words = [w.lower() for w in re.findall(r"[a-z0-9]+", name)]
    significant = [w for w in words if len(w) >= 3 and w not in COMMON_NAME_WORDS]
    return significant or [w for w in words if len(w) >= 3]


def name_acronym(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if w.lower() not in {"the", "and", "of", "for", "in", "at", "a", "an"}]
    return "".join(w[0] for w in words).lower()


def name_match_score(name: str, text: str, url: str) -> tuple[int, list[str]]:
    tokens = name_tokens(name)
    acronym = name_acronym(name)
    blob = clean(text).lower()
    h = host(url)
    score = 0
    evidence: list[str] = []
    full = re.sub(r"\s+", " ", name.lower()).strip()
    if full and full in blob:
        score += 45
        evidence.append("full-name-in-page")
    token_hits = [t for t in tokens if t in blob]
    if token_hits:
        score += min(30, 10 * len(token_hits))
        evidence.append("name-tokens-in-page:" + ",".join(token_hits[:5]))
    host_hits = [t for t in tokens if t in h]
    if host_hits:
        score += min(35, 14 * len(host_hits))
        evidence.append("name-tokens-in-host:" + ",".join(host_hits[:5]))
    if acronym and len(acronym) >= 2 and re.search(rf"(^|[.-]){re.escape(acronym)}([.-]|$)", h):
        score += 35
        evidence.append("acronym-in-host:" + acronym)
    if "official" in blob[:5000]:
        score += 5
        evidence.append("official-word-near-top")
    return score, evidence


def search_duckduckgo(query: str, limit: int = 10) -> list[str]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    page = fetch(url, timeout=15)
    urls: list[str] = []

    def add(raw: str) -> None:
        raw = html.unescape(raw)
        parsed = urllib.parse.urlparse(raw)
        if "uddg" in urllib.parse.parse_qs(parsed.query):
            raw = urllib.parse.parse_qs(parsed.query)["uddg"][0]
        normalized = normalize_url(raw)
        if normalized and normalized not in urls:
            urls.append(normalized)

    for raw in DDG_RESULT_RE.findall(page):
        add(raw)
    for raw in re.findall(r"uddg=([^&\"']+)", page):
        add(urllib.parse.unquote(raw))
    return urls[:limit]


def seed_search_urls(name: str) -> list[str]:
    queries = [
        f'"{name}" official website',
        f'"{name}" "what\'s on"',
        f'"{name}" events exhibitions programmes',
    ]
    urls: list[str] = []
    for q in queries:
        try:
            for url in search_duckduckgo(q):
                if url not in urls:
                    urls.append(url)
        except Exception as exc:
            print(f"WARN search failed query={q!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(0.3)
    return urls


def link_score(url: str, label: str) -> tuple[int, list[str]]:
    parsed = urllib.parse.urlparse(url)
    route = (parsed.path + " " + parsed.query).lower().replace("_", "-")
    label_l = clean(label).lower()
    score = 0
    evidence: list[str] = []
    for word in EVENT_ROUTE_WORDS:
        if word in route:
            score += 12
            evidence.append("route:" + word)
    for word in EVENT_LABEL_WORDS:
        if word in label_l:
            score += 18
            evidence.append("label:" + word)
    if "view-all" in route or "view all" in label_l:
        score += 18
        evidence.append("view-all")
    if re.search(r"/(what(?:s-on|son)|events?|exhibitions?|programmes?|programs?|activities?|happenings?)(/|$)", route):
        score += 25
        evidence.append("event-route-shape")
    return score, evidence


def page_links(page: str, base: str) -> Iterable[tuple[str, str, str]]:
    for href, label in HREF_RE.findall(page):
        yield normalize_url(href, base), clean(label), "html-link"
    for raw in GENERIC_URL_RE.findall(page):
        yield normalize_url(raw, base), raw, "raw-url"


def sitemap_urls(root: str) -> list[str]:
    urls: list[str] = []
    robots = urllib.parse.urljoin(root, "/robots.txt")
    try:
        robots_text = fetch(robots, timeout=8)
        urls.extend(normalize_url(x, root) for x in SITEMAP_RE.findall(robots_text))
    except Exception:
        pass
    urls.extend([urllib.parse.urljoin(root, "/sitemap.xml"), urllib.parse.urljoin(root, "/sitemap_index.xml")])
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:8]


def discover_listing_candidates(root: str, homepage: str) -> list[ListingCandidate]:
    found: dict[str, ListingCandidate] = {}

    def add(url: str, label: str, source: str) -> None:
        url = normalize_url(url, root)
        if not url or not same_site(url, root):
            return
        score, evidence = link_score(url, label)
        if score < 25:
            return
        key = url.lower().rstrip("/")
        item = ListingCandidate(url=url, score=score, source=source, label=clean(label)[:140], evidence=evidence[:8])
        if key not in found or item.score > found[key].score:
            found[key] = item

    for url, label, src in page_links(homepage, root):
        add(url, label, src)

    for sm in sitemap_urls(root):
        try:
            xml = fetch(sm, timeout=12)
        except Exception:
            continue
        for loc in LOC_RE.findall(xml):
            add(loc, loc, "sitemap")

    return sorted(found.values(), key=lambda x: -x.score)[:20]


def evaluate_site(name: str, search_url: str) -> SiteCandidate | None:
    candidate_root = root_url(search_url)
    if not candidate_root:
        return None
    try:
        homepage = fetch(candidate_root)
    except Exception:
        try:
            homepage = fetch(search_url)
            candidate_root = root_url(search_url)
        except Exception as exc:
            print(f"WARN fetch site failed {search_url}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return None

    title = title_of(homepage)
    meta = metas(homepage)
    header_text = " ".join([title, meta.get("description", ""), meta.get("og:title", ""), meta.get("og:description", ""), clean(homepage[:10000])])
    score, evidence = name_match_score(name, header_text, candidate_root)
    listings = discover_listing_candidates(candidate_root, homepage)
    if listings:
        score += min(40, listings[0].score // 2)
        evidence.append("event-listing-candidates-found")
    if score < 35:
        return None
    return SiteCandidate(root_url=candidate_root, score=score, search_url=search_url, title=title, evidence=evidence, listing_candidates=listings)


def discover_one(name: str) -> dict:
    search_urls = seed_search_urls(name)
    roots_seen: set[str] = set()
    candidates: list[SiteCandidate] = []
    for url in search_urls:
        root = root_url(url)
        if not root or root in roots_seen:
            continue
        roots_seen.add(root)
        item = evaluate_site(name, url)
        if item:
            candidates.append(item)
    candidates.sort(key=lambda x: -x.score)
    best = candidates[0] if candidates else None
    return {
        "institution": name,
        "official_site": best.root_url if best else "",
        "event_listing_url": best.listing_candidates[0].url if best and best.listing_candidates else "",
        "score": best.score if best else 0,
        "evidence": best.evidence if best else [],
        "candidates": [asdict(c) for c in candidates[:8]],
        "search_urls": search_urls[:20],
    }


def read_names(args: argparse.Namespace) -> list[str]:
    names: list[str] = []
    for item in args.name or []:
        names.append(item.strip())
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            names.extend(line.strip() for line in f if line.strip() and not line.strip().startswith("#"))
    if args.stdin:
        names.extend(line.strip() for line in sys.stdin if line.strip() and not line.strip().startswith("#"))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", action="append", help="Institution name. Can be repeated.")
    parser.add_argument("--input", help="Text file with one institution name per line.")
    parser.add_argument("--stdin", action="store_true", help="Read institution names from stdin.")
    parser.add_argument("--out", default="discovered_event_sources.json")
    args = parser.parse_args()

    names = read_names(args)
    if not names:
        parser.error("provide --name, --input, or --stdin")

    results = []
    for name in names:
        print(f"discovering: {name}", file=sys.stderr)
        results.append(discover_one(name))

    payload = {"ok": True, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(results), "results": results}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
