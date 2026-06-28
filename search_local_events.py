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
OFFICIAL_REGISTRY = BASE / "official_source_registry.json"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
DEFAULT_LOCATION = "Punggol Singapore"
TODAY = date.today()

MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "85"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "30"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "8"))
MAX_TOTAL_EVENTS = int(os.environ.get("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "60"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
SCRIPT_STYLE_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
SCRIPT_JSON_RE = re.compile(r"<script[^>]+type=[\"']application/(?:ld\+)?json[\"'][^>]*>([\s\S]*?)</script>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HTML_HREF_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", re.I)
JSON_URL_RE = re.compile(r"[\"'](?:href|url|link|path|slug|canonicalUrl|pageUrl)[\"']\s*:\s*[\"']([^\"']+)[\"']", re.I)
RAW_PATH_RE = re.compile(r"/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?|things-to-do)/[^\"'<>\\\s]+", re.I)
ABS_URL_RE = re.compile(r"https?://[^\"'<>\\\s]+", re.I)
LOC_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.I)
SITEMAP_RE = re.compile(r"^\s*Sitemap:\s*(\S+)\s*$", re.I | re.M)

DATE_RE = re.compile(
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(?:-|to|–|—|until|till)?\s*\d{0,2}\s*(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)?[a-z]*\s*\d{0,4}\b|"
    r"\b\d{1,2}\s*(?:-|to|–|—|until|till)\s*\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*\d{0,4}\b|"
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+\d{1,2},?\s*\d{0,4}\b",
    re.I,
)
MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12}
EVENT_MARKERS = ("event", "programme", "program", "workshop", "activity", "course", "class", "session", "talk", "tour", "storytelling", "storytime", "festival", "performance", "concert", "carnival", "reading", "exhibition", "show", "camp", "walk", "trail", "experience", "drop-in", "holiday", "screening", "guided", "open house", "lecture")
EVENT_MARKER_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in EVENT_MARKERS) + r")\b", re.I)
LOCAL_PRIORITY_TERMS = ("punggol", "waterway", "one punggol", "punggol regional library", "safra punggol")
LISTING_ROUTE_RE = re.compile(r"/(?:whats-on|whatson|events?|overview|view-all|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?)/?$", re.I)
DETAIL_ROUTE_RE = re.compile(r"/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|happenings?|courses|workshops?)/.+", re.I)
LOCATION_KEY_RE = re.compile(r"\b(?:venue|location|where|place|gallery|room|level|floor)\b", re.I)
LOCATION_VALUE_RE = re.compile(r"\b(?:gallery|galleries|room|theatre|theater|hall|salon|concourse|foyer|atrium|lawn|level|floor|basement|museum|centre|center|library|zoo)\b", re.I)
LOCATION_LABEL_RE = re.compile(r"\b(?:venue|location|where|place)\s*[:\-–—]\s*([^\n|•<>]{2,140})", re.I)

COMMON_EVENT_ENTRY_PATHS = (
    "/whats-on", "/whats-on/", "/whats-on/overview", "/whats-on/view-all", "/whatson",
    "/events", "/events/", "/event", "/event/", "/exhibition", "/exhibition/", "/exhibitions", "/exhibitions/",
    "/programmes", "/programmes/", "/programs", "/programs/", "/activities", "/activities/",
    "/happenings", "/happenings/", "/courses", "/courses/", "/workshops", "/workshops/",
    "/en/whats-on", "/en/whats-on.html", "/en/events", "/en/events.html", "/en/exhibitions", "/en/exhibitions.html",
    "/en/things-to-do/whats-on.html", "/en/things-to-do/events.html", "/en/see-and-do/whats-on.html",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_keep_text(value):
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = TAG_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(value, limit):
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_url(url, base=""):
    raw = html.unescape(str(url or "")).strip()
    raw = raw.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    if raw.startswith("//"):
        raw = "https:" + raw
    if base:
        raw = urljoin(base, raw)
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", urllib.parse.urlencode(query), ""))


def url_key(url):
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, "")).lower()


