#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
DEFAULT_LOCATION = "Punggol Singapore"
TODAY = date.today()
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "85"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "22"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "6"))
MAX_TOTAL_EVENTS = int(os.environ.get("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "60"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
SCRIPT_STYLE_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
JSON_URL_RE = re.compile(r'["\'](?:href|url|link|path|slug)["\']\s*:\s*["\']([^"\']+)["\']', re.I)
HTML_HREF_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', re.I)
DATE_RE = re.compile(
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(?:-|to|–|—|until|till)?\s*\d{0,2}\s*(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)?[a-z]*\s*\d{0,4}\b|"
    r"\b\d{1,2}\s*(?:-|to|–|—|until|till)\s*\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*\d{0,4}\b|"
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+\d{1,2},?\s*\d{0,4}\b",
    re.I,
)
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
EVENT_MARKERS = (
    "event", "programme", "program", "workshop", "activity", "course", "class", "club",
    "session", "talk", "tour", "storytelling", "storytime", "festival", "performance",
    "concert", "carnival", "reading", "exhibition", "show", "camp", "walk", "trail",
    "experience", "drop-in", "holiday", "screening", "guided", "open house",
)
EVENT_MARKER_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in EVENT_MARKERS) + r")\b", re.I)
LOCAL_PRIORITY_TERMS = ("punggol", "waterway", "one punggol", "punggol regional library", "safra punggol")
KNOWN_VENUES = (
    "Children's Museum Singapore", "National Gallery Singapore", "National Museum Singapore",
    "Asian Civilisations Museum", "Peranakan Museum", "ArtScience Museum",
    "Science Centre Singapore", "KidsSTOP", "Punggol Regional Library", "One Punggol",
    "Waterway Point", "SAFRA Punggol", "SAFRA Choa Chu Kang", "SAFRA Toa Payoh",
    "SAFRA Tampines", "SAFRA Mount Faber", "SAFRA Yishun", "SAFRA Jurong",
)

SOURCES = [
    {"name": "Children's Museum Singapore", "source": "Children's Museum Singapore", "default_venue": "Children's Museum Singapore", "domains": ["heritage.sg"], "seeds": ["https://www.heritage.sg/childrensmuseum/whatson"], "frontier_paths": ["/childrensmuseum/whatson"], "detail_prefixes": ["/childrensmuseum/whatson/"]},
    {"name": "National Gallery Singapore", "source": "National Gallery Singapore", "default_venue": "National Gallery Singapore", "domains": ["nationalgallery.sg"], "seeds": ["https://www.nationalgallery.sg/sg/en/whats-on.html"], "frontier_paths": ["/sg/en/whats-on.html", "/whats-on"], "detail_prefixes": ["/sg/en/whats-on/"]},
    {"name": "National Museum Singapore", "source": "National Museum Singapore", "default_venue": "National Museum Singapore", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/nationalmuseum/whats-on"], "frontier_paths": ["/nationalmuseum/whats-on"], "detail_prefixes": ["/nationalmuseum/whats-on/"]},
    {"name": "Asian Civilisations Museum", "source": "Asian Civilisations Museum", "default_venue": "Asian Civilisations Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/acm/whats-on"], "frontier_paths": ["/acm/whats-on", "/acm/whatson"], "detail_prefixes": ["/acm/whats-on/", "/acm/whatson/"]},
    {"name": "Peranakan Museum", "source": "Peranakan Museum", "default_venue": "Peranakan Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/peranakanmuseum/whats-on"], "frontier_paths": ["/peranakanmuseum/whats-on"], "detail_prefixes": ["/peranakanmuseum/whats-on/"]},
    {"name": "ArtScience Museum", "source": "ArtScience Museum", "default_venue": "ArtScience Museum", "domains": ["marinabaysands.com"], "seeds": ["https://www.marinabaysands.com/museum/events.html", "https://www.marinabaysands.com/museum/exhibitions.html"], "frontier_paths": ["/museum/events.html", "/museum/exhibitions.html"], "detail_prefixes": ["/museum/events/", "/museum/exhibitions/"]},
    {"name": "Science Centre Singapore", "source": "Science Centre Singapore", "default_venue": "Science Centre Singapore", "domains": ["science.edu.sg"], "seeds": ["https://www.science.edu.sg/whats-on"], "frontier_paths": ["/whats-on"], "detail_prefixes": ["/whats-on/"]},
    {"name": "NLB", "source": "NLB", "default_venue": "NLB", "domains": ["nlb.gov.sg"], "seeds": ["https://www.nlb.gov.sg/main/whats-on"], "frontier_paths": ["/main/whats-on"], "detail_prefixes": ["/main/whats-on/"]},
    {"name": "One Punggol", "source": "One Punggol", "default_venue": "One Punggol", "domains": ["onepunggol.sg"], "seeds": ["https://www.onepunggol.sg/events", "https://www.onepunggol.sg/happenings"], "frontier_paths": ["/events", "/happenings"], "detail_prefixes": ["/events/", "/happenings/"]},
    {"name": "onePA", "source": "onePA", "default_venue": "onePA", "domains": ["onepa.gov.sg"], "seeds": ["https://www.onepa.gov.sg/events", "https://www.onepa.gov.sg/courses"], "frontier_paths": ["/events", "/courses"], "detail_prefixes": ["/events/", "/courses/"]},
    {"name": "SAFRA", "source": "SAFRA", "default_venue": "SAFRA", "domains": ["safra.sg"], "seeds": ["https://www.safra.sg/whats-on"], "frontier_paths": ["/whats-on"], "detail_prefixes": ["/whats-on/"]},
    {"name": "Waterway Point", "source": "Waterway Point", "default_venue": "Waterway Point", "domains": ["waterwaypoint.com.sg"], "seeds": ["https://www.waterwaypoint.com.sg/happenings"], "frontier_paths": ["/happenings"], "detail_prefixes": ["/happenings/"]},
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(value, limit):
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_url(url, base=""):
    raw = html.unescape(str(url or "")).strip()
    raw = raw.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    if base:
        raw = urljoin(base, raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urllib.parse.urlencode(query), parsed.fragment))


