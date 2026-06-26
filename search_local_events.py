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
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "20"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "6"))
MAX_TOTAL_EVENTS = int(os.environ.get("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "60"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
SCRIPT_STYLE_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
BROKEN_ATTR_RE = re.compile(r"\b(?:hPriority|decoding|loading|alt|src|srcset|width|height|class|style|href|aria-[\w-]+|data-[\w-]+)=[\"'][^\"']*[\"']\s*/?", re.I)
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
EVENT_TERMS = (
    "event", "programme", "program", "workshop", "activity", "course", "class",
    "club", "session", "talk", "tour", "story", "storytelling", "storytime",
    "family", "children", "kids", "festival", "performance", "concert", "carnival",
    "reading", "exhibition", "show", "camp", "walk", "trail", "experience",
    "drop-in", "holiday", "screening", "guided", "open house",
)
EVENT_TERM_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in EVENT_TERMS) + r")\b", re.I)
ACTION_TITLE_RE = re.compile(r"^(register|registration|book|booking|ticket|tickets|details|learn more|find out more|read more|view more|view all|open|share)$", re.I)
BAD_TITLE_PREFIX_RE = re.compile(r"^(about|visit|address|opening hours|operating hours|get(?:ting)? here|directions|contact|facilities|amenities|parking)\b", re.I)
GENERIC_TITLES = {
    "events", "event", "what s on", "whats on", "activities", "activities and events",
    "things to do", "programmes", "programs", "home", "homepage", "visit us",
    "contact us", "about us", "all events", "view all", "address", "opening hours",
    "operating hours", "location", "directions", "getting here", "facilities",
}
INFO_WORDS = (
    "address", "opening hours", "operating hours", "closed for disinfection", "last entry",
    "directions", "getting here", "visit us", "facilities", "amenities", "parking",
    "contact us", "admission",
)
BAD_PATH_PARTS = (
    "/privacy", "/terms", "/contact", "/about", "/career", "/login", "/directions",
    "/parking", "/getting-here", "/visit-us", "/address", "/opening-hours",
)
BAD_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf",
    ".zip", ".mp4", ".mp3", ".css", ".js", ".woff", ".woff2",
)
CONTAINER_EXACT = {
    "/events", "/event", "/happenings", "/whats-on", "/whatson", "/activities",
    "/things-to-do", "/programmes", "/programs", "/courses", "/course",
}
CONTAINER_FILES = {"whats-on.html", "events.html", "happenings.html", "activities.html"}
LOCAL_PRIORITY_TERMS = ("punggol", "waterway", "one punggol", "punggol regional library", "safra punggol")
VENUES = [
    "Children's Museum Singapore", "National Gallery Singapore", "National Museum Singapore",
    "Asian Civilisations Museum", "Peranakan Museum", "ArtScience Museum",
    "Science Centre Singapore", "KidsSTOP", "Punggol Regional Library", "One Punggol",
    "Waterway Point", "SAFRA Punggol", "SAFRA Choa Chu Kang", "SAFRA Toa Payoh",
    "SAFRA Tampines", "SAFRA Mount Faber", "SAFRA Yishun", "SAFRA Jurong",
    "Choa Chu Kang Public Library", "Tampines Regional Library", "Jurong Regional Library",
    "Woodlands Regional Library", "Sengkang Public Library",
]
VENUE_ONLY_KEYS = {re.sub(r"[^a-z0-9]+", " ", v.lower()).strip() for v in VENUES}

