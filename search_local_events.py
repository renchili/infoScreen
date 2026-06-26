#!/usr/bin/env python3
"""
Strict local-event discovery for InfoScreen.

Source URLs must be verified official institution URLs. Do not invent branch
websites for Singapore outlets: many branches are represented inside the
institution's central event system.

The requested location, for example "Punggol Singapore", is a preference signal
for ranking and highlighting only. It must not be treated as a hard filter.

Runtime output:
    local_event_search_results.json
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
DEFAULT_LOCATION = "Punggol Singapore"
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "78"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "10"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "10"))
FOLLOW_LINKS = os.environ.get("LOCAL_EVENTS_FOLLOW_LINKS", "1") != "0"

SOURCE_REGISTRY = [
    {
        "name": "Children's Museum Singapore",
        "source": "Children's Museum Singapore",
        "venue": "Children's Museum Singapore",
        "domains": ["heritage.sg", "childrensmuseum.sg"],
        "seeds": [
            "https://www.heritage.sg/childrensmuseum/whatson/activities",
            "https://www.heritage.sg/childrensmuseum/whatson/childrens-season---listing-page",
            "https://www.heritage.sg/childrensmuseum/",
        ],
        "aliases": ["Children's Museum Singapore", "Children's Season", "CMSG"],
        "verified": "2026-06-26",
    },
    {
        "name": "National Gallery Singapore",
        "source": "National Gallery Singapore",
        "venue": "National Gallery Singapore",
        "domains": ["nationalgallery.sg"],
        "seeds": ["https://www.nationalgallery.sg/sg/en/whats-on.html"],
        "aliases": ["National Gallery Singapore", "National Gallery", "GalleryToddlers"],
        "verified": "2026-06-26",
    },
    {
        "name": "National Museum of Singapore",
        "source": "National Museum of Singapore",
        "venue": "National Museum of Singapore",
        "domains": ["nationalmuseum.nhb.gov.sg"],
        "seeds": [
            "https://www.nationalmuseum.nhb.gov.sg/whats-on/view-all",
            "https://www.nationalmuseum.nhb.gov.sg/",
        ],
        "aliases": ["National Museum of Singapore", "National Museum Singapore", "NMS"],
        "verified": "2026-06-26",
    },
    {
        "name": "Asian Civilisations Museum",
        "source": "Asian Civilisations Museum",
        "venue": "Asian Civilisations Museum",
        "domains": ["acm.nhb.gov.sg", "acm.org.sg"],
        "seeds": [
            "https://www.acm.nhb.gov.sg/whats-on/overview?category=Programmes&time=Today%2CUpcoming",
            "https://www.acm.nhb.gov.sg/",
        ],
        "aliases": ["Asian Civilisations Museum", "ACM Singapore", "ACM"],
        "verified": "2026-06-26",
    },
    {
        "name": "Peranakan Museum",
        "source": "Peranakan Museum",
        "venue": "Peranakan Museum",
        "domains": ["peranakanmuseum.nhb.gov.sg", "peranakanmuseum.org.sg"],
        "seeds": [
            "https://www.peranakanmuseum.nhb.gov.sg/whatson/programmes",
            "https://www.peranakanmuseum.nhb.gov.sg/",
        ],
        "aliases": ["Peranakan Museum", "The Peranakan Museum"],
        "verified": "2026-06-26",
    },
    {
        "name": "ArtScience Museum",
        "source": "ArtScience Museum",
        "venue": "ArtScience Museum",
        "domains": ["marinabaysands.com"],
        "seeds": [
            "https://www.marinabaysands.com/museum/whats-on.html?tab=event",
            "https://www.marinabaysands.com/museum/whats-on.html",
        ],
        "aliases": ["ArtScience Museum", "ArtScience"],
        "verified": "2026-06-26",
    },
    {
        "name": "Science Centre Singapore",
        "source": "Science Centre Singapore",
        "venue": "Science Centre Singapore",
        "domains": ["science.edu.sg"],
        "seeds": ["https://www.science.edu.sg/whats-on"],
        "aliases": ["Science Centre Singapore", "KidsSTOP", "Science Centre"],
        "verified": "2026-06-26",
    },
    {
        "name": "National Library Board",
        "source": "National Library Board",
        "venue": "NLB Libraries",
        "domains": ["nlb.gov.sg", "nlb.libcal.com"],
        "seeds": [
            "https://www.nlb.gov.sg/main/whats-on",
            "https://nlb.libcal.com/calendar?cid=11498",
        ],
        "aliases": ["National Library Board", "NLB", "public libraries", "library"],
        "preferred_terms": ["Punggol Regional Library", "Punggol Library", "NLB Punggol", "Punggol"],
        "verified": "2026-06-26",
    },
    {
        "name": "onePA / People's Association",
        "source": "onePA",
        "venue": "People's Association CCs",
        "domains": ["onepa.gov.sg"],
        "seeds": ["https://www.onepa.gov.sg/events"],
        "aliases": ["onePA", "People's Association", "community club", "community centre"],
        "preferred_terms": ["Punggol", "Punggol CC", "Punggol 21 CC", "Punggol West CC", "Punggol Coast", "One Punggol"],
        "verified": "2026-06-26",
    },
    {
        "name": "SAFRA",
        "source": "SAFRA",
        "venue": "SAFRA Clubs",
        "domains": ["safra.sg"],
        "seeds": ["https://www.safra.sg/whats-on"],
        "aliases": ["SAFRA", "SAFRA events", "with my family"],
        "preferred_terms": ["SAFRA Punggol", "Punggol"],
        "verified": "2026-06-26",
    },
    {
        "name": "One Punggol",
        "source": "One Punggol",
        "venue": "One Punggol",
        "domains": ["onepunggol.sg"],
        "seeds": [
            "https://www.onepunggol.sg/events",
            "https://www.onepunggol.sg/happenings",
            "https://www.onepunggol.sg/",
        ],
        "aliases": ["One Punggol", "Punggol Town Hub"],
        "preferred_terms": ["Punggol", "One Punggol"],
        "verified": "2026-06-26",
    },
    {
        "name": "Waterway Point",
        "source": "Waterway Point",
        "venue": "Waterway Point",
        "domains": ["waterwaypoint.com.sg", "frasersproperty.com"],
        "seeds": [
            "https://www.waterwaypoint.com.sg/happenings",
            "https://www.waterwaypoint.com.sg/promotions",
            "https://www.waterwaypoint.com.sg/",
        ],
        "aliases": ["Waterway Point", "Frasers Property"],
        "preferred_terms": ["Punggol", "Waterway Point"],
        "verified": "2026-06-26",
    },
    {
        "name": "Mandai Wildlife Reserve",
        "source": "Mandai Wildlife Reserve",
        "venue": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "seeds": [
            "https://www.mandai.com/en/discover-mandai/events.html",
            "https://www.mandai.com/en/see-and-do.html",
            "https://www.mandai.com/en/singapore-zoo.html",
            "https://www.mandai.com/en/bird-paradise.html",
            "https://www.mandai.com/en/river-wonders.html",
            "https://www.mandai.com/en/night-safari.html",
        ],
        "aliases": ["Mandai", "Singapore Zoo", "Bird Paradise", "River Wonders", "Night Safari"],
        "verified": "2026-06-26",
    },
    {
        "name": "Sentosa",
        "source": "Sentosa",
        "venue": "Sentosa",
        "domains": ["sentosa.com.sg"],
        "seeds": ["https://www.sentosa.com.sg/en/things-to-do/events/"],
        "aliases": ["Sentosa", "Sentosa events", "Sentosa kids"],
        "verified": "2026-06-26",
        "js_heavy": True,
    },
    {
        "name": "Resorts World Sentosa",
        "source": "Resorts World Sentosa",
        "venue": "Resorts World Sentosa",
        "domains": ["rwsentosa.com"],
        "seeds": ["https://www.rwsentosa.com/en/events"],
        "aliases": ["Resorts World Sentosa", "RWS", "Universal Studios Singapore", "SEA Aquarium"],
        "verified": "2026-06-26",
        "js_heavy": True,
    },
]

EVENT_WORDS = (
    "event", "events", "programme", "program", "programmes", "programs", "workshop",
    "activity", "activities", "course", "class", "session", "talk", "tour", "story",
    "storytelling", "storytime", "family", "children", "kids", "festival", "performance",
    "carnival", "reading", "exhibition", "show", "camp", "walk", "trail", "experience",
    "experiences", "drop-in", "drop in", "screening", "guided tours",
)
EVENT_PATH_HINTS = (
    "/event", "/events", "/programme", "/programmes", "/program", "/programs",
    "/course", "/courses", "/workshop", "/activities", "/activity", "/whats-on",
    "/whatson", "/happenings", "/happening", "/things-to-do", "/experiences",
    "/experience", "/family", "/kids", "/children", "/calendar", "/discover-mandai/events",
)
BAD_WORDS = (
    "privacy policy", "terms of use", "cookie", "facebook", "instagram", "youtube",
    "linkedin", "career", "job", "property", "condo", "rental", "parking",
    "directions", "opening hours", "contact us", "about us", "venue hire", "press release",
    "annual report", "media release",
)
BAD_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf",
    ".zip", ".mp4", ".mp3", ".css", ".js", ".woff", ".woff2",
)
GENERIC_TITLES = {
    "events", "event", "what's on", "whats on", "things to do", "programmes",
    "programs", "activities", "activities and events", "exhibitions & programmes",
    "exhibitions and programmes", "what's on at acm", "home", "homepage",
    "visit us", "contact us", "about us", "calendar", "happenings",
    "children's season 2026", "childrens season 2026",
}
LISTING_PATH_MARKERS = (
    "/whatson/activities",
    "/whatson/childrens-season---listing-page",
    "/whats-on/view-all",
    "/whats-on/overview",
    "/whatson/programmes",
    "/main/whats-on",
    "/museum/whats-on.html",
)
TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
DATE_RE = re.compile(
    r"("
    r"\b\d{1,2}\s*(?:-|to|–|—)\s*\d{1,2}\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    r"\s*(?:-|to|–|—)?\s*\d{0,2}\s*"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?[a-z]*\s+\d{4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
    r"\b(?:mon|tue|wed|thu|fri|sat|sun),?\s+\d{1,2}\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\btoday\b|\btomorrow\b|\btonight\b|\bthis weekend\b|\bdaily\b|\bpermanent\b|various timings daily"
    r")",
    re.I,
)
JSON_LD_EVENT_RE = re.compile(r'"@type"\s*:\s*(?:"Event"|\[[^\]]*"Event"[^\]]*\])', re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def textify(value: str) -> str:
    value = html.unescape(value or "")
    value = TEMPLATE_RE.sub(" ", value)
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def has_template_placeholder(value: str) -> bool:
    return bool(TEMPLATE_RE.search(value or ""))


def shorten(value: str, limit: int) -> str:
    value = textify(value)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def same_source_domain(url: str, source: dict) -> bool:
    h = host(url)
    return bool(h) and any(
        h == d.replace("www.", "") or h.endswith("." + d.replace("www.", ""))
        for d in source["domains"]
    )


def normalize_url(url: str, base: str | None = None) -> str:
    if not url:
        return ""
    url = html.unescape(url.strip())
    if base:
        url = urljoin(base, url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "cmpid")
    ]
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", urllib.parse.urlencode(query), "")
    )


def url_key(url: str) -> str:
    p = urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", p.query, "")).lower()


def bad_url(url: str) -> bool:
    p = urlparse(url).path.lower()
    if any(p.endswith(ext) for ext in BAD_EXT):
        return True
    return any(
        x in p
        for x in ("/privacy", "/terms", "/contact", "/about", "/career", "/login", "/cart", "/checkout")
    )


def fetch(url: str, timeout: int = 8) -> str:
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
        raw = response.read(1_800_000)
        ctype = response.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w.-]+)", ctype, re.I)
        enc = m.group(1) if m else "utf-8"
        return raw.decode(enc, "replace")


def meta_content(page: str, names: list[str]) -> str:
    for name in names:
        e = re.escape(name)
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\']{e}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{e}["\']',
        ]
        for pat in patterns:
            m = re.search(pat, page, re.I | re.S)
            if m:
                v = textify(m.group(1))
                if v:
                    return v
    return ""


def strip_title_suffix(title: str) -> str:
    title = textify(title)
    title = re.sub(
        r"\s*[\|–-]\s*(NLB|National Library Board|onePA|SAFRA|Mandai|Sentosa|"
        r"Resorts World Sentosa|Singapore|National Heritage Board|National Gallery Singapore|"
        r"Science Centre Corporate Website)\s*$",
        "",
        title,
        flags=re.I,
    )
    return textify(title)


def extract_title(page: str, fallback: str = "") -> str:
    vals = [meta_content(page, ["og:title", "twitter:title"])]
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.I | re.S)
    if h1:
        vals.append(textify(h1.group(1)))
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    if title:
        vals.append(textify(title.group(1)))
    vals.append(fallback)
    for v in vals:
        t = strip_title_suffix(v)
        if t:
            return t
    return ""


def extract_summary(page: str, fallback: str = "") -> str:
    vals = [meta_content(page, ["og:description", "description", "twitter:description"]), fallback]
    plain = textify(page)
    for word in EVENT_WORDS:
        m = re.search(r"([^.。!?]*\b" + re.escape(word) + r"\b[^.。!?]*[.。!?]?)", plain, re.I)
        if m:
            vals.append(m.group(1))
            break
    for v in vals:
        if has_template_placeholder(v):
            continue
        v = shorten(v, 220)
        if v and v.lower() not in GENERIC_TITLES:
            return v
    return "Open the official page for details."


def extract_date(*vals: str) -> str:
    blob = " ".join(textify(v) for v in vals if v)
    m = DATE_RE.search(blob)
    return textify(m.group(1)) if m else "Check official page"


def event_path_score(url: str) -> int:
    p = urlparse(url).path.lower()
    return sum(12 for hint in EVENT_PATH_HINTS if hint in p)


def alias_score(source: dict, blob: str) -> int:
    score = 0
    for alias in source.get("aliases", []):
        alias_l = alias.lower()
        if alias_l and alias_l in blob:
            score += 10
            continue
        for part in re.split(r"\W+", alias_l):
            if len(part) >= 4 and part in blob:
                score += 2
    return score


def preferred_terms(source: dict, location: str) -> list[str]:
    terms = []
    for raw in [location, *source.get("preferred_terms", [])]:
        value = textify(raw).lower()
        if not value:
            continue
        terms.append(value)
        for part in re.split(r"\W+", value):
            if len(part) >= 4 and part not in terms:
                terms.append(part)
    return terms


def preferred_location_match(source: dict, location: str, blob: str) -> tuple[bool, list[str]]:
    hits = [term for term in preferred_terms(source, location) if term in blob]
    return bool(hits), hits[:8]


def has_event_schema(page: str) -> bool:
    return bool(JSON_LD_EVENT_RE.search(page[:500_000]))


def extract_links(page: str, base_url: str, source: dict) -> list[tuple[int, str, str]]:
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        url = normalize_url(m.group(1), base_url)
        anchor = textify(m.group(2))
        if not url or bad_url(url) or not same_source_domain(url, source):
            continue
        blob = f"{url} {anchor}".lower()
        score = event_path_score(url) + alias_score(source, blob)
        score += sum(4 for word in EVENT_WORDS if word in blob)
        if score >= 8:
            out.append((score, url, anchor))
    out.sort(key=lambda x: -x[0])
    return out


def is_listing_page_url(url: str) -> bool:
    p = urlparse(url).path.lower().rstrip("/")
    return any(p.endswith(marker.rstrip("/")) or marker in p for marker in LISTING_PATH_MARKERS)


def is_generic_event_title(source: dict, title: str, date: str, url: str) -> bool:
    t = textify(title).lower()
    if not t:
        return True
    if t in GENERIC_TITLES:
        return True
    for name in [source["name"], source["source"], source["venue"]]:
        if t == textify(name).lower() and date == "Check official page":
            return True
    p = urlparse(url).path.lower()
    return (p in ("", "/") or p.endswith("/contact") or p.endswith("/about")) and date == "Check official page"


def page_event_score(source: dict, url: str, title: str, summary: str, body: str, location: str):
    blob = f"{title} {summary} {url} {body[:6000]}".lower()
    date = extract_date(title, summary, body[:5000])
    has_date = date != "Check official page"
    schema_event = has_event_schema(body)
    event_word_hits = [w for w in EVENT_WORDS if w in blob]
    score = event_path_score(url) + min(len(event_word_hits), 10) * 4 + alias_score(source, blob)
    if has_date:
        score += 28
    if schema_event:
        score += 30
    priority_location, preferred_hits = preferred_location_match(source, location, blob)
    if priority_location:
        score += 18
    for bad in BAD_WORDS:
        if bad in blob:
            score -= 60
    generic_title = is_generic_event_title(source, title, date, url)
    listing_page = is_listing_page_url(url)
    if generic_title:
        score -= 90
    if listing_page and not schema_event:
        score -= 80
    if not has_date and not schema_event:
        score -= 35
    evidence = {
        "has_date": has_date,
        "schema_event": schema_event,
        "generic_title": generic_title,
        "listing_page": listing_page,
        "event_word_hits": event_word_hits[:8],
        "preferred_location_hits": preferred_hits,
    }
    return score, date, priority_location, evidence


def build_event(source: dict, url: str, page: str, location: str, origin: str):
    if has_template_placeholder(page[:20_000]):
        page = TEMPLATE_RE.sub(" ", page)
    title = extract_title(page)
    summary = extract_summary(page)
    body = textify(page)
    score, date, priority_location, evidence = page_event_score(source, url, title, summary, body, location)
    if score < 45:
        return None
    return {
        "type": "event",
        "title": shorten(title, 150),
        "poster_title": shorten(title, 150),
        "what": shorten(title, 150),
        "when": date,
        "date": date,
        "where": source["venue"],
        "venue": source["venue"],
        "who": source["source"],
        "why": shorten(summary, 180),
        "how": host(url),
        "summary": shorten(summary, 220),
        "poster_summary": shorten(summary, 220),
        "source": source["source"],
        "source_name": source["name"],
        "url": url,
        "score": score,
        "priority_location": priority_location,
        "seed_origin": origin,
        "evidence": evidence,
    }


def crawl_source(source: dict, location: str, deadline: float) -> dict:
    queue = []
    queued = set()
    fetched = set()
    events = []
    rejected = []

    def push(url: str, score: int, origin: str):
        url = normalize_url(url)
        if not url:
            return
        key = url_key(url)
        if key in queued or key in fetched:
            return
        if not same_source_domain(url, source) or bad_url(url):
            return
        queued.add(key)
        queue.append((score, url, origin))

    for seed in source.get("seeds", []):
        push(seed, 90 + event_path_score(seed), "verified_seed")

    pages = 0
    while queue and pages < MAX_PAGES_PER_SOURCE and len(events) < MAX_EVENTS_PER_SOURCE and time.monotonic() < deadline:
        queue.sort(key=lambda x: -x[0])
        _, url, origin = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)
        try:
            page = fetch(url)
        except Exception as e:
            rejected.append({"url": url, "origin": origin, "reason": f"fetch_failed: {type(e).__name__}"})
            continue
        pages += 1
        item = build_event(source, url, page, location, origin)
        if item:
            events.append(item)
        else:
            title = extract_title(page)
            summary = extract_summary(page)
            rejected.append({
                "url": url,
                "origin": origin,
                "reason": "below_event_threshold",
                "title": shorten(title, 120),
                "date": extract_date(title, summary, textify(page)[:4000]),
                "listing_page": is_listing_page_url(url),
                "generic_title": textify(title).lower() in GENERIC_TITLES,
            })
        if FOLLOW_LINKS:
            for score, link, _anchor in extract_links(page, url, source)[:24]:
                push(link, score, f"linked_from:{host(url)}")
        if len(queue) > 120:
            queue.sort(key=lambda x: -x[0])
            queue[:] = queue[:80]

    return {
        "events": events,
        "debug": {
            "source": source["name"],
            "verified": source.get("verified"),
            "js_heavy": bool(source.get("js_heavy")),
            "pages_fetched": pages,
            "queue_seen": len(queued),
            "accepted": len(events),
            "verified_seeds": source.get("seeds", []),
            "preferred_terms": source.get("preferred_terms", []),
            "rejected_preview": rejected[:8],
        },
        "source_card": {
            "type": "source",
            "title": source["name"],
            "url": source.get("seeds", [""])[0],
            "source": source["source"],
            "venue": source["venue"],
            "verified": source.get("verified"),
            "preferred_terms": source.get("preferred_terms", []),
        },
    }


def dedupe_events(events: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for item in events:
        key = re.sub(r"\W+", "", f'{item.get("source_name")} {item.get("title")} {item.get("venue")}'.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect(location: str):
    deadline = time.monotonic() + MAX_SECONDS
    events = []
    sources = []
    debug = []
    for source in SOURCE_REGISTRY:
        if time.monotonic() >= deadline:
            break
        result = crawl_source(source, location, deadline)
        events.extend(result["events"])
        sources.append(result["source_card"])
        debug.append(result["debug"])
    events = dedupe_events(events)
    events.sort(
        key=lambda x: (
            not bool(x.get("priority_location")),
            -int(x.get("score", 0)),
            x.get("when", ""),
            x.get("source_name", ""),
            x.get("title", "").lower(),
        )
    )
    return events[:80], sources, debug


def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events, sources, debug = collect(location)
    payload = {
        "version": 9,
        "ok": True,
        "extractor": "verified-source-preferred-location-crawler",
        "updated_at": now_iso(),
        "location": location,
        "count": len(events),
        "results": events,
        "items": events,
        "sources": sources,
        "debug_by_source": debug,
        "settings": {
            "follow_links": FOLLOW_LINKS,
            "max_pages_per_source": MAX_PAGES_PER_SOURCE,
            "max_events_per_source": MAX_EVENTS_PER_SOURCE,
            "verified_source_count": len(SOURCE_REGISTRY),
            "location_is_preference_only": True,
            "reject_generic_listing_pages": True,
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")


if __name__ == "__main__":
    main()
