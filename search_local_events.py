#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, date, timedelta, date, timedelta
from pathlib import Path
from urllib.parse import urlparse, urljoin

BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
DEFAULT_LOCATION = "Punggol Singapore"
YEAR = str(datetime.now().year)
TODAY = date.today()
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))
MAX_RESULTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_RESULTS_PER_SOURCE", "4"))
TODAY = date.today()
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))
MAX_RESULTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_RESULTS_PER_SOURCE", "4"))

MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "78"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "8"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "8"))

SOURCE_REGISTRY = [
    {
        "name": "Children's Museum Singapore",
        "source": "Children's Museum Singapore",
        "domains": ["heritage.sg"],
        "venue": "Children's Museum Singapore",
        "seeds": [
            "https://www.heritage.sg/childrensmuseum/",
            "https://www.heritage.sg/childrensmuseum/whatson",
            "https://www.heritage.sg/childrensmuseum/whatson/childrens-season---listing-page",
        ],
        "aliases": ["Children's Museum Singapore", "Children's Season Singapore", "Children's Season"],
    },
    {
        "name": "National Gallery Singapore",
        "source": "National Gallery Singapore",
        "domains": ["nationalgallery.sg"],
        "venue": "National Gallery Singapore",
        "seeds": [
            "https://www.nationalgallery.sg/",
            "https://www.nationalgallery.sg/whats-on",
            "https://www.nationalgallery.sg/sg/en/whats-on.html",
        ],
        "aliases": ["National Gallery Singapore", "National Gallery family", "National Gallery children"],
    },
    {
        "name": "National Museum Singapore",
        "source": "National Museum Singapore",
        "domains": ["nhb.gov.sg"],
        "venue": "National Museum Singapore",
        "seeds": [
            "https://www.nhb.gov.sg/nationalmuseum/",
            "https://www.nhb.gov.sg/nationalmuseum/whats-on",
        ],
        "aliases": ["National Museum Singapore", "National Museum family", "National Museum children"],
    },
    {
        "name": "Asian Civilisations Museum",
        "source": "Asian Civilisations Museum",
        "domains": ["nhb.gov.sg"],
        "venue": "Asian Civilisations Museum",
        "seeds": [
            "https://www.nhb.gov.sg/acm/",
            "https://www.nhb.gov.sg/acm/whats-on",
        ],
        "aliases": ["Asian Civilisations Museum", "ACM family", "ACM children"],
    },
    {
        "name": "Peranakan Museum",
        "source": "Peranakan Museum",
        "domains": ["nhb.gov.sg"],
        "venue": "Peranakan Museum",
        "seeds": [
            "https://www.nhb.gov.sg/peranakanmuseum/",
            "https://www.nhb.gov.sg/peranakanmuseum/whats-on",
        ],
        "aliases": ["Peranakan Museum", "Peranakan Museum family", "Peranakan Museum children"],
    },
    {
        "name": "ArtScience Museum",
        "source": "ArtScience Museum",
        "domains": ["marinabaysands.com"],
        "venue": "ArtScience Museum",
        "seeds": [
            "https://www.marinabaysands.com/museum.html",
            "https://www.marinabaysands.com/museum/events.html",
            "https://www.marinabaysands.com/museum/exhibitions.html",
        ],
        "aliases": ["ArtScience Museum", "ArtScience family", "ArtScience children"],
    },
    {
        "name": "Science Centre Singapore",
        "source": "Science Centre Singapore",
        "domains": ["science.edu.sg"],
        "venue": "Science Centre Singapore",
        "seeds": [
            "https://www.science.edu.sg/",
            "https://www.science.edu.sg/whats-on",
            "https://www.science.edu.sg/for-schools/programmes",
        ],
        "aliases": ["Science Centre Singapore", "KidsSTOP", "Science Centre kids"],
    },
    {
        "name": "NLB Punggol Regional Library",
        "source": "NLB",
        "domains": ["nlb.gov.sg"],
        "venue": "Punggol Regional Library",
        "seeds": [
            "https://www.nlb.gov.sg/main/visit-us/our-libraries-and-locations/punggol-regional-library",
            "https://www.nlb.gov.sg/main/whats-on",
        ],
        "aliases": ["Punggol Regional Library", "NLB Punggol", "library@punggol"],
    },
    {
        "name": "One Punggol",
        "source": "One Punggol",
        "domains": ["onepunggol.sg"],
        "venue": "One Punggol",
        "seeds": [
            "https://www.onepunggol.sg/",
            "https://www.onepunggol.sg/events",
            "https://www.onepunggol.sg/happenings",
        ],
        "aliases": ["One Punggol"],
    },
    {
        "name": "onePA / People's Association",
        "source": "onePA",
        "domains": ["onepa.gov.sg"],
        "venue": "People's Association CCs",
        "seeds": [
            "https://www.onepa.gov.sg/",
            "https://www.onepa.gov.sg/courses",
            "https://www.onepa.gov.sg/events",
        ],
        "aliases": ["Punggol onePA", "Punggol CC", "Punggol 21 CC", "Punggol West CC", "People's Association"],
    },
    {
        "name": "SAFRA Punggol",
        "source": "SAFRA Punggol",
        "domains": ["safra.sg"],
        "venue": "SAFRA Punggol",
        "seeds": [
            "https://www.safra.sg/",
            "https://www.safra.sg/whats-on",
            "https://www.safra.sg/amenities-offerings/safra-punggol",
        ],
        "aliases": ["SAFRA Punggol", "SAFRA family", "SAFRA children"],
    },
    {
        "name": "Waterway Point",
        "source": "Waterway Point",
        "domains": ["waterwaypoint.com.sg"],
        "venue": "Waterway Point",
        "seeds": [
            "https://www.waterwaypoint.com.sg/",
            "https://www.waterwaypoint.com.sg/happenings",
            "https://www.waterwaypoint.com.sg/promotions",
        ],
        "aliases": ["Waterway Point"],
    },
    {
        "name": "Singapore Zoo",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Singapore Zoo",
        "seeds": [
            "https://www.mandai.com/en/singapore-zoo.html",
            "https://www.mandai.com/en/things-to-do.html",
            "https://www.mandai.com/en/singapore-zoo/things-to-do.html",
        ],
        "aliases": ["Singapore Zoo", "Mandai Singapore Zoo"],
    },
    {
        "name": "River Wonders",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "River Wonders",
        "seeds": [
            "https://www.mandai.com/en/river-wonders.html",
            "https://www.mandai.com/en/river-wonders/things-to-do.html",
        ],
        "aliases": ["River Wonders"],
    },
    {
        "name": "Bird Paradise",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Bird Paradise",
        "seeds": [
            "https://www.mandai.com/en/bird-paradise.html",
            "https://www.mandai.com/en/bird-paradise/things-to-do.html",
        ],
        "aliases": ["Bird Paradise"],
    },
    {
        "name": "Night Safari",
        "source": "Mandai Wildlife Reserve",
        "domains": ["mandai.com"],
        "venue": "Night Safari",
        "seeds": [
            "https://www.mandai.com/en/night-safari.html",
            "https://www.mandai.com/en/night-safari/things-to-do.html",
        ],
        "aliases": ["Night Safari"],
    },
    {
        "name": "Sentosa",
        "source": "Sentosa",
        "domains": ["sentosa.com.sg"],
        "venue": "Sentosa",
        "seeds": [
            "https://www.sentosa.com.sg/",
            "https://www.sentosa.com.sg/en/things-to-do/events/",
            "https://www.sentosa.com.sg/en/things-to-do/",
        ],
        "aliases": ["Sentosa", "Sentosa family", "Sentosa kids"],
    },
    {
        "name": "Resorts World Sentosa",
        "source": "Resorts World Sentosa",
        "domains": ["rwsentosa.com"],
        "venue": "Resorts World Sentosa",
        "seeds": [
            "https://www.rwsentosa.com/",
            "https://www.rwsentosa.com/en/events",
            "https://www.rwsentosa.com/en/attractions",
        ],
        "aliases": ["Resorts World Sentosa", "RWS", "Universal Studios Singapore", "SEA Aquarium"],
    },
]