def url_key(url):
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, parsed.fragment)).lower()


def host(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def same_domain(url, domains):
    h = host(url)
    return bool(h) and any(h.endswith(domain) for domain in domains)


def path_norm(url):
    return urlparse(url).path.lower().rstrip("/") or "/"


def source_frontier_page(source, url):
    parsed = urlparse(url)
    if parsed.query or parsed.fragment:
        return False
    path = path_norm(url)
    return path in {item.rstrip("/").lower() for item in source.get("frontier_paths", [])}


def source_detail_route(source, url):
    path = path_norm(url) + "/"
    if any(path.startswith(prefix.lower()) for prefix in source.get("detail_prefixes", [])):
        return not source_frontier_page(source, url)
    return False


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(1_800_000)
        match = re.search(r"charset=([\w.-]+)", response.headers.get("Content-Type", ""), re.I)
        return raw.decode(match.group(1) if match else "utf-8", "replace")


def meta_content(page, names):
    for name in names:
        escaped = re.escape(name)
        patterns = (
            rf'<meta[^>]+(?:name|property)=["\']{escaped}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{escaped}["\']',
        )
        for pattern in patterns:
            match = re.search(pattern, page, re.I | re.S)
            if match and clean(match.group(1)):
                return clean(match.group(1))
    return ""


def page_title(page, fallback=""):
    candidates = [meta_content(page, ["og:title", "twitter:title"])]
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page, re.I)
    if h1:
        candidates.append(clean(h1.group(1)))
    title = re.search(r"<title[^>]*>([\s\S]*?)</title>", page, re.I)
    if title:
        candidates.append(clean(title.group(1)))
    candidates.append(fallback)
    for item in candidates:
        value = clean(item)
        if value and TEMPLATE_RE.search(value) is None:
            return value
    return ""


def page_summary(page):
    return shorten(meta_content(page, ["og:description", "description", "twitter:description"]), 260) or "Open the official page for details."


def parse_one(day, month, year=""):
    month_num = MONTHS.get(month.lower()[:3])
    if not month_num:
        return None
    y = int(year) if year else TODAY.year
    try:
        parsed = date(y, month_num, int(day))
    except ValueError:
        return None
    if not year and parsed < TODAY - timedelta(days=30):
        parsed = date(TODAY.year + 1, parsed.month, parsed.day)
    return parsed


