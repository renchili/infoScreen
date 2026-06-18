#!/usr/bin/env python3
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LOCATION = " ".join(sys.argv[1:]).strip() or "Punggol Singapore"
OUT = Path("local_event_search_results.json")

SOURCE_REGISTRY = [
    {
        "name": "Children's Museum Singapore",
        "kind": "direct",
        "url": "https://www.heritage.sg/childrensmuseum/whatson/childrens-season---listing-page",
        "audience": "children and families",
        "where": "Children's Museum Singapore / participating venues",
    },
    {
        "name": "Children's Museum Singapore",
        "kind": "site_query",
        "site": "heritage.sg/childrensmuseum",
        "queries": [
            '"Children\'s Museum Singapore" "2026" "programme"',
            '"Children\'s Season 2026" "Singapore"',
            '"Children\'s Season 2026" "museum"',
        ],
        "audience": "children and families",
    },
    {
        "name": "National Gallery Singapore",
        "kind": "site_query",
        "site": "nationalgallery.sg",
        "queries": [
            '"National Gallery Singapore" "family" "programme"',
            '"National Gallery Singapore" "children" "workshop"',
            '"National Gallery Singapore" "kids" "2026"',
        ],
        "audience": "children and families",
    },
    {
        "name": "National Museum Singapore",
        "kind": "site_query",
        "site": "nhb.gov.sg/nationalmuseum",
        "queries": [
            '"National Museum Singapore" "children" "programme"',
            '"National Museum Singapore" "family" "2026"',
        ],
        "audience": "children and families",
    },
    {
        "name": "Asian Civilisations Museum",
        "kind": "site_query",
        "site": "nhb.gov.sg/acm",
        "queries": [
            '"Asian Civilisations Museum" "family" "programme"',
            '"Asian Civilisations Museum" "children" "2026"',
        ],
        "audience": "children and families",
    },
    {
        "name": "Peranakan Museum",
        "kind": "site_query",
        "site": "nhb.gov.sg/peranakanmuseum",
        "queries": [
            '"Peranakan Museum" "family" "programme"',
            '"Peranakan Museum" "children" "2026"',
        ],
        "audience": "children and families",
    },
    {
        "name": "ArtScience Museum",
        "kind": "site_query",
        "site": "marinabaysands.com/museum",
        "queries": [
            '"ArtScience Museum" "family" "workshop"',
            '"ArtScience Museum" "children" "2026"',
        ],
        "audience": "children and families",
    },
    {
        "name": "Science Centre Singapore",
        "kind": "site_query",
        "site": "science.edu.sg",
        "queries": [
            '"Science Centre Singapore" "children" "workshop"',
            '"KidsSTOP" "2026" "programme"',
        ],
        "audience": "children and families",
    },
    {
        "name": "NLB Punggol Regional Library",
        "kind": "site_query",
        "site": "eventbrite.sg",
        "queries": [
            '"Punggol Regional Library" "NLB" "event"',
            '"Punggol Regional Library" "programme"',
            '"NLB" "Punggol" "children"',
        ],
        "audience": "library visitors",
        "where": "Punggol Regional Library",
    },
    {
        "name": "One Punggol",
        "kind": "site_query",
        "site": "onepunggol.sg",
        "queries": [
            '"One Punggol" "event"',
            '"One Punggol" "programme"',
            '"One Punggol" "children"',
        ],
        "audience": "residents",
        "where": "One Punggol",
    },
    {
        "name": "onePA / People's Association",
        "kind": "site_query",
        "site": "onepa.gov.sg",
        "queries": [
            '"Punggol" "onePA" "event"',
            '"Punggol" "People\'s Association" "event"',
            '"Punggol CC" "event"',
            '"Punggol West" "event"',
        ],
        "audience": "residents",
    },
    {
        "name": "SAFRA Punggol",
        "kind": "site_query",
        "site": "safra.sg",
        "queries": [
            '"SAFRA Punggol" "event"',
            '"SAFRA Punggol" "workshop"',
            '"SAFRA Punggol" "children"',
        ],
        "audience": "families",
        "where": "SAFRA Punggol",
    },
    {
        "name": "Waterway Point",
        "kind": "site_query",
        "site": "waterwaypoint.com.sg",
        "queries": [
            '"Waterway Point" "event"',
            '"Waterway Point" "children"',
            '"Waterway Point" "workshop"',
        ],
        "audience": "shoppers and families",
        "where": "Waterway Point",
    },
]