COMMON_SEED_PATHS = [
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
]

EVENT_WORDS = (
    "event", "events", "programme", "program", "programmes", "programs",
    "workshop", "workshops", "activity", "activities", "course", "class",
    "club", "session", "talk", "tour", "story", "storytelling", "storytime",
    "family", "children", "kids", "festival", "performance", "carnival",
    "conversation", "training", "reading", "exhibition", "show", "camp",
    "meet", "meeting", "walk", "trail", "experience", "experiences",
)

EVENT_PATH_HINTS = (
    "/event", "/events", "/programme", "/programmes", "/program",
    "/programs", "/course", "/courses", "/workshop", "/activities",
    "/activity", "/whats-on", "/whatson", "/happenings", "/happening",
    "/things-to-do", "/experiences", "/experience", "/family", "/kids",
    "/children", "/calendar",
)

BAD_WORDS = (
    "privacy policy", "terms of use", "cookie", "facebook", "instagram",
    "youtube", "linkedin", "pdf", "career", "job", "property", "condo",
    "rental", "parking", "directions", "opening hours", "contact us",
    "about us", "venue hire", "press release",
)

BAD_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf",
    ".zip", ".mp4", ".mp3", ".css", ".js", ".woff", ".woff2",
)

GENERIC_TITLES = {
    "events", "event", "what's on", "whats on", "things to do",
    "programmes", "programs", "activities", "home", "homepage",
    "visit us", "contact us", "about us",
}

DATE_RE = re.compile(
    r"("
    r"\b\d{1,2}\s*(?:-|to|–|—)\s*\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:-|to|–|—)?\s*\d{0,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?[a-z]*\s+\d{4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\btoday\b|\btomorrow\b|\btonight\b|\bthis weekend\b"
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
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"

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
        (k, v) for k, v in query
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]

    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        "",
        urllib.parse.urlencode(query),
        "",
    ))

def url_key(url):
    p = urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", p.query, "")).lower()

def fetch(url, timeout=7):
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
        r"\s*[\|\-–]\s*(NLB|National Library Board|onePA|One Punggol|SAFRA|Mandai|Sentosa|Resorts World Sentosa|Singapore)\s*$",
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
    if any(x in p for x in ("/privacy", "/terms", "/contact", "/about", "/career", "/login", "/register/login")):
        return True
    return False

def link_score(source, url, anchor):
    if not url or bad_url(url) or not same_source_domain(url, source):
        return -999

    blob = f"{url} {anchor}".lower()
    score = event_path_score(url)

    for w in EVENT_WORDS:
        if w in blob:
            score += 5

    for alias in source.get("aliases", []):
        for part in re.split(r"\W+", alias.lower()):
            if len(part) >= 4 and part in blob:
                score += 2

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

