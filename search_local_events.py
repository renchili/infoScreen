#!/usr/bin/env python3
"""
Strict local-event discovery for InfoScreen.

Design:
- Start from a small, explicit official-source registry.
- Discover candidate URLs with DuckDuckGo site: queries instead of inventing paths.
- Crawl only URLs that stay on the source's official domains.
- Reject generic home/category pages unless they have concrete event evidence.
- Keep rich debug data in local_event_search_results.json so bad sources can be fixed.

No runtime output is committed; local_event_search_results.json stays ignored.
"""

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

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/126 Safari/537.36"
)
DEFAULT_LOCATION = "Punggol Singapore"
YEAR = str(datetime.now().year)

MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "78"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "8"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "8"))
MAX_DDG_RESULTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_DDG_RESULTS_PER_SOURCE", "8"))
ENABLE_DDG_DISCOVERY = os.environ.get("LOCAL_EVENTS_ENABLE_DDG", "1") != "0"
ALLOW_COMMON_PATH_GUESSES = os.environ.get("LOCAL_EVENTS_ALLOW_COMMON_PATHS", "0") == "1"

SOURCE_REGISTRY = [
    {
        "name": "Children's Museum Singapore",
        "source": "Children's Museum Singapore",
        "domains": ["heritage.sg"],
        "venue": "Children's Museum Singapore",
        "seeds": ["https://www.heritage.sg/childrensmuseum/"],
        "aliases": [
            "Children's Museum Singapore",
            "Children's Season Singapore",
            "Children's Season",
        ],
    },
    {
        "name": "National Gallery Singapore",
        "source": "National Gallery Singapore",
        "domains": ["nationalgallery.sg"],
        "venue": "National Gallery Singapore",
        "seeds": ["https://www.nationalgallery.sg/"],
        "aliases": [
            "National Gallery Singapore",
            "National Gallery family",
            "National Gallery children",
        ],
    },
    {
        "name": "National Museum Singapore",
        "source": "National Museum Singapore",
        "domains": ["nhb.gov.sg"],
        "venue": "National Museum Singapore",
        "seeds": ["https://www.nhb.gov.sg/nationalmuseum/"],
        "aliases": [
            "National Museum Singapore",
            "National Museum of Singapore",
            "National Museum family",
            "National Museum children",
        ],
    },
    {
        "name": "Asian Civilisations Museum",
        "source": "Asian Civilisations Museum",
        "domains": ["nhb.gov.sg"],
        "venue": "Asian Civilisations Museum",
        "seeds": ["https://www.nhb.gov.sg/acm/"],
        "aliases": [
            "Asian Civilisations Museum",
            "ACM Singapore",
            "ACM family",
            "ACM children",
        ],
    },
    {
        "name": "Peranakan Museum",
        "source": "Peranakan Museum",
        "domains": ["nhb.gov.sg"],
        "venue": "Peranakan Museum",
        "seeds": ["https://www.nhb.gov.sg/peranakanmuseum/"],
        "aliases": [
            "Peranakan Museum",
            "Peranakan Museum family",
            "Peranakan Museum children",
        ],
    },
    {
        "name": "ArtScience Museum",
        "source": "ArtScience Museum",
        "domains": ["marinabaysands.com"],
        "venue": "ArtScience Museum",
        "seeds": ["https://www.marinabaysands.com/museum.html"],
        "aliases": [
            "ArtScience Museum",
            "ArtScience family",
            "ArtScience children",
        ],
    },
    {
        "name": "Science Centre Singapore",
        "source": "Science Centre Singapore",
        "domains": ["science.edu.sg"],
        "venue": "Science Centre Singapore",
        "seeds": ["https://www.science.edu.sg/"],
        "aliases": [
            "Science Centre Singapore",
            "KidsSTOP",
            "Science Centre kids",
        ],
    },
    {
        "name": "NLB Punggol Regional Library",
        "source": "NLB",
        "domains": ["nlb.gov.sg"],
        "venue": "Punggol Regional Library",
        "seeds": [
            "https://www.nlb.gov.sg/main/visit-us/our-libraries-and-locations/punggol-regional-library"
        ],
        "aliases": [
            "Punggol Regional Library",
            "NLB Punggol",
            "library@punggol",
            "National Library Board Punggol events",
        ],
        "local": True,
    },
    {
        "name": "One Punggol",
        "source": "One Punggol",
        "domains": ["onepunggol.sg"],
        "venue": "One Punggol",
        "seeds": ["https://www.onepunggol.sg/"],
        "aliases": ["One Punggol"],
        "local": True,
    },
    {
        "name": "onePA / People's Association",
        "source": "onePA",
        "domains": ["onepa.gov.sg"],
        "venue": "People's Association CCs",
        "seeds": ["https://www.onepa.gov.sg/"],
        "aliases": [
            "Punggol onePA",
            "Punggol CC",
            "Punggol 21 CC",
            "Punggol West CC",
            "People's Association",
        ],
        "local": True,
    },
    {
        "name": "SAFRA Punggol",
        "source": "SAFRA Punggol",
        "domains": ["safra.sg"],
        "venue": "SAFRA Punggol",
        "seeds": ["https://www.safra.sg/amenities-offerings/safra-punggol"],
        "aliases": [
            "SAFRA Punggol",
            "SAFRA family",
            "SAFRA children",
        ],
        "local": True,
    },
    {
        "name": "Waterway Point",
        "source": "Waterway Point",
        "domains": ["waterwaypoint.com.sg"],
        "venue": "Waterway Point",
        "seeds": ["https://www.waterwaypoint.com.sg/"],
        "aliases": ["Waterway Point"],
        "local": True,
    },
    {
        "name": "Singapore Zoo",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Singapore Zoo",
        "seeds": ["https://www.mandai.com/en/singapore-zoo.html"],
        "aliases": ["Singapore Zoo", "Mandai Singapore Zoo"],
    },
    {
        "name": "River Wonders",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "River Wonders",
        "seeds": ["https://www.mandai.com/en/river-wonders.html"],
        "aliases": ["River Wonders", "Mandai River Wonders"],
    },
    {
        "name": "Bird Paradise",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Bird Paradise",
        "seeds": ["https://www.mandai.com/en/bird-paradise.html"],
        "aliases": ["Bird Paradise", "Mandai Bird Paradise"],
    },
    {
        "name": "Night Safari",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Night Safari",
        "seeds": ["https://www.mandai.com/en/night-safari.html"],
        "aliases": ["Night Safari", "Mandai Night Safari"],
    },
    {
        "name": "Sentosa",
        "source": "Sentosa",
        "domains": ["sentosa.com.sg"],
        "venue": "Sentosa",
        "seeds": ["https://www.sentosa.com.sg/"],
        "aliases": ["Sentosa", "Sentosa family", "Sentosa kids"],
    },
    {
        "name": "Resorts World Sentosa",
        "source": "Resorts World Sentosa",
        "domains": ["rwsentosa.com"],
        "venue": "Resorts World Sentosa",
        "seeds": ["https://www.rwsentosa.com/"],
        "aliases": [
            "Resorts World Sentosa",
            "RWS",
            "Universal Studios Singapore",
            "SEA Aquarium",
        ],
    },
]