BAD_HOST = re.compile(
    r"(duckduckgo|google|bing|facebook\.com|instagram\.com|youtube\.com|tiktok|"
    r"sgmytaxi|taxi|propertyguru|99\.co|edgeprop|tripadvisor|booking|agoda|"
    r"klook|kkday|travel|tourism|wanderlog|holidify|foodpanda|deliveroo)",
    re.I,
)

BAD_TITLE = re.compile(
    r"(things to do|popular things|places to visit|attractions|natural escape|"
    r"guide|tourist|travel|restaurant|food|condo|property|hotel|taxi|"
    r"airport transfer|near me|map|weather|media release|press release|"
    r"shavees|stands together)",
    re.I,
)

GENERIC_TITLE = re.compile(
    r"^\s*(events?|activities|calendar|programmes?|programs?|what.?s happening|"
    r"onepa\s*\|\s*events|local events?|community events?|things to do|"
    r"listing page|whatson|what.?s on)\s*$",
    re.I,
)

EVENT_HINT = re.compile(
    r"(event|programme|program|workshop|register|registration|ticket|booking|"
    r"class|festival|talk|tour|fair|market|screening|performance|concert|"
    r"children|kids|family|museum|gallery|library|community|activity|session|"
    r"open house|guided walk|sign up|signup|carnival|storytelling|craft|play)",
    re.I,
)

DATE_RE = re.compile(
    r"(\b\d{1,2}(?:,\s*\d{1,2})*(?:\s*(?:-|–|to)\s*\d{1,2})?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*[-–]\s*"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)",
    re.I,
)

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def strip_brand(s):
    s = clean(s)
    s = re.sub(
        r"\s*[-|]\s*(DuckDuckGo|Google|Facebook|Eventbrite|Peatix|Meetup|onePA|Allevents|People.?s Association|NLB|National Gallery Singapore).*$",
        "",
        s,
        flags=re.I,
    )
    return s.strip()

def get(url, timeout=22):
    return requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 infoscreen-local-events-source-registry/5.0",
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        },
        allow_redirects=True,
    )

def abs_url(base, href):
    return urllib.parse.urljoin(base, href or "")

def unwrap_ddg_url(href):
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            return urllib.parse.unquote(qs.get("uddg", [""])[0])
        except Exception:
            return ""
    return href