def page_event_score(source, url, title, summary, body, location):
    blob = f"{title} {summary} {url} {body[:5000]}".lower()
    score = event_path_score(url)

    for w in EVENT_WORDS:
        if w in blob:
            score += 4

    date = extract_date(title, summary, body[:4000])
    if date != "Check official page":
        score += 22

    for alias in source.get("aliases", []):
        for part in re.split(r"\W+", alias.lower()):
            if len(part) >= 4 and part in blob:
                score += 2

    loc_words = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    priority = any(w in blob for w in loc_words)

    if priority:
        score += 14

    for bad in BAD_WORDS:
        if bad in blob:
            score -= 70

    if is_generic_event_title(source, title, date, url):
        score -= 80

    return score, date, priority

NON_EVENT_PAGE_WORDS = (
    "address", "opening hours", "opening hour", "directions", "getting here",
    "contact us", "about us", "facilities", "amenities", "venue hire",
    "parking", "privacy policy", "terms of use", "faq", "frequently asked",
)

NON_EVENT_PATH_PARTS = (
    "/contact", "/about", "/privacy", "/terms", "/directions",
    "/getting-here", "/visit-us", "/facilities", "/amenities",
    "/parking", "/faq",
)

def is_check_date(value):
    return textify(value).lower() == "check official page"