COMMON_SEED_PATHS = (
    "/events",
    "/event",
    "/whats-on",
    "/whatson",
    "/happenings",
    "/things-to-do",
    "/things-to-do/events",
    "/programmes",
    "/programs",
    "/activities",
    "/family",
    "/kids",
)

EVENT_WORDS = (
    "event",
    "events",
    "programme",
    "program",
    "programmes",
    "programs",
    "workshop",
    "workshops",
    "activity",
    "activities",
    "course",
    "class",
    "club",
    "session",
    "talk",
    "tour",
    "story",
    "storytelling",
    "storytime",
    "family",
    "children",
    "kids",
    "festival",
    "performance",
    "carnival",
    "conversation",
    "training",
    "reading",
    "exhibition",
    "show",
    "camp",
    "meet",
    "meeting",
    "walk",
    "trail",
    "experience",
    "experiences",
    "drop-in",
    "drop in",
    "screening",
)

EVENT_PATH_HINTS = (
    "/event",
    "/events",
    "/programme",
    "/programmes",
    "/program",
    "/programs",
    "/course",
    "/courses",
    "/workshop",
    "/activities",
    "/activity",
    "/whats-on",
    "/whatson",
    "/happenings",
    "/happening",
    "/things-to-do",
    "/experiences",
    "/experience",
    "/family",
    "/kids",
    "/children",
    "/calendar",
)