def is_bad_url_or_title(title, url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()

    if not url.startswith("http"):
        return True
    if url.lower().endswith(".pdf"):
        return True
    if "/y.js" in path:
        return True
    if BAD_HOST.search(host) or BAD_HOST.search(url) or BAD_TITLE.search(title):
        return True
    if GENERIC_TITLE.match(title):
        return True
    if re.search(r"(/search|/tag|/category|/categories|/directory|/things-to-do|/places|/attractions)", path):
        return True
    return False

def search_ddg(query, site=None):
    q = query
    if site:
        q = f'site:{site} {query}'
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    r = get(url)
    r.raise_for_status()
    return r.text

def parse_ddg(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for block in soup.select(".result, .web-result, .results_links, .result__body"):
        a = block.select_one("a.result__a, .result__title a, a[href*='uddg=']")
        if not a:
            continue

        raw_title = clean(a.get_text(" ", strip=True))
        title = strip_brand(raw_title)
        url = unwrap_ddg_url(a.get("href", ""))

        if is_bad_url_or_title(title, url):
            continue

        sn = block.select_one(".result__snippet, .snippet")
        snippet = clean(sn.get_text(" ", strip=True)) if sn else ""

        rows.append({
            "title": title,
            "url": url,
            "snippet": snippet[:320],
            "source": urllib.parse.urlparse(url).netloc.lower().replace("www.", ""),
        })

    return dedupe_rows(rows)

def parse_direct_listing(source):
    base = source["url"]
    r = get(base)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for bad in soup(["script", "style", "noscript", "svg"]):
        bad.decompose()

    rows = []
    for a in soup.find_all("a"):
        raw_title = clean(a.get_text(" ", strip=True))
        title = strip_brand(raw_title)
        url = abs_url(base, a.get("href", ""))

        if len(title) < 8:
            continue
        if is_bad_url_or_title(title, url):
            continue

        block = a
        for _ in range(4):
            if block.parent:
                block = block.parent

        text = clean(block.get_text(" ", strip=True))
        if not EVENT_HINT.search(text + " " + title):
            continue

        rows.append({
            "title": title,
            "url": url,
            "snippet": text[:360],
            "source": urllib.parse.urlparse(url).netloc.lower().replace("www.", ""),
            "source_name": source["name"],
            "source_where": source.get("where", ""),
            "source_audience": source.get("audience", ""),
        })

    return dedupe_rows(rows)

def dedupe_rows(rows):
    seen = set()
    out = []
    for r in rows:
        key = r["url"].split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def parse_date(blob):
    m = DATE_RE.search(blob or "")
    return m.group(0) if m else ""

def jsonld_event(soup, row, source):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw = script.string or script.get_text()
            data = json.loads(raw)
            stack = data if isinstance(data, list) else [data]
            while stack:
                obj = stack.pop(0)
                if isinstance(obj, list):
                    stack.extend(obj)
                    continue
                if not isinstance(obj, dict):
                    continue
                if "@graph" in obj and isinstance(obj["@graph"], list):
                    stack.extend(obj["@graph"])
                typ = obj.get("@type")
                typ_s = " ".join(typ) if isinstance(typ, list) else str(typ)
                if "event" not in typ_s.lower():
                    continue

                name = clean(obj.get("name"))
                if not name or BAD_TITLE.search(name) or GENERIC_TITLE.match(name):
                    continue

                start = clean(obj.get("startDate"))
                desc = clean(obj.get("description"))

                where = source.get("where") or row.get("source_where") or LOCATION
                loc = obj.get("location")
                if isinstance(loc, dict):
                    where = clean(loc.get("name") or loc.get("address") or where)

                return {
                    "title": name,
                    "poster_title": name,
                    "what": name,
                    "when": start or "CHECK DATE",
                    "where": where,
                    "who": source.get("audience") or row.get("source_audience") or "visitors",
                    "why": desc[:180] or row.get("snippet", "")[:180],
                    "how": row["source"],
                    "summary": desc[:220] or row.get("snippet", "")[:220],
                    "poster_summary": desc[:220] or row.get("snippet", "")[:220],
                    "source": row["source"],
                    "url": row["url"],
                    "source_name": source["name"],
                }
        except Exception:
            pass
    return None

def extract_detail(row, source):
    try:
        r = get(row["url"], timeout=18)
        if r.status_code >= 400:
            return None, "http_" + str(r.status_code)
    except Exception:
        return None, "fetch_failed"

    soup = BeautifulSoup(r.text[:900000], "html.parser")

    ev = jsonld_event(soup, row, source)
    if ev:
        return ev, "ok_jsonld"

    for bad in soup(["script", "style", "noscript", "svg"]):
        bad.decompose()

    page_title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    h1 = soup.find(["h1", "h2"])
    heading = clean(h1.get_text(" ", strip=True) if h1 else "")
    text = clean(soup.get_text(" ", strip=True))

    title = strip_brand(heading or row["title"] or page_title)
    blob = f"{title} {row.get('snippet','')} {text[:6500]}"

    if not title or GENERIC_TITLE.match(title):
        return None, "generic_title"
    if BAD_TITLE.search(title):
        return None, "bad_title"
    if not EVENT_HINT.search(blob):
        return None, "no_event_hint"

    # 直接机构源放宽地点限制；普通 site query 需要命中机构名/地点
    low = blob.lower()
    source_name = source["name"].lower()
    if source["kind"] != "direct":
        related = (
            "punggol" in low
            or "children" in low
            or "family" in low
            or "museum" in low
            or "gallery" in low
            or "library" in low
            or any(part in low for part in source_name.split() if len(part) >= 5)
        )
        if not related:
            return None, "not_source_related"

    when = parse_date(blob)

    strong = re.search(
        r"(register|registration|ticket|booking|workshop|class|festival|talk|tour|screening|concert|children|kids|family|programme|program|library|museum|gallery|carnival|storytelling|craft|play)",
        blob,
        re.I,
    )
    if not when and not strong:
        return None, "weak_no_date"

    summary = clean(row.get("snippet", ""))
    if not summary or BAD_TITLE.search(summary):
        for part in re.split(r"(?<=[.!?。])\s+", text):
            part = clean(part)
            if 35 <= len(part) <= 200 and not re.search(r"(cookie|privacy|terms|copyright|login|subscribe|javascript)", part, re.I):
                summary = part
                break

    where = source.get("where") or row.get("source_where") or LOCATION
    who = source.get("audience") or row.get("source_audience") or "visitors"

    return {
        "title": title,
        "poster_title": title,
        "what": title,
        "when": when or "CHECK DATE",
        "where": where,
        "who": who,
        "why": summary[:180],
        "how": row["source"],
        "summary": summary[:220],
        "poster_summary": summary[:220],
        "source": row["source"],
        "url": row["url"],
        "source_name": source["name"],
    }, "ok"

def build_candidates():
    all_rows = []
    debug = []

    for source in SOURCE_REGISTRY:
        if source["kind"] == "direct":
            try:
                rows = parse_direct_listing(source)
                debug.append({"source": source["name"], "kind": "direct", "candidates": len(rows)})
                for r in rows:
                    r["_source_cfg"] = source
                all_rows.extend(rows)
            except Exception as e:
                debug.append({"source": source["name"], "kind": "direct", "error": str(e)})

        elif source["kind"] == "site_query":
            for q in source["queries"]:
                try:
                    html = search_ddg(q, source.get("site"))
                    rows = parse_ddg(html)
                    debug.append({"source": source["name"], "kind": "site_query", "query": q, "candidates": len(rows)})
                    for r in rows:
                        r["_source_cfg"] = source
                    all_rows.extend(rows)
                except Exception as e:
                    debug.append({"source": source["name"], "kind": "site_query", "query": q, "error": str(e)})

    return dedupe_rows(all_rows), debug

def main():
    rows, debug = build_candidates()
    results = []
    rejected = []
    seen = set()

    for row in rows:
        source = row.pop("_source_cfg", None) or {"name": row.get("source", ""), "kind": "site_query"}
        key = row["url"].split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)

        ev, reason = extract_detail(row, source)
        if ev:
            results.append(ev)
        else:
            rejected.append({
                "reason": reason,
                "title": row.get("title"),
                "source": row.get("source"),
                "url": row.get("url"),
                "source_name": source.get("name"),
            })

        if len(results) >= 12:
            break

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "location": LOCATION,
        "extractor": "source-registry-institutions-detail-parser",
        "sources": [s["name"] for s in SOURCE_REGISTRY],
        "results": results,
        "candidates_checked": len(rows),
        "debug_candidates": debug[:80],
        "rejected_preview": rejected[:40],
        "error": None,
        "from_cache": False,
    }

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