def host(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def root_url(url):
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), "/", "", "", ""))


def same_domain(url, domains):
    h = host(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def fetch(url, timeout=10, max_bytes=2_500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(max_bytes)
        match = re.search(r"charset=([\w.-]+)", response.headers.get("Content-Type", ""), re.I)
        return raw.decode(match.group(1) if match else "utf-8", "replace")


def meta_content(page, names):
    for name in names:
        escaped = re.escape(name)
        patterns = (rf'<meta[^>]+(?:name|property)=["\']{escaped}["\'][^>]+content=["\']([^"\']+)["\']', rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{escaped}["\']')
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
        value = date(y, month_num, int(day))
    except ValueError:
        return None
    if not year and value < TODAY - timedelta(days=PAST_GRACE_DAYS):
        try:
            value = date(y + 1, month_num, int(day))
        except ValueError:
            return None
    return value


def label_to_dates(label):
    text = clean(label)
    dates = []
    for y, m, d in re.findall(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text):
        try:
            dates.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for d, m, y in re.findall(r"\b(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s*(20\d{2})?\b", text, re.I):
        parsed = parse_one(d, m, y)
        if parsed:
            dates.append(parsed)
    for m, d, y in re.findall(r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)[a-z]*\s+(\d{1,2}),?\s*(20\d{2})?\b", text, re.I):
        parsed = parse_one(d, m, y)
        if parsed:
            dates.append(parsed)
    return dates


def sessions_from_label(label):
    label = clean(label)
    if not label:
        return []
    dates = label_to_dates(label)
    if not dates:
        return []
    if max(dates) < TODAY - timedelta(days=PAST_GRACE_DAYS):
        return []
    return [{"label": label, "dates": sorted(set(dates))}]


def sessions_from_text(text, limit=10):
    sessions = []
    seen = set()
    for match in DATE_RE.finditer(clean(text)[:250000]):
        label = clean(match.group(0))
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        sessions.extend(sessions_from_label(label))
        if len(sessions) >= limit:
            break
    return sessions[:limit]


def session_labels(sessions):
    labels = []
    for item in sessions:
        label = item.get("label") or ""
        if label and label not in labels:
            labels.append(label)
    return labels


def best_date(sessions):
    dates = []
    for item in sessions:
        dates.extend(item.get("dates") or [])
    future = [d for d in dates if d >= TODAY - timedelta(days=PAST_GRACE_DAYS)]
    return min(future or dates) if dates else TODAY


def format_when(sessions):
    labels = session_labels(sessions)
    if not labels:
        return ""
    return " / ".join(labels[:4]) + (f" / +{len(labels) - 4} more" if len(labels) > 4 else "")


def load_json_objects(page):
    objects = []
    for match in SCRIPT_JSON_RE.finditer(page):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except Exception:
            pass
    return objects


def walk_json(value):
    stack = [value]
    while stack:
        item = stack.pop()
        yield item
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def event_type(value):
    raw = value.get("@type") or value.get("type") if isinstance(value, dict) else None
    items = raw if isinstance(raw, list) else [raw]
    return any(str(item).lower() == "event" for item in items)


def clean_location(value):
    text = clean_keep_text(value)
    text = re.sub(r"\b(?:venue|location|where|place)\b\s*[:\-–—]?\s*", "", text, flags=re.I).strip()
    text = re.split(r"\b(?:admission|ticket|tickets|date|time|opening hours|operating hours|about|description)\b", text, 1, flags=re.I)[0].strip(" |•,;:-–—")
    if not text or len(text) < 2 or len(text) > 140:
        return ""
    if re.search(r"https?://|@|\.(?:com|sg|org|net)\b", text, re.I):
        return ""
    if DATE_RE.search(text):
        return ""
    return shorten(text, 120)


def location_from_value(value):
    if isinstance(value, dict):
        loc = value.get("location")
        if isinstance(loc, str):
            return clean_location(loc)
        if isinstance(loc, dict):
            return clean_location(loc.get("name") or loc.get("address") or "")
    return ""


def json_location_candidates(page):
    candidates = []
    keys = ("venue", "venueName", "venueTitle", "eventVenue", "location", "locationName", "place", "placeName", "room", "gallery", "floor", "level")
    for obj in load_json_objects(page):
        for node in walk_json(obj):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                if key not in keys and not LOCATION_KEY_RE.search(str(key)):
                    continue
                if isinstance(value, str):
                    loc = clean_location(value)
                    if loc and (LOCATION_VALUE_RE.search(loc) or len(loc.split()) <= 8):
                        candidates.append(loc)
                elif isinstance(value, dict):
                    loc = clean_location(value.get("name") or value.get("title") or value.get("label") or value.get("address") or "")
                    if loc:
                        candidates.append(loc)
    out = []
    for item in candidates:
        if item not in out:
            out.append(item)
    return out


def labeled_location_candidates(page):
    candidates = []
    visible = clean_keep_text(SCRIPT_STYLE_RE.sub(" ", page[:250000]))
    for match in LOCATION_LABEL_RE.finditer(visible):
        loc = clean_location(match.group(1))
        if loc:
            candidates.append(loc)
    html_text = html.unescape(page[:250000]).replace("\\/", "/")
    for match in re.finditer(r">\s*(Venue|Location|Where|Place)\s*<([\s\S]{0,900})", html_text, re.I):
        tail = match.group(2)
        values = [clean_location(x) for x in re.findall(r">\s*([^<>]{2,160})\s*<", tail)]
        for value in values:
            if value and value.lower() not in {"venue", "location", "where", "place"}:
                candidates.append(value)
                break
    out = []
    for item in candidates:
        if item not in out:
            out.append(item)
    return out


def sessions_from_value(value):
    if not isinstance(value, dict):
        return []
    labels = []
    for key in ("startDate", "endDate", "doorTime", "datePublished"):
        raw = value.get(key)
        if raw:
            labels.append(str(raw))
    return sessions_from_text(" - ".join(labels), limit=3)


def source_venue_names(source):
    names = [source.get("default_venue") or source.get("name") or ""]
    names.extend(source.get("aliases") or [])
    for sub in source.get("official_subsites") or []:
        if isinstance(sub, dict) and sub.get("name"):
            names.append(sub["name"])
    return [clean(x) for x in names if clean(x)]


def extract_location(source, page, event_obj=None):
    if event_obj:
        loc = location_from_value(event_obj)
        if loc:
            return loc
    for loc in json_location_candidates(page) + labeled_location_candidates(page):
        low = loc.lower()
        if low not in {"venue", "location", "where", "place"}:
            return loc
    text = clean(page[:120000])
    for name in source_venue_names(source):
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.I):
            return name
    return source.get("default_venue") or source.get("name")


def route_looks_listing(url):
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/") or "/"
    if parsed.query and re.search(r"\b(category|filter|time|date|type|page)=", parsed.query, re.I):
        return True
    return bool(LISTING_ROUTE_RE.search(path))


def route_looks_event_detail(url):
    path = urlparse(url).path.lower().rstrip("/")
    return bool(DETAIL_ROUTE_RE.search(path)) and not route_looks_listing(url)


def valid_unstructured_event(title, url, page_text):
    if TEMPLATE_RE.search(str(title or "")):
        return False
    if len(re.sub(r"[^a-z0-9]+", "", str(title or "").lower())) < 6:
        return False
    if not route_looks_event_detail(url):
        return False
    if not sessions_from_text(page_text, limit=1):
        return False
    route_text = urllib.parse.unquote(urlparse(url).path.replace("-", " ").replace("_", " "))
    signal_text = f"{title} {route_text} {clean(page_text[:5000])}"
    return bool(EVENT_MARKER_RE.search(signal_text))


def make_event(source, url, title, sessions, page, event_obj=None, structured=False):
    if not title or not sessions:
        return None
    if max(d for s in sessions for d in s.get("dates", [])) < TODAY - timedelta(days=PAST_GRACE_DAYS):
        return None
    if not structured and not valid_unstructured_event(title, url, page):
        return None
    return {"title": shorten(title, 140), "when": format_when(sessions), "where": extract_location(source, page, event_obj), "host": source.get("source") or source.get("name"), "source_name": source.get("source") or source.get("name"), "url": url, "summary": page_summary(page), "start_date": best_date(sessions).isoformat(), "kind": "event", "source_type": "official_registry", "structured": bool(structured)}


def structured_events(source, url, page):
    events = []
    for obj in load_json_objects(page):
        for node in walk_json(obj):
            if isinstance(node, dict) and event_type(node):
                title = clean(node.get("name") or node.get("headline") or "")
                sessions = sessions_from_value(node)
                if not sessions:
                    sessions = sessions_from_text(" ".join(str(node.get(k) or "") for k in ("startDate", "endDate", "description")))
                event = make_event(source, url, title, sessions, page, node, structured=True)
                if event:
                    events.append(event)
    return events


def unstructured_event(source, url, page, fallback_title=""):
    title = page_title(page, fallback_title)
    sessions = sessions_from_text(page)
    event = make_event(source, url, title, sessions, page, structured=False)
    return [event] if event else []


def score_link(source, url, label, context):
    if not same_domain(url, source.get("domains") or []):
        return -999
    p = urlparse(url)
    route = urllib.parse.unquote((p.path + " " + p.query).lower().replace("-", " ").replace("_", " "))
    text = clean(f"{label} {context[:1800]}").lower()
    score = 0
    if route_looks_event_detail(url):
        score += 80
    if route_looks_listing(url):
        score += 45
    if EVENT_MARKER_RE.search(route):
        score += 20
    if EVENT_MARKER_RE.search(text):
        score += 20
    if DATE_RE.search(text):
        score += 20
    if any(term in text or term in route for term in LOCAL_PRIORITY_TERMS):
        score += 8
    if p.scheme not in ("http", "https"):
        score -= 100
    return score


def discover_links(source, page, base_url):
    found = {}
    def add(raw, label, context):
        url = normalize_url(raw, base_url)
        if not url:
            return
        score = score_link(source, url, label, context)
        if score < 35:
            return
        key = url_key(url)
        item = (score, url, clean(label)[:120])
        if key not in found or item[0] > found[key][0]:
            found[key] = item
    for match in HTML_HREF_RE.finditer(page):
        context = page[max(0, match.start() - 900): min(len(page), match.end() + 1400)]
        add(match.group(1), match.group(2), context)
    decoded = html.unescape(page).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    for match in JSON_URL_RE.finditer(decoded):
        context = decoded[max(0, match.start() - 700): min(len(decoded), match.end() + 1000)]
        add(match.group(1), match.group(1), context)
    for regex in (RAW_PATH_RE, ABS_URL_RE):
        for match in regex.finditer(decoded):
            context = decoded[max(0, match.start() - 700): min(len(decoded), match.end() + 1000)]
            add(match.group(0), match.group(0), context)
    return sorted(found.values(), key=lambda x: (-x[0], x[1]))


def analyze_page(source, url, page, location=DEFAULT_LOCATION, fallback_title=""):
    events = structured_events(source, url, page)
    if not events:
        events = unstructured_event(source, url, page, fallback_title)
    return events


def sitemap_urls_for_source(source):
    root = root_url(source["official_site"])
    urls = [urljoin(root, "/sitemap.xml"), urljoin(root, "/sitemap_index.xml")]
    try:
        robots = fetch(urljoin(root, "/robots.txt"), timeout=6, max_bytes=400000)
        urls.extend(normalize_url(x, root) for x in SITEMAP_RE.findall(robots))
    except Exception:
        pass
    out = []
    for url in urls:
        if url and same_domain(url, source.get("domains") or []) and url not in out:
            out.append(url)
    return out[:8]


def sitemap_event_links(source, deadline):
    found = {}
    pending = [(url, 0) for url in sitemap_urls_for_source(source)]
    seen = set()
    while pending and time.time() < deadline and len(seen) < 18 and len(found) < 80:
        url, depth = pending.pop(0)
        key = url_key(url)
        if key in seen:
            continue
        seen.add(key)
        try:
            xml = fetch(url, timeout=8, max_bytes=2_500_000)
        except Exception:
            continue
        for loc in LOC_RE.findall(xml):
            loc_url = normalize_url(loc, url)
            if not loc_url or not same_domain(loc_url, source.get("domains") or []):
                continue
            if (loc_url.lower().endswith(".xml") or "sitemap" in loc_url.lower()) and depth < 1:
                pending.append((loc_url, depth + 1))
                continue
            score = score_link(source, loc_url, loc_url, "")
            if score >= 35:
                found[url_key(loc_url)] = (score + 10, loc_url, "sitemap")
    return sorted(found.values(), key=lambda x: (-x[0], x[1]))


def common_entry_links(source):
    found = {}
    bases = [source.get("official_site")]
    bases.extend(sub.get("url") for sub in source.get("official_subsites") or [] if isinstance(sub, dict))
    roots = []
    for base in bases:
        base = normalize_url(base)
        if not base:
            continue
        root = root_url(base)
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        for path in COMMON_EVENT_ENTRY_PATHS:
            url = normalize_url(path, root)
            if not same_domain(url, source.get("domains") or []):
                continue
            score = score_link(source, url, path, "")
            if score >= 35:
                found[url_key(url)] = (score + 5, url, "common-entry")
    return sorted(found.values(), key=lambda x: (-x[0], x[1]))


def registry_source_from_entry(entry):
    name = clean(entry.get("name"))
    official_site = normalize_url(entry.get("official_site"))
    if not name or not official_site:
        return None
    domains = [host(official_site)]
    for d in entry.get("allowed_domains") or []:
        d = str(d).lower().replace("www.", "").strip()
        if d and d not in domains:
            domains.append(d)
    seeds = [official_site]
    for sub in entry.get("official_subsites") or []:
        if isinstance(sub, dict):
            url = normalize_url(sub.get("url"))
            if url and same_domain(url, domains) and url not in seeds:
                seeds.append(url)
    return {"name": name, "source": name, "default_venue": name, "aliases": [clean(x) for x in entry.get("aliases") or [] if clean(x)], "official_subsites": entry.get("official_subsites") or [], "domains": domains, "seeds": seeds, "official_site": official_site, "registry_status": entry.get("status"), "registry_score": entry.get("score")}


def load_sources():
    if not OFFICIAL_REGISTRY.exists():
        raise SystemExit(f"missing official source registry: {OFFICIAL_REGISTRY}")
    data = json.loads(OFFICIAL_REGISTRY.read_text(encoding="utf-8"))
    sources = []
    for entry in data.get("institutions") or []:
        if entry.get("status") != "confirmed":
            continue
        source = registry_source_from_entry(entry)
        if source:
            sources.append(source)
    if not sources:
        raise SystemExit("official_source_registry.json has no confirmed institutions")
    return sources


def source_cards(sources):
    return [{"title": source.get("name"), "url": source.get("official_site")} for source in sources if source.get("name") and source.get("official_site")]


def push_queue(queue, queued, url, score, label, source):
    url = normalize_url(url)
    if not url or not same_domain(url, source.get("domains") or []):
        return False
    key = url_key(url)
    if key in queued:
        return False
    queued.add(key)
    queue.append((score, url, label))
    return True


def crawl_source(source, location, deadline):
    queue = []
    queued = set()
    debug = {"source": source.get("name"), "official_site": source.get("official_site"), "domains": source.get("domains"), "seeds": [], "runtime_entry_preview": [], "sitemap_preview": [], "pages_fetched": 0, "queue_seen": 0, "discovered_preview": [], "fetched_preview": [], "accepted_preview": [], "rejected_preview": []}
    for seed in source.get("seeds") or []:
        if push_queue(queue, queued, seed, 100, "official-site", source):
            debug["seeds"].append(seed)
    for score, url, label in common_entry_links(source):
        if push_queue(queue, queued, url, score, label, source) and len(debug["runtime_entry_preview"]) < 30:
            debug["runtime_entry_preview"].append({"score": score, "url": url, "label": label})
    for score, url, label in sitemap_event_links(source, deadline):
        if push_queue(queue, queued, url, score, label, source) and len(debug["sitemap_preview"]) < 30:
            debug["sitemap_preview"].append({"score": score, "url": url, "label": label})
    fetched = set()
    results = []
    result_keys = set()
    debug["queue_seen"] = len(queued)
    while queue and time.time() < deadline and len(fetched) < MAX_PAGES_PER_SOURCE and len(results) < MAX_EVENTS_PER_SOURCE:
        queue.sort(key=lambda x: (-x[0], x[1]))
        score, url, label = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)
        try:
            page = fetch(url)
        except Exception as exc:
            if len(debug["rejected_preview"]) < 30:
                debug["rejected_preview"].append({"url": url, "reason": f"fetch:{type(exc).__name__}", "label": label})
            continue
        debug["pages_fetched"] += 1
        if len(debug["fetched_preview"]) < 40:
            debug["fetched_preview"].append({"url": url, "score": score, "label": label})
        for event in analyze_page(source, url, page, location, label):
            event_key = url_key(event["url"]) + "::" + event["title"].lower()
            if event_key in result_keys:
                continue
            result_keys.add(event_key)
            results.append(event)
            debug["accepted_preview"].append({"title": event["title"], "url": event["url"], "when": event["when"], "where": event.get("where")})
            if len(results) >= MAX_EVENTS_PER_SOURCE:
                break
        for link_score_value, link_url, link_label in discover_links(source, page, url):
            link_key = url_key(link_url)
            if link_key in fetched or link_key in queued:
                continue
            queued.add(link_key)
            queue.append((link_score_value, link_url, link_label))
            if len(debug["discovered_preview"]) < 40:
                debug["discovered_preview"].append({"score": link_score_value, "url": link_url, "label": link_label})
        debug["queue_seen"] = len(queued)
    debug["accepted"] = len(results)
    return results, debug


def sort_results(items, location):
    def local_score(item):
        text = " ".join(str(item.get(k, "")) for k in ("title", "where", "summary", "source_name")).lower()
        return sum(1 for term in LOCAL_PRIORITY_TERMS if term in text)
    return sorted(items, key=lambda x: (-local_score(x), x.get("source_name", ""), x.get("start_date", ""), x.get("title", "")))


def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    deadline = time.time() + MAX_SECONDS
    sources = load_sources()
    all_results = []
    debug_by_source = []
    seen = set()
    for source in sources:
        if time.time() >= deadline or len(all_results) >= MAX_TOTAL_EVENTS:
            break
        results, debug = crawl_source(source, location, deadline)
        debug_by_source.append(debug)
        for item in results:
            key = url_key(item["url"]) + "::" + item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            all_results.append(item)
            if len(all_results) >= MAX_TOTAL_EVENTS:
                break
    all_results = sort_results(all_results, location)[:MAX_TOTAL_EVENTS]
    payload = {"ok": True, "version": 20, "extractor": "official-registry-runtime-discovery-v20", "updated_at": now_iso(), "location": location, "source_registry": str(OFFICIAL_REGISTRY.name), "source_count": len(sources), "per_source_limit": MAX_EVENTS_PER_SOURCE, "count": len(all_results), "sources": source_cards(sources), "results": all_results, "debug_by_source": debug_by_source}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