BAD_WORDS = (
    "privacy policy",
    "terms of use",
    "cookie",
    "facebook",
    "instagram",
    "youtube",
    "linkedin",
    "pdf",
    "career",
    "job",
    "property",
    "condo",
    "rental",
    "parking",
    "directions",
    "opening hours",
    "contact us",
    "about us",
    "venue hire",
    "press release",
    "annual report",
    "media release",
)

BAD_EXT = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".mp4",
    ".mp3",
    ".css",
    ".js",
    ".woff",
    ".woff2",
)

GENERIC_TITLES = {
    "events",
    "event",
    "what's on",
    "whats on",
    "things to do",
    "programmes",
    "programs",
    "activities",
    "home",
    "homepage",
    "visit us",
    "contact us",
    "about us",
    "calendar",
    "happenings",
}

DATE_RE = re.compile(
    r"("
    r"\b\d{1,2}\s*(?:-|to|–|—)\s*\d{1,2}\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b|"
    r"\b\d{1,2}\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    r"\s*(?:-|to|–|—)?\s*\d{0,2}\s*"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?[a-z]*\s+\d{4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\btoday\b|\btomorrow\b|\btonight\b|\bthis weekend\b"
    r")",
    re.I,
)

JSON_LD_EVENT_RE = re.compile(
    r'"@type"\s*:\s*(?:"Event"|\[[^\]]*"Event"[^\]]*\])',
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
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def host(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def same_source_domain(url, source):
    h = host(url)
    return bool(h) and any(h.endswith(d) for d in source["domains"])


def normalize_url(url, base=None):
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

    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (k, v)
        for k, v in query
        if not k.lower().startswith("utm_")
        and k.lower() not in ("fbclid", "gclid", "cmpid")
    ]

    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            urllib.parse.urlencode(query),
            "",
        )
    )


def url_key(url):
    p = urlparse(url)
    return urllib.parse.urlunparse(
        (p.scheme, p.netloc, p.path.rstrip("/"), "", p.query, "")
    ).lower()


def fetch(url, timeout=8):
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


def meta_content(page, names):
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


def strip_title_suffix(title):
    title = textify(title)
    title = re.sub(
        r"\s*[\|\-–]\s*"
        r"(NLB|National Library Board|onePA|One Punggol|SAFRA|Mandai|"
        r"Sentosa|Resorts World Sentosa|Singapore|National Heritage Board)\s*$",
        "",
        title,
        flags=re.I,
    )
    return textify(title)


def extract_title(page, fallback):
    vals = [
        meta_content(page, ["og:title", "twitter:title"]),
    ]

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


def extract_summary(page, fallback):
    vals = [
        meta_content(page, ["og:description", "description", "twitter:description"]),
        fallback,
    ]

    plain = textify(page)
    for word in EVENT_WORDS:
        m = re.search(r"([^.。!?]*\b" + re.escape(word) + r"\b[^.。!?]*[.。!?]?)", plain, re.I)
        if m:
            vals.append(m.group(1))
            break

    for v in vals:
        v = shorten(v, 220)
        if v:
            return v

    return "Open the official page for details."


def extract_date(*vals):
    blob = " ".join(textify(v) for v in vals if v)
    m = DATE_RE.search(blob)
    return textify(m.group(1)) if m else "Check official page"


def has_event_schema(page):
    return bool(JSON_LD_EVENT_RE.search(page[:500_000]))


def has_any(text, words):
    text = textify(text).lower()
    return any(w.lower() in text for w in words)


def event_path_score(url):
    p = urlparse(url).path.lower()
    score = 0
    for hint in EVENT_PATH_HINTS:
        if hint in p:
            score += 12
    if YEAR in url:
        score += 4
    return score


def bad_url(url):
    p = urlparse(url).path.lower()
    if any(p.endswith(ext) for ext in BAD_EXT):
        return True
    if any(
        x in p
        for x in (
            "/privacy",
            "/terms",
            "/contact",
            "/about",
            "/career",
            "/login",
            "/register/login",
            "/cart",
            "/checkout",
        )
    ):
        return True
    return False


def alias_score(source, blob):
    score = 0
    for alias in source.get("aliases", []):
        for part in re.split(r"\W+", alias.lower()):
            if len(part) >= 4 and part in blob:
                score += 2
    return score