SOURCES = [
    {"name": "Children's Museum Singapore", "source": "Children's Museum Singapore", "default_venue": "Children's Museum Singapore", "domains": ["heritage.sg"], "seeds": ["https://www.heritage.sg/childrensmuseum/whatson"], "event_prefixes": ["/childrensmuseum/whatson/"], "container_paths": ["/childrensmuseum/whatson"]},
    {"name": "National Gallery Singapore", "source": "National Gallery Singapore", "default_venue": "National Gallery Singapore", "domains": ["nationalgallery.sg"], "seeds": ["https://www.nationalgallery.sg/sg/en/whats-on.html"], "event_prefixes": ["/sg/en/whats-on/"], "container_paths": ["/sg/en/whats-on.html", "/whats-on"]},
    {"name": "National Museum Singapore", "source": "National Museum Singapore", "default_venue": "National Museum Singapore", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/nationalmuseum/whats-on"], "event_prefixes": ["/nationalmuseum/whats-on/"], "container_paths": ["/nationalmuseum/whats-on"]},
    {"name": "Asian Civilisations Museum", "source": "Asian Civilisations Museum", "default_venue": "Asian Civilisations Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/acm/whats-on"], "event_prefixes": ["/acm/whats-on/", "/acm/whatson/"], "container_paths": ["/acm/whats-on", "/acm/whatson"]},
    {"name": "Peranakan Museum", "source": "Peranakan Museum", "default_venue": "Peranakan Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/peranakanmuseum/whats-on"], "event_prefixes": ["/peranakanmuseum/whats-on/"], "container_paths": ["/peranakanmuseum/whats-on"]},
    {"name": "ArtScience Museum", "source": "ArtScience Museum", "default_venue": "ArtScience Museum", "domains": ["marinabaysands.com"], "seeds": ["https://www.marinabaysands.com/museum/events.html", "https://www.marinabaysands.com/museum/exhibitions.html"], "event_prefixes": ["/museum/events/", "/museum/exhibitions/"], "container_paths": ["/museum/events.html", "/museum/exhibitions.html"]},
    {"name": "Science Centre Singapore", "source": "Science Centre Singapore", "default_venue": "Science Centre Singapore", "domains": ["science.edu.sg"], "seeds": ["https://www.science.edu.sg/whats-on"], "event_prefixes": ["/whats-on/"], "container_paths": ["/whats-on"]},
    {"name": "NLB", "source": "NLB", "default_venue": "NLB", "domains": ["nlb.gov.sg"], "seeds": ["https://www.nlb.gov.sg/main/whats-on"], "event_prefixes": ["/main/whats-on/"], "container_paths": ["/main/whats-on"]},
    {"name": "One Punggol", "source": "One Punggol", "default_venue": "One Punggol", "domains": ["onepunggol.sg"], "seeds": ["https://www.onepunggol.sg/events", "https://www.onepunggol.sg/happenings"], "event_prefixes": ["/events/", "/happenings/"], "container_paths": ["/events", "/happenings"]},
    {"name": "onePA", "source": "onePA", "default_venue": "onePA", "domains": ["onepa.gov.sg"], "seeds": ["https://www.onepa.gov.sg/events", "https://www.onepa.gov.sg/courses"], "event_prefixes": ["/events/", "/courses/"], "container_paths": ["/events", "/courses"]},
    {"name": "SAFRA", "source": "SAFRA", "default_venue": "SAFRA", "domains": ["safra.sg"], "seeds": ["https://www.safra.sg/whats-on"], "event_prefixes": ["/whats-on/"], "container_paths": ["/whats-on"]},
    {"name": "Waterway Point", "source": "Waterway Point", "default_venue": "Waterway Point", "domains": ["waterwaypoint.com.sg"], "seeds": ["https://www.waterwaypoint.com.sg/happenings"], "event_prefixes": ["/happenings/"], "container_paths": ["/happenings"]},
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/")
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = BROKEN_ATTR_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical(value):
    text = DATE_RE.sub(" ", clean(value).lower())
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(value, limit):
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_url(url, base=""):
    raw = html.unescape(str(url or "")).strip().replace("\\/", "/")
    raw = raw.replace("\\u002F", "/").replace("\\u002f", "/")
    if base:
        raw = urljoin(base, raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urllib.parse.urlencode(query), parsed.fragment))


def url_key(url):
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, parsed.fragment)).lower()