def parse_dates(label):
    text = clean(label).lower()
    out = []
    for match in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text):
        try:
            out.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            pass
    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        year = int(match.group(3))
        if year < 100:
            year += 2000
        try:
            out.append(date(year, int(match.group(2)), int(match.group(1))))
        except ValueError:
            pass
    for match in re.finditer(r"\b(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(?:-|to|–|—|until|till)\s*(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(\d{4})?", text, re.I):
        for parsed in (parse_one(match.group(1), match.group(2), match.group(5) or ""), parse_one(match.group(3), match.group(4), match.group(5) or "")):
            if parsed:
                out.append(parsed)
    for match in re.finditer(r"\b(\d{1,2})\s*(?:-|to|–|—|until|till)\s*(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(\d{4})?", text, re.I):
        for parsed in (parse_one(match.group(1), match.group(3), match.group(4) or ""), parse_one(match.group(2), match.group(3), match.group(4) or "")):
            if parsed:
                out.append(parsed)
    for match in re.finditer(r"\b(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(\d{4})?", text, re.I):
        parsed = parse_one(match.group(1), match.group(2), match.group(3) or "")
        if parsed:
            out.append(parsed)
    for match in re.finditer(r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+(\d{1,2}),?\s*(\d{4})?", text, re.I):
        parsed = parse_one(match.group(2), match.group(1), match.group(3) or "")
        if parsed:
            out.append(parsed)
    seen, uniq = set(), []
    for parsed in out:
        key = parsed.isoformat()
        if key not in seen:
            seen.add(key)
            uniq.append(parsed)
    return uniq


def sessions_from_label(label, url):
    dates = parse_dates(label)
    if not dates or max(dates) < TODAY - timedelta(days=PAST_GRACE_DAYS):
        return []
    label = clean(label)
    return [{"date": label, "when": label, "label": label, "url": url, "start_date": min(dates).isoformat(), "end_date": max(dates).isoformat()}]


def sessions_from_text(text, url):
    sessions, seen = [], set()
    for match in DATE_RE.finditer(text):
        label = clean(match.group(0))
        found = sessions_from_label(label, url)
        if not found:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        sessions.extend(found)
        if len(sessions) >= 8:
            break
    sessions.sort(key=lambda item: item.get("start_date", "9999-12-31"))
    return sessions


def summarize_sessions(sessions):
    labels, seen = [], set()
    for session in sessions:
        label = clean(session.get("date") or session.get("when") or session.get("label"))
        if label and label.lower() not in seen:
            seen.add(label.lower())
            labels.append(label)
    if len(labels) <= 1:
        return labels[0] if labels else "Check official page"
    shown = " / ".join(labels[:4])
    if len(labels) > 4:
        shown += f" / +{len(labels) - 4} more"
    return f"{len(labels)} sessions: {shown}"


def jsonld_objects(page):
    objects = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', page, re.I):
        try:
            data = json.loads(html.unescape(match.group(1)).strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                objects.append(item)
                stack.extend(value for value in item.values() if isinstance(value, (dict, list)))
    return objects


def json_type_is_event(value):
    types = value if isinstance(value, list) else [value]
    return any(str(item).lower() == "event" for item in types)


def location_name(value):
    if isinstance(value, dict):
        name = clean(value.get("name"))
        if name:
            return name
        address = value.get("address")
        if isinstance(address, dict):
            parts = [clean(address.get(key)) for key in ("name", "streetAddress", "addressLocality")]
            return ", ".join(part for part in parts if part)
        return clean(address)
    return clean(value)


def known_venue(text):
    blob = clean(text).lower()
    for venue in KNOWN_VENUES:
        if venue.lower() in blob:
            return venue
    return ""


def local_priority(title, summary, venue, url, location):
    blob = f"{title} {summary} {venue} {url}".lower().replace("-", " ")
    query_terms = [word for word in re.split(r"\W+", location.lower()) if len(word) >= 4]
    hit = any(term in blob for term in LOCAL_PRIORITY_TERMS) or any(term in blob for term in query_terms)
    return (25 if hit else 0), hit


def valid_unstructured_event(title, url, page_text):
    if TEMPLATE_RE.search(str(title or "")):
        return False
    title = clean(title)
    if len(re.findall(r"[A-Za-z0-9]", title)) < 6:
        return False
    # For pages without schema.org Event, require positive event semantics from the title or the page route.
    return EVENT_MARKER_RE.search(title) is not None or source_route_looks_eventful(url, page_text)


def source_route_looks_eventful(url, page_text):
    route = path_norm(url).replace("-", " ").replace("_", " ")
    return EVENT_MARKER_RE.search(route) is not None and EVENT_MARKER_RE.search(clean(page_text[:2000])) is not None


def make_event(source, url, title, summary, sessions, location, score, venue="", structured=False, page_text=""):
    url = normalize_url(url)
    title = clean(title)
    summary = clean(summary) if summary else "Open the official page for details."
    venue = clean(venue) or known_venue(f"{title} {summary} {page_text[:8000]}") or source.get("default_venue", source["name"])
    if not url or source_frontier_page(source, url) or not sessions:
        return None
    if structured is False and not valid_unstructured_event(title, url, page_text):
        return None
    boost, priority = local_priority(title, summary, venue, url, location)
    when = summarize_sessions(sessions)
    return {
        "type": "event",
        "title": shorten(title, 150),
        "poster_title": shorten(title, 150),
        "what": shorten(title, 150),
        "when": when,
        "date": when,
        "sessions": sessions,
        "session_count": len(sessions),
        "where": venue,
        "venue": venue,
        "who": source["source"],
        "organizer": source["source"],
        "why": shorten(summary, 260),
        "description": shorten(summary, 260),
        "how": "Official page",
        "summary": shorten(summary, 260),
        "poster_summary": shorten(summary, 220),
        "source": source["source"],
        "source_name": source["name"],
        "url": url,
        "score": score + boost + min(len(sessions), 4),
        "priority_location": priority,
    }


def structured_events(source, page_url, page, location):
    events = []
    for obj in jsonld_objects(page):
        if not json_type_is_event(obj.get("@type") or obj.get("type")):
            continue
        url = normalize_url(obj.get("url") or page_url, page_url)
        if not url or not same_domain(url, source["domains"]):
            continue
        title = clean(obj.get("name") or obj.get("headline"))
        summary = clean(obj.get("description")) or page_summary(page)
        sessions = []
        if obj.get("startDate") or obj.get("endDate"):
            label = " - ".join(clean(x)[:10] for x in (obj.get("startDate"), obj.get("endDate")) if clean(x))
            sessions = sessions_from_label(label, url)
        if not sessions:
            sessions = sessions_from_text(" ".join([title, summary, clean(page[:120000])]), url)
        venue = location_name(obj.get("location")) or known_venue(f"{title} {summary} {clean(page[:30000])}")
        item = make_event(source, url, title, summary, sessions, location, 100, venue, structured=True, page_text=clean(page[:20000]))
        if item:
            events.append(item)
    return events


def analyze_page(source, url, page, location):
    if source_frontier_page(source, url):
        return []
    structured = structured_events(source, url, page, location)
    if structured:
        return structured
    title = page_title(page, "")
    summary = page_summary(page)
    body = clean(page[:120000])
    sessions = sessions_from_text(" ".join([title, summary, body]), url)
    venue = known_venue(" ".join([title, summary, body[:30000]])) or source.get("default_venue", source["name"])
    item = make_event(source, url, title, summary, sessions, location, 70, venue, structured=False, page_text=body)
    return [item] if item else []


def link_score(source, base_url, url, label, context):
    url = normalize_url(url, base_url)
    if not url or not same_domain(url, source["domains"]):
        return -999
    route = path_norm(url).replace("-", " ").replace("_", " ")
    text = clean(f"{label} {context[:1500]}")
    score = 0
    if source_frontier_page(source, url):
        score += 25
    if source_detail_route(source, url):
        score += 60
    if EVENT_MARKER_RE.search(route):
        score += 25
    if EVENT_MARKER_RE.search(text):
        score += 15
    if DATE_RE.search(text):
        score += 15
    if any(term in f"{route} {text}".lower() for term in LOCAL_PRIORITY_TERMS):
        score += 10
    if url_key(url) == url_key(base_url):
        score -= 30
    return score


def page_url_candidates(page):
    out = []
    for match in JSON_URL_RE.finditer(page):
        raw = match.group(1).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
        if raw.startswith("http") or raw.startswith("/"):
            out.append(raw)
    for match in re.finditer(r'/(?:acm|nationalmuseum|peranakanmuseum|childrensmuseum|main|museum)/(?:what(?:s-on|son)|events|happenings|activities|programmes|courses)/[^"\'<>\\\s]+', page, re.I):
        out.append(match.group(0).replace("\\/", "/"))
    return out


def discover_links(source, page, base_url):
    found = {}

    def add(raw_url, label, context, extra=0):
        url = normalize_url(raw_url, base_url)
        score = link_score(source, base_url, url, label, context) + extra
        if score < 20:
            return
        key = url_key(url)
        if score > found.get(key, (-999, ""))[0]:
            found[key] = (score, url)

    for match in HTML_HREF_RE.finditer(page):
        context = page[max(0, match.start() - 700): min(len(page), match.end() + 1000)]
        add(match.group(1), match.group(2), context)
    for raw in page_url_candidates(page):
        add(raw, raw, page[:3000], extra=8)
    return sorted(found.values(), key=lambda item: -item[0])[:80]


def crawl_source(source, location, deadline):
    queue, events = [], []
    queued, fetched = set(), set()
    fetched_preview, rejected_preview, discovered_preview = [], [], []

    def push(url, score):
        url = normalize_url(url)
        key = url_key(url)
        if not url or key in queued or key in fetched or not same_domain(url, source["domains"]):
            return
        queued.add(key)
        queue.append((score, url))
        if len(discovered_preview) < 12:
            discovered_preview.append({"score": score, "url": url})

    for seed in source.get("seeds", []):
        push(seed, 90)

    while queue and len(fetched) < MAX_PAGES_PER_SOURCE and len(events) < MAX_EVENTS_PER_SOURCE and time.monotonic() < deadline:
        queue.sort(key=lambda item: -item[0])
        _score, url = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)
        try:
            page = fetch(url)
        except Exception as exc:
            rejected_preview.append({"url": url, "reason": f"fetch_failed:{type(exc).__name__}"})
            continue
        fetched_preview.append({"url": url, "title": shorten(page_title(page, url), 90), "frontier": source_frontier_page(source, url)})
        events.extend(analyze_page(source, url, page, location))
        for score, link in discover_links(source, page, url):
            push(link, score)

    return {"events": events, "debug": {"source": source["name"], "pages_fetched": len(fetched), "queue_seen": len(queued), "accepted": len(events), "discovered_preview": discovered_preview, "fetched_preview": fetched_preview[:10], "accepted_preview": [{"title": item.get("title"), "when": item.get("when"), "where": item.get("where"), "url": item.get("url")} for item in events[:8]], "rejected_preview": rejected_preview[:8]}}


def event_key(item):
    return "::".join([clean(item.get("source_name")).lower(), clean(item.get("venue")).lower(), clean(item.get("title")).lower()])


def dedupe_events(events):
    grouped = {}
    for item in events:
        if not item.get("sessions") or not clean(item.get("title")):
            continue
        key = event_key(item)
        if key not in grouped or int(item.get("score", 0)) > int(grouped[key].get("score", 0)):
            grouped[key] = item
    out = list(grouped.values())
    used_urls = {}
    for idx, item in enumerate(out, 1):
        url = item.get("url") or ""
        key = url.lower()
        used_urls[key] = used_urls.get(key, 0) + 1
        if used_urls[key] > 1:
            parsed = urlparse(url)
            item["url"] = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, f"event-{idx}"))
    return out


def collect(location):
    deadline = time.monotonic() + MAX_SECONDS
    events, debug = [], []
    for source in SOURCES:
        if time.monotonic() >= deadline:
            break
        result = crawl_source(source, location, deadline)
        events.extend(result["events"])
        debug.append(result["debug"])
    events = dedupe_events(events)
    events.sort(key=lambda item: (not bool(item.get("priority_location")), -int(item.get("score", 0)), item.get("date", ""), item.get("source_name", ""), clean(item.get("title")).lower()))
    events = events[:MAX_TOTAL_EVENTS]
    sources = [{"type": "source", "title": source["name"], "url": source["seeds"][0], "source": source["source"], "venue": source.get("default_venue", source["name"])} for source in SOURCES]
    return events, sources, debug


def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events, sources, debug = collect(location)
    payload = {"version": 17, "ok": True, "extractor": "positive-evidence-event-crawler-v17", "updated_at": now_iso(), "location": location, "count": len(events), "results": events, "items": events, "sources": sources, "debug_by_source": debug, "settings": {"acceptance": "positive_event_evidence_only", "local_terms_are_priority_not_filter": True, "source_is_institution_not_fixed_venue": True, "listing_pages_are_frontier_only": True}}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")


if __name__ == "__main__":
    main()