def link_score(source, url, anchor):
    if not url or bad_url(url) or not same_source_domain(url, source):
        return -999

    blob = f"{url} {anchor}".lower()
    score = event_path_score(url)

    for w in EVENT_WORDS:
        if w in blob:
            score += 5

    score += alias_score(source, blob)

    if YEAR in blob:
        score += 4

    for bad in BAD_WORDS:
        if bad in blob:
            score -= 40

    return score


def extract_links(page, base_url, source):
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        url = normalize_url(m.group(1), base_url)
        anchor = textify(m.group(2))
        score = link_score(source, url, anchor)
        if score >= 8:
            out.append((score, url, anchor))

    out.sort(key=lambda x: -x[0])
    return out


def is_generic_event_title(source, title, date, url):
    t = textify(title).lower()
    if not t:
        return True

    if t in GENERIC_TITLES and date == "Check official page":
        return True

    for name in [source["name"], source["source"], source["venue"]]:
        if t == textify(name).lower() and date == "Check official page":
            return True

    p = urlparse(url).path.lower()
    if (p in ("", "/") or p.endswith("/contact") or p.endswith("/about")) and date == "Check official page":
        return True

    return False


def page_event_score(source, url, title, summary, body, location, schema_event):
    blob = f"{title} {summary} {url} {body[:5000]}".lower()
    score = event_path_score(url)

    event_word_hits = [w for w in EVENT_WORDS if w in blob]
    score += min(len(event_word_hits), 10) * 4

    date = extract_date(title, summary, body[:4000])
    has_date = date != "Check official page"
    if has_date:
        score += 25

    if schema_event:
        score += 30

    score += alias_score(source, blob)

    loc_words = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    priority = any(w in blob for w in loc_words)

    if priority:
        score += 14

    for bad in BAD_WORDS:
        if bad in blob:
            score -= 70

    generic = is_generic_event_title(source, title, date, url)
    if generic:
        score -= 90

    # Strict guardrail: generic pages without a date or Event schema are not events,
    # even if they contain many event-ish words.
    if not has_date and not schema_event:
        score -= 35

    return score, date, priority, {
        "has_date": has_date,
        "schema_event": schema_event,
        "generic_title": generic,
        "event_word_hits": event_word_hits[:8],
    }


def build_event(source, url, page, location, seed_origin):
    title = extract_title(page, "")
    summary = extract_summary(page, "")
    body = textify(page)
    schema_event = has_event_schema(page)

    score, date, priority_location, evidence = page_event_score(
        source, url, title, summary, body, location, schema_event
    )

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
        "seed_origin": seed_origin,
        "evidence": evidence,
    }


def ddg_result_url(href):
    href = html.unescape(href or "")
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return qs["uddg"][0]
    return href


def ddg_search(query, deadline):
    if not ENABLE_DDG_DISCOVERY or time.monotonic() >= deadline:
        return []

    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        page = fetch(url, timeout=8)
    except Exception:
        return []

    urls = []
    seen = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', page, re.I):
        u = normalize_url(ddg_result_url(m.group(1)))
        if not u or "duckduckgo.com" in host(u):
            continue
        k = url_key(u)
        if k in seen:
            continue
        seen.add(k)
        urls.append(u)
    return urls


def discovery_queries(source, location):
    domains = " OR ".join(f"site:{d}" for d in source["domains"])
    aliases = [source["name"]] + source.get("aliases", [])[:3]
    terms = [
        "events",
        "what's on",
        "programmes",
        "kids family events",
    ]
    if source.get("local"):
        terms.insert(0, f"{location} events")

    out = []
    for alias in aliases[:4]:
        for term in terms[:3]:
            out.append(f'"{alias}" {term} {domains}')
    return out[:8]


def discovered_seed_urls(source, location, deadline):
    out = []
    seen = set()

    for query in discovery_queries(source, location):
        if time.monotonic() >= deadline or len(out) >= MAX_DDG_RESULTS_PER_SOURCE:
            break
        for url in ddg_search(query, deadline):
            if len(out) >= MAX_DDG_RESULTS_PER_SOURCE:
                break
            if not same_source_domain(url, source) or bad_url(url):
                continue
            k = url_key(url)
            if k in seen:
                continue
            seen.add(k)
            score = 90 + event_path_score(url)
            out.append((score, url, f"ddg:{query}"))
    return out