def host(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def same_domain(url, domains):
    h = host(url)
    return bool(h) and any(h.endswith(d) for d in domains)


def path_norm(url):
    path = urlparse(url).path.lower().rstrip("/")
    return path or "/"


def source_container(source, url):
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/") or "/"
    if parsed.query or parsed.fragment:
        return False
    filename = path.rsplit("/", 1)[-1]
    if path in CONTAINER_EXACT or filename in CONTAINER_FILES:
        return True
    return path in {p.lower().rstrip("/") for p in source.get("container_paths", [])}


def source_detail_signal(source, url):
    if source_container(source, url):
        return False
    path = path_norm(url) + "/"
    if any(path.startswith(prefix.lower()) for prefix in source.get("event_prefixes", [])):
        return True
    if urlparse(url).query and any(path_norm(url) == p.lower().rstrip("/") for p in source.get("container_paths", [])):
        return True
    return any(root in path for root in ("/events/", "/event/", "/happenings/", "/whats-on/", "/whatson/", "/activities/", "/activity/", "/programmes/", "/programs/", "/courses/", "/course/"))


def bad_url(url):
    path = path_norm(url)
    return any(path.endswith(ext) for ext in BAD_EXT) or any(part in path for part in BAD_PATH_PARTS)


def info_text(value):
    text = clean(value).lower()
    return any(word in text for word in INFO_WORDS) or "hpriority" in text or "decoding=" in text


def title_is_bad(title):
    title = clean(title)
    key = canonical(title)
    return (
        not title
        or key in GENERIC_TITLES
        or key in VENUE_ONLY_KEYS
        or BAD_TITLE_PREFIX_RE.search(title) is not None
        or ACTION_TITLE_RE.match(title.strip()) is not None
        or info_text(title)
        or TEMPLATE_RE.search(title) is not None
    )


def has_event_term(text):
    return EVENT_TERM_RE.search(clean(text)) is not None


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(1_800_000)
        match = re.search(r"charset=([\w.-]+)", response.headers.get("Content-Type", ""), re.I)
        return raw.decode(match.group(1) if match else "utf-8", "replace")


def meta_content(page, names):
    for name in names:
        escaped = re.escape(name)
        for pattern in (rf'<meta[^>]+(?:name|property)=["\']{escaped}["\'][^>]+content=["\']([^"\']+)["\']', rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{escaped}["\']'):
            match = re.search(pattern, page, re.I | re.S)
            if match and clean(match.group(1)):
                return clean(match.group(1))
    return ""


def page_title(page, fallback=""):
    values = [meta_content(page, ["og:title", "twitter:title"])]
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page, re.I)
    if h1:
        values.append(clean(h1.group(1)))
    title = re.search(r"<title[^>]*>([\s\S]*?)</title>", page, re.I)
    if title:
        values.append(clean(title.group(1)))
    values.append(fallback)
    for value in values:
        text = re.sub(r"\s*[|\-–]\s*(NLB|National Library Board|onePA|One Punggol|SAFRA|Singapore)\s*$", "", clean(value), flags=re.I)
        if text and TEMPLATE_RE.search(text) is None:
            return text
    return ""


def summary_from_detail(page):
    text = meta_content(page, ["og:description", "description", "twitter:description"])
    if text and not info_text(text):
        return shorten(text, 260)
    return "Open the official page for details."


def parse_single_date(day, month, year=""):
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
        for parsed in (parse_single_date(match.group(1), match.group(2), match.group(5) or ""), parse_single_date(match.group(3), match.group(4), match.group(5) or "")):
            if parsed:
                out.append(parsed)
    for match in re.finditer(r"\b(\d{1,2})\s*(?:-|to|–|—|until|till)\s*(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(\d{4})?", text, re.I):
        for parsed in (parse_single_date(match.group(1), match.group(3), match.group(4) or ""), parse_single_date(match.group(2), match.group(3), match.group(4) or "")):
            if parsed:
                out.append(parsed)
    for match in re.finditer(r"\b(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(\d{4})?", text, re.I):
        parsed = parse_single_date(match.group(1), match.group(2), match.group(3) or "")
        if parsed:
            out.append(parsed)
    for match in re.finditer(r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+(\d{1,2}),?\s*(\d{4})?", text, re.I):
        parsed = parse_single_date(match.group(2), match.group(1), match.group(3) or "")
        if parsed:
            out.append(parsed)
    seen, uniq = set(), []
    for parsed in out:
        key = parsed.isoformat()
        if key not in seen:
            seen.add(key)
            uniq.append(parsed)
    return uniq


def sessions_from_text(text, url):
    out, seen = [], set()
    for match in DATE_RE.finditer(text):
        label = clean(match.group(0))
        dates = parse_dates(label)
        if not dates or max(dates) < TODAY - timedelta(days=PAST_GRACE_DAYS):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": label, "when": label, "label": label, "url": url, "start_date": min(dates).isoformat(), "end_date": max(dates).isoformat()})
        if len(out) >= 8:
            break
    out.sort(key=lambda item: item.get("start_date", "9999-12-31"))
    return out


def sessions_from_structured(start, end, url):
    start_text = clean(start)[:10]
    end_text = clean(end)[:10]
    label = f"{start_text} - {end_text}" if start_text and end_text and start_text != end_text else start_text or end_text
    if not label:
        return []
    dates = parse_dates(label)
    if not dates or max(dates) < TODAY - timedelta(days=PAST_GRACE_DAYS):
        return []
    return [{"date": label, "when": label, "label": label, "url": url, "start_date": min(dates).isoformat(), "end_date": max(dates).isoformat()}]


def summarize_sessions(sessions):
    labels, seen = [], set()
    for session in sessions:
        label = clean(session.get("date") or session.get("when") or session.get("label"))
        if label and label.lower() not in seen:
            seen.add(label.lower())
            labels.append(label)
    if not labels:
        return "Check official page"
    if len(labels) == 1:
        return labels[0]
    shown = " / ".join(labels[:4])
    if len(labels) > 4:
        shown += f" / +{len(labels) - 4} more"
    return f"{len(labels)} sessions: {shown}"


def extract_known_venue(text):
    blob = clean(text).lower()
    for venue in VENUES:
        if venue.lower() in blob:
            return venue
    return ""


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
                stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
    return objects


def location_name(value):
    if isinstance(value, dict):
        name = clean(value.get("name"))
        if name:
            return name
        address = value.get("address")
        if isinstance(address, dict):
            for key in ("streetAddress", "addressLocality", "name"):
                found = clean(address.get(key))
                if found:
                    return found
        elif address:
            return clean(address)
    if isinstance(value, str):
        return clean(value)
    return ""


def local_priority_score(title, summary, venue, url, location):
    blob = f"{title} {summary} {venue} {url}".lower().replace("-", " ")
    query_terms = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    priority = any(term in blob for term in LOCAL_PRIORITY_TERMS) or any(term in blob for term in query_terms)
    return (25 if priority else 0), priority


def build_event(source, url, title, summary, sessions, location, score, venue=""):
    url = normalize_url(url)
    title = clean(title)
    summary = clean(summary) if summary else "Open the official page for details."
    venue = clean(venue) or extract_known_venue(f"{title} {summary}") or source.get("default_venue", source["name"])
    if not url or source_container(source, url) or bad_url(url) or not sessions or title_is_bad(title):
        return None
    if not source_detail_signal(source, url) and not has_event_term(f"{title} {summary}"):
        return None
    if info_text(summary) and summary != "Open the official page for details.":
        summary = "Open the official page for details."
    local_boost, priority = local_priority_score(title, summary, venue, url, location)
    when = summarize_sessions(sessions)
    return {"type": "event", "title": shorten(title, 150), "poster_title": shorten(title, 150), "what": shorten(title, 150), "when": when, "date": when, "sessions": sessions, "session_count": len(sessions), "where": venue, "venue": venue, "who": source["source"], "organizer": source["source"], "why": shorten(summary, 260), "description": shorten(summary, 260), "how": "Official page", "summary": shorten(summary, 260), "poster_summary": shorten(summary, 220), "source": source["source"], "source_name": source["name"], "url": url, "score": score + local_boost + min(len(sessions), 4), "priority_location": priority}


def structured_events(source, page_url, page, location):
    events = []
    for obj in jsonld_objects(page):
        raw_type = obj.get("@type") or obj.get("type") or ""
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(str(t).lower() == "event" for t in types):
            continue
        url = normalize_url(obj.get("url") or page_url, page_url)
        if not url or not same_domain(url, source["domains"]):
            continue
        title = clean(obj.get("name") or obj.get("headline"))
        summary = clean(obj.get("description")) or summary_from_detail(page)
        sessions = sessions_from_structured(obj.get("startDate") or obj.get("start_date"), obj.get("endDate") or obj.get("end_date"), url)
        if not sessions:
            sessions = sessions_from_text(" ".join([title, summary, clean(page[:120000])]), url)
        venue = location_name(obj.get("location")) or extract_known_venue(f"{title} {summary} {clean(page[:30000])}")
        item = build_event(source, url, title, summary, sessions, location, 100, venue)
        if item:
            events.append(item)
    return events


def analyze_detail_page(source, url, page, location):
    if source_container(source, url) or bad_url(url):
        return []
    events = structured_events(source, url, page, location)
    if events:
        return events
    title = page_title(page, "")
    summary = summary_from_detail(page)
    body = clean(page[:120000])
    sessions = sessions_from_text(" ".join([title, summary, body]), url)
    venue = extract_known_venue(" ".join([title, summary, body[:20000]])) or source.get("default_venue", source["name"])
    item = build_event(source, url, title, summary, sessions, location, 72, venue)
    return [item] if item else []


def link_candidate_score(source, base_url, url, anchor, context):
    if not url or bad_url(url) or not same_domain(url, source["domains"]):
        return -999
    anchor_text = clean(anchor)
    context_text = clean(context[:1500])
    path = path_norm(url)
    blob = f"{path} {anchor_text} {context_text}".lower()
    score = 0
    if source_container(source, url):
        score += 30
    if source_detail_signal(source, url):
        score += 55
    if has_event_term(f"{path} {anchor_text}"):
        score += 25
    if DATE_RE.search(context_text):
        score += 20
    if canonical(anchor_text) and canonical(anchor_text) not in GENERIC_TITLES and not ACTION_TITLE_RE.match(anchor_text):
        score += 10
    if any(term in blob for term in LOCAL_PRIORITY_TERMS):
        score += 10
    if info_text(anchor_text) or BAD_TITLE_PREFIX_RE.search(anchor_text or ""):
        score -= 50
    if url_key(url) == url_key(base_url):
        score -= 30
    return score


def json_link_candidates(page):
    candidates = []
    for pattern in (
        r'["\'](?:href|url|link|path|slug)["\']\s*:\s*["\']([^"\']+)["\']',
        r'(?:href|url|link|path|slug)=\\?["\']([^"\']+)\\?["\']',
    ):
        for match in re.finditer(pattern, page, re.I):
            raw = match.group(1).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
            if raw.startswith("http") or raw.startswith("/"):
                candidates.append(raw)
    for match in re.finditer(r'/(?:acm|nationalmuseum|peranakanmuseum|childrensmuseum|main|museum)/(?:what(?:s-on|son)|events|happenings|activities|programmes|courses)/[^"\'<>\\\s]+', page, re.I):
        candidates.append(match.group(0).replace("\\/", "/"))
    return candidates


def discover_links(source, page, base_url):
    found = {}

    def add(url, anchor, context, bonus=0):
        url = normalize_url(url, base_url)
        if not url:
            return
        score = link_candidate_score(source, base_url, url, anchor, context) + bonus
        if score < 20:
            return
        key = url_key(url)
        if score > found.get(key, (-999, ""))[0]:
            found[key] = (score, url)

    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', page, re.I):
        context = page[max(0, match.start() - 700): min(len(page), match.end() + 1000)]
        add(match.group(1), match.group(2), context)

    for raw in json_link_candidates(page):
        # JSON links do not carry anchor text, so rely on URL shape and nearby page text.
        add(raw, raw, page[:2500], bonus=8)

    return sorted(found.values(), key=lambda item: -item[0])[:80]


def crawl_source(source, location, deadline):
    queue, events, fetched_preview, rejected_preview = [], [], [], []
    queued, fetched = set(), set()

    def push(url, score):
        url = normalize_url(url)
        key = url_key(url)
        if not url or key in queued or key in fetched or not same_domain(url, source["domains"]) or bad_url(url):
            return
        queued.add(key)
        queue.append((score, url))

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
        fetched_preview.append({"url": url, "title": shorten(page_title(page, url), 90), "container": source_container(source, url)})
        events.extend(analyze_detail_page(source, url, page, location))
        for link_score, link in discover_links(source, page, url):
            push(link, link_score)

    return {"events": events, "debug": {"source": source["name"], "pages_fetched": len(fetched), "queue_seen": len(queued), "accepted": len(events), "fetched_preview": fetched_preview[:10], "accepted_preview": [{"title": item.get("title"), "when": item.get("when"), "where": item.get("where"), "url": item.get("url")} for item in events[:8]], "rejected_preview": rejected_preview[:8]}}


def event_key(item):
    return "::".join([clean(item.get("source_name")).lower(), clean(item.get("venue")).lower(), canonical(item.get("title"))])


def dedupe_events(events):
    grouped = {}
    for item in events:
        if not item.get("sessions") or title_is_bad(item.get("title")):
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
    payload = {"version": 16, "ok": True, "extractor": "institution-detail-crawler-v16", "updated_at": now_iso(), "location": location, "count": len(events), "results": events, "items": events, "sources": sources, "debug_by_source": debug, "settings": {"local_terms_are_priority_not_filter": True, "source_is_institution_not_fixed_venue": True, "emit_detail_pages_only": True, "discover_json_links": True, "reject_venue_only_titles": True}}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")


if __name__ == "__main__":
    main()
