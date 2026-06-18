#!/usr/bin/env python3
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

location = " ".join(sys.argv[1:]).strip() or "Punggol Singapore"
out = Path("local_event_search_results.json")

queries = [
    f'"{location}" "event" "date"',
    f'"{location}" "register" "event"',
    f'"{location}" "workshop" "event"',
    f'"{location}" "community club" "event"',
    f'site:onepa.gov.sg/events "{location}"',
    f'site:eventbrite.sg "{location}" event',
    f'site:peatix.com "{location}" event',
    f'site:allevents.in "{location}" event',
]

GENERIC_TITLE = re.compile(
    r'^\s*(onepa\s*\|\s*events|onepa events|events|what.?s happening|things to do|'
    r'community events?|local events?|punggol local events?|activities|calendar)\s*$',
    re.I,
)

BAD_URL = re.compile(
    r'(duckduckgo|google|facebook\.com/login|instagram\.com|maps\.google|'
    r'/search\b|/category\b|/categories\b|/directory\b|/places\b|/things-to-do\b|'
    r'/events/?$|/event/?$|/events/search|/events\?|/whats-on/?$)',
    re.I,
)

BAD_TITLE_PART = re.compile(
    r'(weather|property|condo|hotel|restaurant|food delivery|near me|map of)',
    re.I,
)

DATE_RE = re.compile(
    r'(\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|'
    r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|'
    r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|'
    r'\b(?:today|tomorrow|this weekend|weekend)\b)',
    re.I,
)

EVENT_HINT = re.compile(
    r'(register|ticket|workshop|class|festival|talk|tour|fair|market|screening|'
    r'performance|concert|community|club|activity|programme|program|session|'
    r'eventbrite|peatix|onepa|allevents)',
    re.I,
)

def clean_text(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()

def clean_title(s):
    s = clean_text(s)
    s = re.sub(r'\s*[-|]\s*(DuckDuckGo|Google|Facebook|onePA|Eventbrite|People.?s Association).*$','', s, flags=re.I)
    return s.strip()

def clean_url(href):
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = urllib.parse.unquote(qs.get("uddg", [""])[0])
        except Exception:
            pass
    return href

def ddg(query):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=25,
    )
    r.raise_for_status()
    return r.text

def parse_ddg(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    blocks = soup.select(".result, .web-result, .results_links, .result__body")
    if not blocks:
        blocks = soup.select("a.result__a, .result__title a, a[href*='uddg=']")

    for block in blocks:
        a = None
        if getattr(block, "name", "") == "a":
            a = block
        else:
            a = block.select_one("a.result__a, .result__title a, a[href*='uddg=']")
        if not a:
            continue

        title = clean_text(a.get_text(" ", strip=True))
        url = clean_url(a.get("href", ""))

        if not title or not url.startswith("http"):
            continue

        snippet = ""
        if getattr(block, "name", "") != "a":
            sn = block.select_one(".result__snippet, .result__extras__url, .snippet")
            if sn:
                snippet = clean_text(sn.get_text(" ", strip=True))
            else:
                snippet = clean_text(block.get_text(" ", strip=True)).replace(title, "", 1).strip()

        rows.append({
            "raw_title": title,
            "title": clean_title(title),
            "url": url,
            "snippet": snippet[:260],
            "source": urllib.parse.urlparse(url).netloc.replace("www.", ""),
        })

    seen = set()
    out_rows = []
    for r in rows:
        key = r["url"].split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out_rows.append(r)
    return out_rows

def infer_when(blob):
    m = DATE_RE.search(blob or "")
    return m.group(0) if m else ""

def is_real_event(row):
    title = clean_title(row.get("title"))
    url = row.get("url", "")
    blob = f"{title} {row.get('snippet','')} {url}"

    if not title or len(title) < 8:
        return False, "short_title"
    if GENERIC_TITLE.search(title):
        return False, "generic_title"
    if BAD_TITLE_PART.search(title):
        return False, "bad_title_part"
    if BAD_URL.search(url):
        return False, "bad_url"

    # 必须满足：有日期，或者标题/摘要/URL 明显像一个具体活动
    has_date = bool(DATE_RE.search(blob))
    has_hint = bool(EVENT_HINT.search(blob))

    # onePA/eventbrite/peatix/allevents 详情页可以接受，但不能是根 events 页
    host = urllib.parse.urlparse(url).netloc.lower()
    path = urllib.parse.urlparse(url).path.lower().strip("/")
    trusted_event_host = any(x in host for x in ["onepa.gov.sg", "eventbrite", "peatix", "allevents"])
    detailish_path = len(path.split("/")) >= 2 and not path.endswith("events")

    if has_date or (has_hint and trusted_event_host and detailish_path):
        return True, "ok"

    return False, "no_event_evidence"

def make_event(row):
    blob = f"{row.get('title','')} {row.get('snippet','')}"
    when = infer_when(blob) or "CHECK DATE"
    title = clean_title(row["title"])

    return {
        "title": title,
        "poster_title": title,
        "when": when,
        "where": location,
        "summary": row.get("snippet", ""),
        "poster_summary": row.get("snippet", ""),
        "source": row.get("source", ""),
        "url": row.get("url", ""),
    }

results = []
debug = []
rejected = []
seen = set()

for q in queries:
    try:
        html = ddg(q)
        rows = parse_ddg(html)
        accepted = 0

        for row in rows:
            url_key = row["url"].split("?")[0].rstrip("/")
            if url_key in seen:
                continue
            seen.add(url_key)

            ok, reason = is_real_event(row)
            if not ok:
                rejected.append({
                    "reason": reason,
                    "title": row.get("title"),
                    "url": row.get("url"),
                })
                continue

            results.append(make_event(row))
            accepted += 1

            if len(results) >= 8:
                break

        debug.append({
            "query": q,
            "candidates": len(rows),
            "accepted": accepted,
        })

    except Exception as e:
        debug.append({
            "query": q,
            "error": str(e),
        })

    if len(results) >= 8:
        break

data = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "location": location,
    "extractor": "ddg-html-event-only",
    "queries": queries,
    "results": results,
    "candidates_checked": sum(x.get("candidates", 0) for x in debug),
    "debug_candidates": debug,
    "rejected_preview": rejected[:25],
    "error": None,
    "from_cache": False,
}

out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(json.dumps(data, ensure_ascii=False, indent=2))
