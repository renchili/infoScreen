#!/usr/bin/env python3
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
)

DEFAULT_LOCATION = "Punggol Singapore"
YEAR = str(datetime.now().year)

OFFICIAL_SOURCES = [
    {
        "name": "Punggol Regional Library",
        "url": "https://www.nlb.gov.sg/main/visit-us/our-libraries-and-locations/punggol-regional-library",
        "query": 'site:nlb.gov.sg "Punggol Regional Library" programme event children',
    },
    {
        "name": "One Punggol",
        "url": "https://www.onepunggol.sg/",
        "query": 'site:onepunggol.sg Punggol event workshop family',
    },
    {
        "name": "onePA",
        "url": "https://www.onepa.gov.sg/",
        "query": 'site:onepa.gov.sg Punggol Sengkang event workshop family',
    },
    {
        "name": "SAFRA Punggol",
        "url": "https://www.safra.sg/",
        "query": 'site:safra.sg Punggol event family children',
    },
    {
        "name": "Children’s Season",
        "url": "https://www.nhb.gov.sg/",
        "query": f'"Children\'s Season" Singapore {YEAR} programme event',
    },
    {
        "name": "National Gallery Families",
        "url": "https://www.nationalgallery.sg/",
        "query": f'site:nationalgallery.sg family children programme Singapore {YEAR}',
    },
]

ALLOW_HOSTS = (
    "nlb.gov.sg",
    "onepunggol.sg",
    "onepa.gov.sg",
    "safra.sg",
    "nhb.gov.sg",
    "heritage.sg",
    "heritage.gov.sg",
    "nationalgallery.sg",
    "eventbrite.sg",
    "eventbrite.com",
    "esplanade.com",
    "artscience.com",
    "gardensbythebay.com.sg",
)

EVENT_WORDS = (
    "event", "programme", "program", "workshop", "activity",
    "festival", "season", "storytelling", "family", "children",
    "kids", "course", "class", "talk", "tour", "performance",
)

BAD_WORDS = (
    "top things to do",
    "popular things to do",
    "tripadvisor",
    "klook",
    "property",
    "condo",
    "rental",
    "career",
    "job",
    "privacy policy",
    "terms of use",
    "facebook",
    "instagram",
    "youtube",
    "pdf",
)

DATE_RE = re.compile(
    r"("
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\bthis weekend\b|\btoday\b|\btomorrow\b"
    r")",
    re.I,
)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def textify(value):
    value = html.unescape(value or "")
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def shorten(value, limit):
    value = textify(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"

def fetch(url, timeout=16):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")

def unwrap_ddg(url):
    url = html.unescape(url)
    if url.startswith("//"):
        url = "https:" + url

    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    if "uddg" in query:
        return query["uddg"][0]

    return url

def search_ddg(query, limit=8):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    page = fetch(url)
    out = []

    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )

    for match in pattern.finditer(page):
        link = unwrap_ddg(match.group(1))
        title = textify(match.group(2))

        if link.startswith("http") and title:
            out.append({
                "title": title,
                "url": link,
                "summary": "",
            })

        if len(out) >= limit:
            break

    return out

def search_bing(query, limit=8):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    page = fetch(url)
    out = []

    pattern = re.compile(
        r'<li[^>]+class="b_algo"[\s\S]*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>[\s\S]*?</li>',
        re.I,
    )

    for match in pattern.finditer(page):
        block = match.group(0)
        link = html.unescape(match.group(1))
        title = textify(match.group(2))

        desc_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.I | re.S)
        summary = textify(desc_match.group(1)) if desc_match else ""

        if link.startswith("http") and title:
            out.append({
                "title": title,
                "url": link,
                "summary": summary,
            })

        if len(out) >= limit:
            break

    return out

def source_from_url(url):
    host = urlparse(url).netloc.lower().replace("www.", "")

    names = {
        "nlb.gov.sg": "NLB",
        "onepunggol.sg": "One Punggol",
        "onepa.gov.sg": "onePA",
        "safra.sg": "SAFRA",
        "nhb.gov.sg": "National Heritage Board",
        "heritage.sg": "HeritageSG",
        "heritage.gov.sg": "HeritageSG",
        "nationalgallery.sg": "National Gallery",
        "eventbrite.sg": "Eventbrite",
        "eventbrite.com": "Eventbrite",
        "esplanade.com": "Esplanade",
        "artscience.com": "ArtScience Museum",
        "gardensbythebay.com.sg": "Gardens by the Bay",
    }

    for domain, name in names.items():
        if host.endswith(domain):
            return name

    return host or "Official source"

def allowed_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")

    if not host:
        return False

    if url.lower().endswith(".pdf"):
        return False

    return any(host.endswith(domain) for domain in ALLOW_HOSTS)

def item_score(title, summary, url, location):
    blob = f"{title} {summary} {url}".lower()
    score = 0

    for word in EVENT_WORDS:
        if word in blob:
            score += 4

    for word in ("punggol", "sengkang", "hougang"):
        if word in blob:
            score += 8

    if DATE_RE.search(blob):
        score += 10

    for word in BAD_WORDS:
        if word in blob:
            score -= 60

    location_words = [
        word for word in re.split(r"\W+", location.lower())
        if len(word) >= 4
    ]
    for word in location_words:
        if word in blob:
            score += 4

    return score

def event_date(title, summary):
    match = DATE_RE.search(f"{title} {summary}")
    return textify(match.group(1)) if match else "Check official page"

def collect(location):
    candidates = []
    seen = set()

    for source in OFFICIAL_SOURCES:
        query = f'{location} {source["query"]} {YEAR}'

        found = []
        try:
            found.extend(search_ddg(query))
        except Exception:
            pass

        try:
            found.extend(search_bing(query))
        except Exception:
            pass

        for row in found:
            url = row["url"]
            title = shorten(row["title"], 150)
            summary = shorten(row.get("summary", ""), 240)

            if not title or not allowed_url(url):
                continue

            score = item_score(title, summary, url, location)
            if score < 8:
                continue

            key = (url.split("#")[0].rstrip("/") or title).lower()
            if key in seen:
                continue
            seen.add(key)

            candidates.append({
                "type": "event",
                "title": title,
                "url": url,
                "source": source_from_url(url),
                "date": event_date(title, summary),
                "venue": location,
                "summary": summary or "Open the official page for programme details.",
                "score": score,
            })

        time.sleep(0.2)

    candidates.sort(
        key=lambda x: (-x["score"], x["title"].lower())
    )

    return candidates[:8]

def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events = collect(location)

    sources = [{
        "type": "source",
        "title": source["name"],
        "url": source["url"],
        "source": source["name"],
    } for source in OFFICIAL_SOURCES]

    payload = {
        "version": 2,
        "ok": True,
        "updated_at": now_iso(),
        "location": location,
        "count": len(events),
        "results": events,
        "items": events,
        "sources": sources,
    }

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2)
    )

    print(
        f"local events updated "
        f"count={len(events)} "
        f"sources={len(sources)} "
        f"location={location}"
    )

if __name__ == "__main__":
    main()