def source_seed_urls(source, location, deadline):
    seeds = []

    for seed in source.get("seeds", []):
        u = normalize_url(seed)
        if u and same_source_domain(u, source) and not bad_url(u):
            seeds.append((70 + event_path_score(u), u, "explicit_seed"))

    if ALLOW_COMMON_PATH_GUESSES:
        for seed in source.get("seeds", [])[:1]:
            p = urlparse(seed)
            root = f"{p.scheme}://{p.netloc}"
            for path in COMMON_SEED_PATHS:
                u = normalize_url(root + path)
                if u and same_source_domain(u, source) and not bad_url(u):
                    seeds.append((45 + event_path_score(u), u, "optional_common_path"))

    seeds.extend(discovered_seed_urls(source, location, deadline))

    out = []
    seen = set()
    for score, u, origin in sorted(seeds, key=lambda x: -x[0]):
        k = url_key(u)
        if k in seen:
            continue
        seen.add(k)
        out.append((score, u, origin))
    return out


def crawl_source(source, location, deadline):
    queue = []
    queued = set()
    fetched = set()
    events = []
    rejected = []
    seed_debug = []

    def push(url, score, origin):
        if not url or url_key(url) in queued or url_key(url) in fetched:
            return
        if not same_source_domain(url, source) or bad_url(url):
            return
        queued.add(url_key(url))
        queue.append((score, url, origin))

    for score, seed, origin in source_seed_urls(source, location, deadline):
        seed_debug.append({"url": seed, "origin": origin, "score": score})
        push(seed, score, origin)

    pages = 0
    candidates = 0

    while (
        queue
        and pages < MAX_PAGES_PER_SOURCE
        and len(events) < MAX_EVENTS_PER_SOURCE
        and time.monotonic() < deadline
    ):
        queue.sort(key=lambda x: -x[0])
        _, url, origin = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)

        try:
            page = fetch(url)
        except Exception as e:
            rejected.append(
                {
                    "url": url,
                    "origin": origin,
                    "reason": f"fetch_failed: {type(e).__name__}",
                }
            )
            continue

        pages += 1

        item = build_event(source, url, page, location, origin)
        if item:
            candidates += 1
            events.append(item)
        else:
            rejected.append(
                {
                    "url": url,
                    "origin": origin,
                    "reason": "below_event_threshold",
                    "title": shorten(extract_title(page, ""), 120),
                    "date": extract_date(extract_title(page, ""), extract_summary(page, ""), textify(page)[:4000]),
                }
            )

        for score, link, _anchor in extract_links(page, url, source)[:28]:
            push(link, score, f"linked_from:{host(url)}")

        if len(queue) > 160:
            queue.sort(key=lambda x: -x[0])
            queue[:] = queue[:100]

    return {
        "events": events,
        "debug": {
            "source": source["name"],
            "pages_fetched": pages,
            "queue_seen": len(queued),
            "accepted": len(events),
            "candidates": candidates,
            "seed_preview": seed_debug[:12],
            "rejected_preview": rejected[:8],
        },
        "source_card": {
            "type": "source",
            "title": source["name"],
            "url": source.get("seeds", [""])[0],
            "source": source["source"],
            "venue": source["venue"],
        },
    }


def dedupe_events(events):
    out = []
    seen = set()

    for item in events:
        key = re.sub(
            r"\W+",
            "",
            f'{item.get("source_name")} {item.get("title")} {item.get("venue")}'.lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def collect(location):
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
        "version": 5,
        "ok": True,
        "extractor": "official-source-discovery-ddg-strict",
        "updated_at": now_iso(),
        "location": location,
        "count": len(events),
        "results": events,
        "items": events,
        "sources": sources,
        "debug_by_source": debug,
        "settings": {
            "ddg_discovery": ENABLE_DDG_DISCOVERY,
            "allow_common_path_guesses": ALLOW_COMMON_PATH_GUESSES,
            "max_pages_per_source": MAX_PAGES_PER_SOURCE,
            "max_events_per_source": MAX_EVENTS_PER_SOURCE,
        },
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(
        f"local events updated count={len(events)} "
        f"sources={len(sources)} location={location}"
    )


if __name__ == "__main__":
    main()