def canonical_event_title(value):
    value = textify(value).lower()
    value = re.sub(r"\b\d{1,2}\s*(?:-|to|–|—)\s*\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b", " ", value)
    value = re.sub(r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", " ", value)
    value = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", " ", value)
    value = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", value)
    value = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", value)
    value = re.sub(r"\b\d{1,2}\s*(?:am|pm)\b", " ", value)
    value = re.sub(r"\b(today|tomorrow|tonight|weekend|mon|tue|wed|thu|fri|sat|sun)\b", " ", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def is_non_event_page(source, url, title, summary, body, date):
    title_l = textify(title).lower()
    summary_l = textify(summary).lower()
    path_l = urlparse(url).path.lower()
    blob = f"{title_l} {summary_l} {path_l}"

    if any(part in path_l for part in NON_EVENT_PATH_PARTS):
        return True

    if any(word in blob for word in NON_EVENT_PAGE_WORDS) and is_check_date(date):
        return True

    if is_generic_event_title(source, title, date, url):
        return True

    for name in (source.get("name"), source.get("source"), source.get("venue")):
        if title_l == textify(name).lower() and is_check_date(date):
            return True

    title_key = canonical_event_title(title)
    if len(title_key) < 4 and is_check_date(date):
        return True

    return False

def extract_sessions(page, title, summary, url):
    raw = html.unescape(page or "")
    text = " ".join([
        textify(title),
        textify(summary),
        textify(raw[:180000]),
        raw[:180000],
    ])

    sessions = []
    seen = set()

    def add(label):
        label = textify(label)
        if not label:
            return

        # avoid pure years like 2026 from sitemap/news pages
        if re.fullmatch(r"\d{4}", label):
            return

        key = label.lower()
        if key in seen:
            return
        seen.add(key)

        sessions.append({
            "date": label,
            "when": label,
            "label": label,
            "url": url,
        })

    # ISO ranges in JSON: "startDate":"2026-08-01", "endDate":"2026-08-31"
    for m in re.finditer(
        r'["\'](?:startDate|start_date|start|from|date)["\']\s*:\s*["\'](\d{4}-\d{1,2}-\d{1,2})(?:[T ][^"\']*)?["\'][\s\S]{0,220}?["\'](?:endDate|end_date|end|to)["\']\s*:\s*["\'](\d{4}-\d{1,2}-\d{1,2})(?:[T ][^"\']*)?["\']',
        raw,
        re.I,
    ):
        if m.group(1) == m.group(2):
            add(m.group(1))
        else:
            add(f"{m.group(1)} - {m.group(2)}")

    # reversed JSON order
    for m in re.finditer(
        r'["\'](?:endDate|end_date|end|to)["\']\s*:\s*["\'](\d{4}-\d{1,2}-\d{1,2})(?:[T ][^"\']*)?["\'][\s\S]{0,220}?["\'](?:startDate|start_date|start|from|date)["\']\s*:\s*["\'](\d{4}-\d{1,2}-\d{1,2})(?:[T ][^"\']*)?["\']',
        raw,
        re.I,
    ):
        if m.group(1) == m.group(2):
            add(m.group(1))
        else:
            add(f"{m.group(2)} - {m.group(1)}")

    # single ISO dates from HTML/JSON. Keep future filtering later.
    for m in re.finditer(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", raw):
        add(m.group(0))
        if len(sessions) >= 16:
            break

    # human-readable dates/ranges from visible text
    for m in DATE_RE.finditer(text):
        add(m.group(1))
        if len(sessions) >= 16:
            break

    return sessions[:16]

def summarize_sessions(sessions):
    dates = []
    seen = set()

    for session in sessions or []:
        date = textify(session.get("date") or session.get("when") or session.get("label"))
        key = date.lower()
        if not date or key in seen:
            continue
        seen.add(key)
        dates.append(date)

    if not dates:
        return "Check official page"

    if len(dates) == 1:
        return dates[0]

    shown = " / ".join(dates[:4])
    if len(dates) > 4:
        shown += f" / +{len(dates) - 4} more"

    return f"{len(dates)} sessions: {shown}"


MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

def parse_one_date(day, month_text, year_text=""):
    month = MONTHS[month_text[:3].lower()]
    year = int(year_text) if year_text else TODAY.year
    try:
        d = date(year, month, int(day))
        if not year_text and d < TODAY - timedelta(days=30):
            d = date(TODAY.year + 1, month, int(day))
        return d
    except ValueError:
        return None

def parse_event_dates_from_label(value):
    text = textify(value).lower()
    if not text:
        return []

    dates = []

    if "today" in text:
        dates.append(TODAY)
    if "tomorrow" in text:
        dates.append(TODAY + timedelta(days=1))

    # 12 Jun - 31 Aug 2026 / 12 June to 31 August 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(?:-|to|–|—|until|till)\s*"
        r"(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        end_year = m.group(5) or str(TODAY.year)
        d1 = parse_one_date(m.group(1), m.group(2), end_year)
        d2 = parse_one_date(m.group(3), m.group(4), end_year)
        if d1:
            dates.append(d1)
        if d2:
            dates.append(d2)

    # 12 - 31 Aug 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        year = m.group(4) or str(TODAY.year)
        d1 = parse_one_date(m.group(1), m.group(3), year)
        d2 = parse_one_date(m.group(2), m.group(3), year)
        if d1:
            dates.append(d1)
        if d2:
            dates.append(d2)

    # 12 Jun 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        d = parse_one_date(m.group(1), m.group(2), m.group(3) or "")
        if d:
            dates.append(d)

    # Jun 12 2026
    for m in re.finditer(
        r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s+(\d{1,2}),?\s*(\d{4})?\b",
        text,
        re.I,
    ):
        d = parse_one_date(m.group(2), m.group(1), m.group(3) or "")
        if d:
            dates.append(d)

    # 25/06/2026
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            dates.append(date(year, month, day))
        except ValueError:
            pass

    out = []
    seen = set()
    for d in dates:
        if d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        out.append(d)

    return out

def parse_one_date(day, month_text, year_text=""):
    month = MONTHS[month_text[:3].lower()]
    year = int(year_text) if year_text else TODAY.year
    try:
        d = date(year, month, int(day))
        if not year_text and d < TODAY - timedelta(days=30):
            d = date(TODAY.year + 1, month, int(day))
        return d
    except ValueError:
        return None

def parse_event_dates_from_label(value):
    text = textify(value).lower()
    if not text:
        return []

    dates = []

    if "today" in text:
        dates.append(TODAY)
    if "tomorrow" in text:
        dates.append(TODAY + timedelta(days=1))

    # 12 Jun - 31 Aug 2026 / 12 June to 31 August 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(?:-|to|–|—|until|till)\s*"
        r"(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        end_year = m.group(5) or str(TODAY.year)
        d1 = parse_one_date(m.group(1), m.group(2), end_year)
        d2 = parse_one_date(m.group(3), m.group(4), end_year)
        if d1:
            dates.append(d1)
        if d2:
            dates.append(d2)

    # 12 - 31 Aug 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        year = m.group(4) or str(TODAY.year)
        d1 = parse_one_date(m.group(1), m.group(3), year)
        d2 = parse_one_date(m.group(2), m.group(3), year)
        if d1:
            dates.append(d1)
        if d2:
            dates.append(d2)

    # 12 Jun 2026
    for m in re.finditer(
        r"\b(\d{1,2})\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s*(\d{4})?\b",
        text,
        re.I,
    ):
        d = parse_one_date(m.group(1), m.group(2), m.group(3) or "")
        if d:
            dates.append(d)

    # Jun 12 2026
    for m in re.finditer(
        r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*"
        r"\s+(\d{1,2}),?\s*(\d{4})?\b",
        text,
        re.I,
    ):
        d = parse_one_date(m.group(2), m.group(1), m.group(3) or "")
        if d:
            dates.append(d)

    # 25/06/2026
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            dates.append(date(year, month, day))
        except ValueError:
            pass

    out = []
    seen = set()
    for d in dates:
        if d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        out.append(d)

    return out

def parse_event_date_label(value):
    dates = parse_event_dates_from_label(value)
    return min(dates) if dates else None

def latest_event_date_label(value):
    dates = parse_event_dates_from_label(value)
    return max(dates) if dates else None

def is_future_or_current_session(label):
    latest = latest_event_date_label(label)
    if not latest:
        return False
    return latest >= TODAY - timedelta(days=PAST_GRACE_DAYS)


def filter_future_sessions(sessions):
    out = []
    seen = set()

    for session in sessions or []:
        label = textify(session.get("date") or session.get("when") or session.get("label"))
        if not label:
            continue
        if not is_future_or_current_session(label):
            continue

        key = label.lower()
        if key in seen:
            continue
        seen.add(key)

        session = dict(session)
        parsed_start = parse_event_date_label(label)
        parsed_end = latest_event_date_label(label)
        if parsed_start:
            session["start_date"] = parsed_start.isoformat()
        if parsed_end:
            session["end_date"] = parsed_end.isoformat()
        out.append(session)

    out.sort(key=lambda x: x.get("start_date", "9999-12-31"))
    return out

def has_valid_future_date(item):
    sessions = item.get("sessions") or []
    if sessions:
        return bool(filter_future_sessions(sessions))

    label = textify(item.get("date") or item.get("when"))
    return bool(label and is_future_or_current_session(label))


OFFER_OR_INFO_WORDS = (
    "exclusive perks", "perks", "privileges", "promotion", "promotions",
    "deals", "discount", "discounts", "membership", "member benefits",
    "national servicemen", "families", "credit card", "voucher",
    "shop", "shopping", "dining privilege", "reward", "rewards",
)

def looks_like_non_event_offer(title, summary="", url=""):
    blob = f"{textify(title)} {textify(summary)} {urlparse(url).path}".lower()

    if any(word in blob for word in OFFER_OR_INFO_WORDS):
        # A real event page usually has stronger event words in title/summary/path.
        strong_event_words = (
            "workshop", "class", "course", "talk", "tour", "storytime",
            "festival", "performance", "concert", "exhibition", "programme",
            "program", "activity", "event", "session", "walk", "camp",
        )
        if not any(word in blob for word in strong_event_words):
            return True

    return False

def build_event(source, url, page, location):
    title = extract_title(page, "")
    summary = extract_summary(page, "")
    body = textify(page)

    if looks_like_non_event_offer(title, summary, url):
        return None

    sessions = extract_sessions(page, title, summary, url)
    sessions = filter_future_sessions(sessions)

    if not sessions:
        return None

    score, _date, priority_location = page_event_score(source, url, title, summary, body, location)

    # A real event-like detail URL with future sessions should not be dropped only
    # because the visible text score is weak. Many sites render details from JSON.
    if event_path_score(url) >= 12:
        score = max(score, 55)

    if score < 35:
        return None

    if is_non_event_page(source, url, title, summary, body, summarize_sessions(sessions)):
        return None

    when_text = summarize_sessions(sessions)

    return {
        "type": "event",
        "title": shorten(title, 150),
        "poster_title": shorten(title, 150),
        "what": shorten(title, 150),
        "when": when_text,
        "date": when_text,
        "sessions": sessions,
        "session_count": len(sessions),
        "where": source["venue"],
        "venue": source["venue"],
        "who": source["source"],
        "organizer": source["source"],
        "why": shorten(summary, 220),
        "description": shorten(summary, 260),
        "how": "Official page",
        "summary": shorten(summary, 260),
        "poster_summary": shorten(summary, 220),
        "source": source["source"],
        "source_name": source["name"],
        "url": url,
        "score": score,
        "priority_location": priority_location,
    }


def unwrap_search_url(url):
    url = html.unescape(url or "").strip()
    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urljoin("https://duckduckgo.com", url)

    parsed = urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)

    if "uddg" in qs and qs["uddg"]:
        url = qs["uddg"][0]

    return normalize_url(url)

def discovery_queries(source):
    domains = source.get("domains", [])
    names = [source.get("name", ""), source.get("venue", ""), source.get("source", "")]
    names.extend(source.get("aliases", [])[:3])

    names = [textify(x) for x in names if textify(x)]
    names = list(dict.fromkeys(names))

    queries = []

    for domain in domains:
        for name in names[:3]:
            queries.extend([
                f"site:{domain} {name} events",
                f"site:{domain} {name} whats on",
                f"site:{domain} {name} programme",
                f"site:{domain} {name} workshop",
                f"site:{domain} {name} kids family",
                f"site:{domain} {name} {YEAR}",
            ])

        queries.extend([
            f"site:{domain} events {YEAR}",
            f"site:{domain} whats on {YEAR}",
            f"site:{domain} programme {YEAR}",
        ])

    return list(dict.fromkeys(queries))

def parse_duckduckgo_results(page, query):
    results = []

    for m in re.finditer(
        r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        page,
        re.I,
    ):
        href = m.group(1)
        title = textify(m.group(2))
        tail = page[m.end():m.end() + 1800]

        snippet = ""
        sm = re.search(
            r'class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>([\s\S]*?)</',
            tail,
            re.I,
        )
        if sm:
            snippet = textify(sm.group(1))

        results.append({
            "url": unwrap_search_url(href),
            "title": title,
            "snippet": snippet,
            "query": query,
        })

    if not results:
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', page, re.I):
            href = m.group(1)
            title = textify(m.group(2))
            if not title or len(title) < 4:
                continue

            results.append({
                "url": unwrap_search_url(href),
                "title": title,
                "snippet": "",
                "query": query,
            })

    return results

def duckduckgo_search_results(source, deadline):
    if os.environ.get("LOCAL_EVENTS_USE_SEARCH", "1") != "1":
        return []

    max_queries = int(os.environ.get("LOCAL_EVENTS_SEARCH_QUERIES_PER_SOURCE", "6"))
    max_results = int(os.environ.get("LOCAL_EVENTS_SEARCH_URLS_PER_SOURCE", "16"))

    found = []
    seen = set()

    endpoints = [
        "https://duckduckgo.com/html/?",
        "https://html.duckduckgo.com/html/?",
        "https://lite.duckduckgo.com/lite/?",
    ]

    for query in discovery_queries(source)[:max_queries]:
        if time.monotonic() >= deadline:
            break

        for endpoint in endpoints:
            if time.monotonic() >= deadline:
                break

            search_url = endpoint + urllib.parse.urlencode({"q": query})

            try:
                page = fetch(search_url, timeout=8)
            except Exception:
                continue

            parsed = parse_duckduckgo_results(page, query)

            for item in parsed:
                url = item.get("url") or ""
                if not url:
                    continue
                if not same_source_domain(url, source):
                    continue
                if bad_url(url):
                    continue

                key = url_key(url)
                if key in seen:
                    continue

                seen.add(key)
                found.append(item)

                if len(found) >= max_results:
                    return found

            if parsed:
                break

    return found

def duckduckgo_discover_urls(source, deadline):
    return [x["url"] for x in duckduckgo_search_results(source, deadline)]

def search_result_event(source, result, location):
    url = result.get("url") or ""
    title = strip_title_suffix(result.get("title") or "")
    snippet = textify(result.get("snippet") or "")

    if not title or not url:
        return None

    if "looks_like_non_event_offer" in globals() and looks_like_non_event_offer(title, snippet, url):
        return None

    blob = f"{title} {snippet} {url}"

    if any(bad in blob.lower() for bad in BAD_WORDS):
        return None

    if canonical_event_title(title) in GENERIC_TITLES:
        return None

    sessions = extract_sessions(blob, title, snippet, url)
    sessions = filter_future_sessions(sessions)

    if not sessions:
        return None

    loc_words = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    priority_location = any(w in blob.lower() for w in loc_words)

    score = 70 + event_path_score(url)
    for w in EVENT_WORDS:
        if w in blob.lower():
            score += 3
    if priority_location:
        score += 14

    summary = shorten(snippet or title, 260)

    return {
        "type": "event",
        "title": shorten(title, 150),
        "poster_title": shorten(title, 150),
        "what": shorten(title, 150),
        "when": summarize_sessions(sessions),
        "date": summarize_sessions(sessions),
        "sessions": sessions,
        "session_count": len(sessions),
        "where": source["venue"],
        "venue": source["venue"],
        "who": source["source"],
        "organizer": source["source"],
        "why": summary,
        "description": summary,
        "how": "Official page",
        "summary": summary,
        "poster_summary": summary,
        "source": source["source"],
        "source_name": source["name"],
        "url": url,
        "score": score,
        "priority_location": priority_location,
        "discovered_by": "duckduckgo",
    }



def source_roots(source):
    roots = []

    for seed in source.get("seeds", []):
        u = normalize_url(seed)
        if not u:
            continue
        p = urlparse(u)
        if p.scheme and p.netloc:
            roots.append(f"{p.scheme}://{p.netloc}")

    for domain in source.get("domains", []):
        roots.append("https://www." + domain)
        roots.append("https://" + domain)

    out = []
    seen = set()

    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        out.append(root)

    return out

def sitemap_score(source, url):
    url_l = url.lower()
    path_l = urlparse(url).path.lower()

    score = event_path_score(url)

    for word in EVENT_WORDS:
        if word in url_l:
            score += 3

    for alias in source.get("aliases", []):
        for part in re.split(r"\W+", alias.lower()):
            if len(part) >= 4 and part in url_l:
                score += 2

    if YEAR in url_l:
        score += 6

    bad_path_parts = globals().get("NON_EVENT_PATH_PARTS", ())
    if any(part in path_l for part in bad_path_parts):
        score -= 60

    if any(word in url_l for word in (
        "promotion", "privilege", "membership", "perks", "deals",
        "privacy", "terms", "career", "contact-us", "about-us",
    )):
        score -= 30

    return score

def parse_sitemap_locs(xml_text):
    locs = []

    for m in re.finditer(r"<loc>\s*([\s\S]*?)\s*</loc>", xml_text, re.I):
        u = textify(m.group(1))
        if u:
            locs.append(u)

    return locs

def robots_sitemaps(root):
    out = []

    try:
        txt = fetch(root.rstrip("/") + "/robots.txt", timeout=6)
    except Exception:
        return out

    for line in txt.splitlines():
        if line.lower().startswith("sitemap:"):
            u = normalize_url(line.split(":", 1)[1].strip())
            if u:
                out.append(u)

    return out

def discover_sitemap_urls(source, deadline):
    if os.environ.get("LOCAL_EVENTS_USE_SITEMAP", "1") != "1":
        return []

    max_docs = int(os.environ.get("LOCAL_EVENTS_SITEMAP_DOCS_PER_SOURCE", "8"))
    max_urls = int(os.environ.get("LOCAL_EVENTS_SITEMAP_URLS_PER_SOURCE", "24"))

    sitemap_queue = []
    sitemap_seen = set()
    url_seen = set()
    found = []

    def push_sitemap(u):
        u = normalize_url(u)
        if not u:
            return
        if u in sitemap_seen:
            return
        if not same_source_domain(u, source):
            return

        sitemap_seen.add(u)
        sitemap_queue.append(u)

    for root in source_roots(source):
        push_sitemap(root.rstrip("/") + "/sitemap.xml")
        push_sitemap(root.rstrip("/") + "/sitemap_index.xml")
        push_sitemap(root.rstrip("/") + "/sitemap-index.xml")

        for u in robots_sitemaps(root):
            push_sitemap(u)

    docs = 0

    while sitemap_queue and docs < max_docs and time.monotonic() < deadline:
        sm_url = sitemap_queue.pop(0)

        try:
            xml_text = fetch(sm_url, timeout=8)
        except Exception:
            continue

        docs += 1
        locs = parse_sitemap_locs(xml_text)

        for loc in locs:
            u = normalize_url(loc)
            if not u:
                continue

            if u.lower().endswith(".xml") and same_source_domain(u, source):
                push_sitemap(u)
                continue

            if not same_source_domain(u, source):
                continue
            if bad_url(u):
                continue

            score = sitemap_score(source, u)
            if score < 8:
                continue

            key = url_key(u)
            if key in url_seen:
                continue

            url_seen.add(key)
            found.append((score, u))

            if len(found) >= max_urls:
                break

    found.sort(key=lambda x: -x[0])
    return [u for _score, u in found[:max_urls]]


def source_seed_urls(source, deadline=None, search_results=None):
    seeds = list(source.get("seeds", []))

    if deadline is None:
        deadline = time.monotonic() + 20

    if search_results is None:
        search_results = duckduckgo_search_results(source, deadline)

    search_urls = [x.get("url") for x in search_results if x.get("url")]
    sitemap_urls = discover_sitemap_urls(source, deadline)

    source["_last_search_urls"] = search_urls[:20]
    source["_last_sitemap_urls"] = sitemap_urls[:20]

    # real discovered URLs first
    seeds = search_urls + sitemap_urls + seeds

    # guessed common paths only when manually enabled
    if os.environ.get("LOCAL_EVENTS_EXPAND_COMMON_PATHS", "0") == "1":
        for seed in source.get("seeds", [])[:1]:
            p = urlparse(seed)
            root = f"{p.scheme}://{p.netloc}"
            for path in COMMON_SEED_PATHS:
                seeds.append(root + path)

    out = []
    seen = set()

    for u in seeds:
        u = normalize_url(u)
        if not u:
            continue
        if u in seen:
            continue
        if not same_source_domain(u, source):
            continue
        if bad_url(u):
            continue

        seen.add(u)
        out.append(u)

    return out

def crawl_source(source, location, deadline):
    search_results = duckduckgo_search_results(source, deadline)
    seed_urls = source_seed_urls(source, deadline, search_results)

    queue = []
    queued = set()
    fetched = set()
    events = []
    rejected = []
    built_rejected = []
    fetched_preview = []

    def push(url, score):
        if not url or url_key(url) in queued or url_key(url) in fetched:
            return
        if not same_source_domain(url, source) or bad_url(url):
            return
        queued.add(url_key(url))
        queue.append((score, url))

    for result in search_results:
        item = search_result_event(source, result, location)
        if item:
            events.append(item)

    for seed in seed_urls:
        push(seed, 80 + event_path_score(seed))

    pages = 0
    candidates = len(events)

    while queue and pages < MAX_PAGES_PER_SOURCE and len(events) < MAX_EVENTS_PER_SOURCE and time.monotonic() < deadline:
        queue.sort(key=lambda x: -x[0])
        _, url = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)

        try:
            page = fetch(url)
        except Exception as e:
            rejected.append({"url": url, "reason": f"fetch_failed: {type(e).__name__}"})
            continue

        pages += 1
        fetched_preview.append({
            "url": url,
            "title": shorten(extract_title(page, url), 90),
        })

        structured_builder = globals().get("build_structured_events")
        structured_items = structured_builder(source, url, page, location) if structured_builder else []

        if structured_items:
            candidates += len(structured_items)
            events.extend(structured_items)
        else:
            item = build_event(source, url, page, location)
            if item:
                candidates += 1
                events.append(item)
            else:
                built_rejected.append({
                    "url": url,
                    "title": shorten(extract_title(page, url), 90),
                    "sessions_found": len(extract_sessions(page, extract_title(page, ""), extract_summary(page, ""), url)),
                })

        for score, link, _anchor in extract_links(page, url, source)[:28]:
            push(link, score)

        if len(queue) > 160:
            queue.sort(key=lambda x: -x[0])
            queue[:] = queue[:100]

    return {
        "events": events,
        "debug": {
            "source": source["name"],
            "search_results": len(search_results),
            "search_preview": [
                {
                    "title": x.get("title"),
                    "url": x.get("url"),
                    "snippet": shorten(x.get("snippet", ""), 100),
                    "query": x.get("query"),
                }
                for x in search_results[:8]
            ],
            "seed_urls": seed_urls[:12],
            "search_urls": source.get("_last_search_urls", [])[:12],
            "sitemap_urls": source.get("_last_sitemap_urls", [])[:12],
            "pages_fetched": pages,
            "queue_seen": len(queued),
            "accepted": len(events),
            "candidates": candidates,
            "failed_fetches": len(rejected),
            "fetched_preview": fetched_preview[:8],
            "accepted_preview": [
                {
                    "title": x.get("title"),
                    "when": x.get("when"),
                    "url": x.get("url"),
                }
                for x in events[:6]
            ],
            "built_rejected_preview": built_rejected[:8],
            "rejected_preview": rejected[:5],
        },
        "source_card": {
            "type": "source",
            "title": source["name"],
            "url": source.get("seeds", [""])[0],
            "source": source["source"],
            "venue": source["venue"],
        },
    }

def useful_url_score(url):
    p = urlparse(url).path.lower()
    score = 0
    for hint in EVENT_PATH_HINTS:
        if hint in p:
            score += 10
    if any(part in p for part in NON_EVENT_PATH_PARTS):
        score -= 50
    if p in ("", "/"):
        score -= 40
    if YEAR in url:
        score += 5
    return score

def merge_unique_sessions(dst, src):
    seen = {
        textify(x.get("date") or x.get("when") or x.get("label")).lower()
        for x in dst
    }

    for session in src or []:
        date = textify(session.get("date") or session.get("when") or session.get("label"))
        if not date:
            continue
        key = date.lower()
        if key in seen:
            continue
        seen.add(key)
        dst.append({
            "date": date,
            "when": date,
            "label": date,
            "url": session.get("url") or "",
        })

def event_group_key(item):
    source = textify(item.get("source_name") or item.get("source"))
    venue = textify(item.get("venue") or item.get("where"))
    title = textify(item.get("title") or item.get("what"))
    title_key = canonical_event_title(title)

    if len(title_key) >= 6:
        return f"title::{source.lower()}::{venue.lower()}::{title_key}"

    url = item.get("url") or ""
    if url:
        return f"url::{url_key(url)}"

    return f"fallback::{source.lower()}::{venue.lower()}::{title.lower()}"

def is_bad_event_item(item):
    title = textify(item.get("title") or item.get("what"))
    summary = textify(item.get("summary") or item.get("why") or item.get("description"))
    date = textify(item.get("when") or item.get("date"))
    url = item.get("url") or ""

    blob = f"{title} {summary} {urlparse(url).path}".lower()

    if not title:
        return True

    if any(word in blob for word in NON_EVENT_PAGE_WORDS) and "session" not in date.lower() and is_check_date(date):
        return True

    if canonical_event_title(title) in GENERIC_TITLES:
        return True

    return False

def dedupe_events(events):
    grouped = {}

    for item in events:
        if is_bad_event_item(item):
            continue

        key = event_group_key(item)
        sessions = list(item.get("sessions") or [])

        if not sessions:
            date = textify(item.get("date") or item.get("when"))
            if date and not is_check_date(date):
                sessions = [{
                    "date": date,
                    "when": date,
                    "label": date,
                    "url": item.get("url") or "",
                }]

        if key not in grouped:
            base = dict(item)
            base["sessions"] = []
            merge_unique_sessions(base["sessions"], sessions)
            grouped[key] = base
            continue

        base = grouped[key]

        merge_unique_sessions(base["sessions"], sessions)

        if int(item.get("score", 0)) > int(base.get("score", 0)):
            base["score"] = item.get("score", base.get("score", 0))

        if item.get("priority_location"):
            base["priority_location"] = True

        for field in ("summary", "why", "description", "poster_summary"):
            old = textify(base.get(field))
            new = textify(item.get(field))
            if len(new) > len(old):
                base[field] = item.get(field)

        old_url = base.get("url") or ""
        new_url = item.get("url") or ""
        if new_url and useful_url_score(new_url) > useful_url_score(old_url):
            base["url"] = new_url

    out = []

    for item in grouped.values():
        sessions = filter_future_sessions(item.get("sessions") or [])
        if not sessions:
            continue

        item["sessions"] = sessions
        item["session_count"] = len(sessions)
        item["when"] = summarize_sessions(sessions)
        item["date"] = item["when"]

        if not item.get("how"):
            item["how"] = "Official page"

        out.append(item)

    return out

def balance_sources(events):
    grouped = {}
    for item in events:
        source = textify(item.get("source_name") or item.get("source") or "unknown")
        grouped.setdefault(source, []).append(item)

    for source_items in grouped.values():
        source_items.sort(key=lambda x: (
            not bool(x.get("priority_location")),
            -int(x.get("score", 0)),
            x.get("date", ""),
            x.get("title", "").lower(),
        ))

    out = []
    used = {k: 0 for k in grouped}
    keys = sorted(grouped.keys())

    while True:
        added = False
        for key in keys:
            if used[key] >= MAX_RESULTS_PER_SOURCE:
                continue
            items = grouped[key]
            if used[key] >= len(items):
                continue
            out.append(items[used[key]])
            used[key] += 1
            added = True
        if not added:
            break

    return out

def balance_sources(events):
    grouped = {}
    for item in events:
        source = textify(item.get("source_name") or item.get("source") or "unknown")
        grouped.setdefault(source, []).append(item)

    for source_items in grouped.values():
        source_items.sort(key=lambda x: (
            not bool(x.get("priority_location")),
            -int(x.get("score", 0)),
            x.get("date", ""),
            x.get("title", "").lower(),
        ))

    out = []
    used = {k: 0 for k in grouped}
    keys = sorted(grouped.keys())

    while True:
        added = False
        for key in keys:
            if used[key] >= MAX_RESULTS_PER_SOURCE:
                continue
            items = grouped[key]
            if used[key] >= len(items):
                continue
            out.append(items[used[key]])
            used[key] += 1
            added = True
        if not added:
            break

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

    events.sort(key=lambda x: (
        not bool(x.get("priority_location")),
        -int(x.get("score", 0)),
        x.get("when", ""),
        x.get("source_name", ""),
        x.get("title", "").lower(),
    ))

    events = balance_sources(events)

    return events[:80], sources, debug

def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events, sources, debug = collect(location)

    payload = {
        "version": 4,
        "ok": True,
        "extractor": "official-site-crawler-source-registry",
        "updated_at": now_iso(),
        "location": location,
        "count": len(events),
        "results": events,
        "items": events,
        "sources": sources,
        "debug_by_source": debug,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")

if __name__ == "__main__":
    main()
