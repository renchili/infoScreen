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
TODAY = date.today()
DEFAULT_LOCATION = "Punggol Singapore"
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "80"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "14"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "4"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
ATTR_RE = re.compile(r"\b(?:hPriority|decoding|loading|alt|src|srcset|width|height|class|style|href|aria-[\w-]+|data-[\w-]+)=[\"'][^\"']*[\"']\s*/?", re.I)
DATE_RE = re.compile(r"\b20\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s*(?:-|to|–|—|until|till)\s*\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*\d{0,4}\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:-|to|–|—|until|till)?\s*\d{0,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?[a-z]*\s*\d{0,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s*\d{0,4}\b|\btoday\b|\btomorrow\b|\btonight\b|\bthis weekend\b", re.I)
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
EVENT_WORDS = set("event events programme program workshop activity course class club session talk tour story storytelling storytime family children kids festival performance concert carnival reading exhibition show camp meet meeting walk trail experience".split())
GENERIC = {"events", "event", "what's on", "whats on", "activities", "activities and events", "things to do", "programmes", "programs", "home", "homepage", "visit us", "contact us", "about us", "address", "opening hours", "operating hours", "location", "directions", "getting here", "facilities", "view all"}
INFO_WORDS = ("address", "opening hours", "operating hours", "closed for disinfection", "last entry", "directions", "getting here", "visit us", "facilities", "amenities", "parking", "contact us")
CONTAINERS = {"/events", "/event", "/happenings", "/whats-on", "/whatson", "/activities", "/things-to-do", "/programmes", "/programs"}
CONTAINER_FILES = {"whats-on.html", "events.html", "happenings.html", "activities.html"}
BAD_PATHS = ("/privacy", "/terms", "/contact", "/about", "/career", "/login", "/directions", "/parking")
BAD_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js")
ACTION_RE = re.compile(r"\b(register|registration|book|booking|ticket|tickets|details|learn more|find out more|read more|view more|view all|open|share)\b", re.I)

OTHER_SAFRA_VENUES = ["toa payoh", "tampines", "mount faber", "yishun", "jurong", "choa chu kang", "cck"]
OTHER_NLB_VENUES = ["ang mo kio", "bedok", "bishan", "bukit batok", "bukit merah", "bukit panjang", "choa chu kang", "clementi", "geylang east", "jurong", "marine parade", "pasir ris", "queenstown", "sengkang", "serangoon", "tampines", "toa payoh", "woodlands", "yishun"]

SOURCES = [
    {"name": "Children's Museum Singapore", "source": "Children's Museum Singapore", "venue": "Children's Museum Singapore", "domains": ["heritage.sg"], "seeds": ["https://www.heritage.sg/childrensmuseum/whatson"]},
    {"name": "National Gallery Singapore", "source": "National Gallery Singapore", "venue": "National Gallery Singapore", "domains": ["nationalgallery.sg"], "seeds": ["https://www.nationalgallery.sg/sg/en/whats-on.html"]},
    {"name": "National Museum Singapore", "source": "National Museum Singapore", "venue": "National Museum Singapore", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/nationalmuseum/whats-on"]},
    {"name": "Asian Civilisations Museum", "source": "Asian Civilisations Museum", "venue": "Asian Civilisations Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/acm/whats-on"]},
    {"name": "Peranakan Museum", "source": "Peranakan Museum", "venue": "Peranakan Museum", "domains": ["nhb.gov.sg"], "seeds": ["https://www.nhb.gov.sg/peranakanmuseum/whats-on"]},
    {"name": "ArtScience Museum", "source": "ArtScience Museum", "venue": "ArtScience Museum", "domains": ["marinabaysands.com"], "seeds": ["https://www.marinabaysands.com/museum/events.html", "https://www.marinabaysands.com/museum/exhibitions.html"]},
    {"name": "Science Centre Singapore", "source": "Science Centre Singapore", "venue": "Science Centre Singapore", "domains": ["science.edu.sg"], "seeds": ["https://www.science.edu.sg/whats-on"]},
    {"name": "NLB Punggol Regional Library", "source": "NLB", "venue": "Punggol Regional Library", "domains": ["nlb.gov.sg"], "seeds": ["https://www.nlb.gov.sg/main/whats-on"], "local_terms": ["punggol", "punggol regional library"], "blocked_terms": OTHER_NLB_VENUES},
    {"name": "One Punggol", "source": "One Punggol", "venue": "One Punggol", "domains": ["onepunggol.sg"], "seeds": ["https://www.onepunggol.sg/events", "https://www.onepunggol.sg/happenings"], "local_terms": ["punggol", "one punggol"]},
    {"name": "onePA / People's Association", "source": "onePA", "venue": "People's Association CCs", "domains": ["onepa.gov.sg"], "seeds": ["https://www.onepa.gov.sg/events", "https://www.onepa.gov.sg/courses"], "local_terms": ["punggol", "punggol west", "punggol 21", "one punggol"], "blocked_terms": ["choa chu kang", "tampines", "toa payoh", "jurong", "bedok", "pasir ris", "woodlands", "yishun", "sengkang", "ang mo kio"]},
    {"name": "SAFRA Punggol", "source": "SAFRA Punggol", "venue": "SAFRA Punggol", "domains": ["safra.sg"], "seeds": ["https://www.safra.sg/whats-on"], "local_terms": ["punggol", "safra punggol"], "blocked_terms": OTHER_SAFRA_VENUES},
    {"name": "Waterway Point", "source": "Waterway Point", "venue": "Waterway Point", "domains": ["waterwaypoint.com.sg"], "seeds": ["https://www.waterwaypoint.com.sg/happenings"], "local_terms": ["waterway", "punggol", "waterway point"]},
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    text = html.unescape(str(value or ""))
    text = SCRIPT_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = ATTR_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical(value):
    text = DATE_RE.sub(" ", clean(value).lower())
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(value, limit):
    text = clean(value)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def normalize_url(url, base=""):
    raw = html.unescape(str(url or "")).strip()
    if base:
        raw = urljoin(base, raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", urllib.parse.urlencode(qs), ""))


def url_key(url):
    p = urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", p.query, "")).lower()


def host(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def same_domain(url, domains):
    h = host(url)
    return bool(h) and any(h.endswith(d) for d in domains)


def is_container_url(url):
    path = urlparse(url).path.lower().rstrip("/")
    filename = path.rsplit("/", 1)[-1]
    if path in CONTAINERS or filename in CONTAINER_FILES:
        return True
    return any(x in path for x in ("/whatson/activities", "/whatson/childrens-season---listing-page", "/whats-on/view-all", "/whats-on/overview"))


def bad_url(url):
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in BAD_EXT) or any(x in path for x in BAD_PATHS)


def detail_path_signal(url):
    if is_container_url(url):
        return False
    path = urlparse(url).path.lower()
    roots = ("/events/", "/event/", "/happenings/", "/whats-on/", "/whatson/", "/activities/", "/activity/", "/programmes/", "/programs/", "/courses/", "/course/")
    return any(root in path for root in roots)


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(1_600_000)
        m = re.search(r"charset=([\w.-]+)", resp.headers.get("Content-Type", ""), re.I)
        return raw.decode(m.group(1) if m else "utf-8", "replace")


def meta(page, names):
    for name in names:
        e = re.escape(name)
        for pat in (rf'<meta[^>]+(?:name|property)=["\']{e}["\'][^>]+content=["\']([^"\']+)["\']', rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{e}["\']'):
            m = re.search(pat, page, re.I | re.S)
            if m and clean(m.group(1)):
                return clean(m.group(1))
    return ""


def page_title(page, fallback=""):
    vals = [meta(page, ["og:title", "twitter:title"])]
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page, re.I)
    if h1:
        vals.append(clean(h1.group(1)))
    t = re.search(r"<title[^>]*>([\s\S]*?)</title>", page, re.I)
    if t:
        vals.append(clean(t.group(1)))
    vals.append(fallback)
    for value in vals:
        title = re.sub(r"\s*[|\-–]\s*(NLB|National Library Board|onePA|One Punggol|SAFRA|Singapore)\s*$", "", clean(value), flags=re.I)
        if title and not TEMPLATE_RE.search(title):
            return title
    return ""


def info_text(value):
    text = clean(value).lower()
    return any(w in text for w in INFO_WORDS) or "hpriority" in text or "decoding=" in text


def summary_from_detail(page):
    text = meta(page, ["og:description", "description", "twitter:description"])
    return shorten(text, 260) if text and not info_text(text) else "Open the official page for details."


def venue_matches_source(source, title, summary, url):
    local_terms = [t.lower() for t in source.get("local_terms", [])]
    blocked_terms = [t.lower() for t in source.get("blocked_terms", [])]
    if not local_terms and not blocked_terms:
        return True
    blob = f"{title} {summary} {url}".lower().replace("-", " ").replace("_", " ")
    has_local = any(t in blob for t in local_terms)
    has_blocked = any(t in blob for t in blocked_terms)
    if has_blocked and not has_local:
        return False
    if local_terms and not has_local:
        return False
    return True


def parse_dates(label):
    text = clean(label).lower()
    out = []
    if "today" in text:
        out.append(TODAY)
    if "tomorrow" in text:
        out.append(TODAY + timedelta(days=1))
    for m in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text):
        try:
            out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            out.append(date(y, int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(\d{4})?\b", text):
        y = int(m.group(3)) if m.group(3) else TODAY.year
        try:
            d = date(y, MONTHS[m.group(2)[:3]], int(m.group(1)))
            if not m.group(3) and d < TODAY - timedelta(days=30):
                d = date(TODAY.year + 1, d.month, d.day)
            out.append(d)
        except ValueError:
            pass
    seen, uniq = set(), []
    for d in out:
        if d.isoformat() not in seen:
            seen.add(d.isoformat())
            uniq.append(d)
    return uniq


def sessions_from_text(text, url):
    out, seen = [], set()
    for m in DATE_RE.finditer(text):
        label = clean(m.group(0))
        dates = parse_dates(label)
        if not dates or max(dates) < TODAY - timedelta(days=PAST_GRACE_DAYS):
            continue
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        out.append({"date": label, "when": label, "label": label, "url": url, "start_date": min(dates).isoformat(), "end_date": max(dates).isoformat()})
        if len(out) >= 8:
            break
    out.sort(key=lambda x: x.get("start_date", "9999-12-31"))
    return out


def summarize_sessions(sessions):
    labels = []
    seen = set()
    for s in sessions:
        label = clean(s.get("date") or s.get("when") or s.get("label"))
        if label and label.lower() not in seen:
            seen.add(label.lower())
            labels.append(label)
    if not labels:
        return "Check official page"
    if len(labels) == 1:
        return labels[0]
    shown = " / ".join(labels[:4])
    return f"{len(labels)} sessions: {shown}" + (f" / +{len(labels) - 4} more" if len(labels) > 4 else "")


def title_valid(title, url):
    key = canonical(title)
    if not title or key in GENERIC or info_text(title) or TEMPLATE_RE.search(str(title)):
        return False
    if ACTION_RE.fullmatch(title.strip()):
        return False
    blob = f"{title.lower()} {urlparse(url).path.lower()}"
    return detail_path_signal(url) or any(w in blob for w in EVENT_WORDS)


def make_event(source, url, title, summary, sessions, location, score):
    url = normalize_url(url)
    title = clean(title)
    summary = clean(summary) if summary else "Open the official page for details."
    if summary != "Open the official page for details." and info_text(summary):
        summary = "Open the official page for details."
    if not url or is_container_url(url) or not sessions or not title_valid(title, url):
        return None
    if not venue_matches_source(source, title, summary, url):
        return None
    loc_words = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    priority = any(w in f"{title} {summary} {url}".lower() for w in loc_words)
    when = summarize_sessions(sessions)
    return {"type": "event", "title": shorten(title, 150), "poster_title": shorten(title, 150), "what": shorten(title, 150), "when": when, "date": when, "sessions": sessions, "session_count": len(sessions), "where": source["venue"], "venue": source["venue"], "who": source["source"], "organizer": source["source"], "why": shorten(summary, 260), "description": shorten(summary, 260), "how": "Official page", "summary": shorten(summary, 260), "poster_summary": shorten(summary, 220), "source": source["source"], "source_name": source["name"], "url": url, "score": score + (12 if priority else 0), "priority_location": priority}


def structured_events(source, page_url, page, location):
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', page, re.I):
        try:
            data = json.loads(html.unescape(m.group(1)).strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            typ = obj.get("@type") or obj.get("type") or ""
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower() == "event" for t in types):
                url = normalize_url(obj.get("url") or page_url, page_url)
                if same_domain(url, source["domains"]):
                    title = clean(obj.get("name") or obj.get("headline"))
                    summary = clean(obj.get("description")) or summary_from_detail(page)
                    dates = " ".join([str(obj.get("startDate") or ""), str(obj.get("endDate") or "")])
                    sessions = sessions_from_text(dates or clean(page[:90000]), url)
                    item = make_event(source, url, title, summary, sessions, location, 95)
                    if item:
                        out.append(item)
            for key in ("@graph", "itemListElement"):
                val = obj.get(key)
                if isinstance(val, (dict, list)):
                    stack.append(val)
    return out


def analyze_page(source, url, page, location):
    if is_container_url(url) or bad_url(url):
        return []
    events = structured_events(source, url, page, location)
    if events:
        return events
    title = page_title(page)
    summary = summary_from_detail(page)
    sessions = sessions_from_text(" ".join([title, summary, clean(page[:100000])]), url)
    item = make_event(source, url, title, summary, sessions, location, 70)
    return [item] if item else []


def link_score(base_url, url, anchor, context):
    if not url or bad_url(url):
        return -999
    path = urlparse(url).path.lower()
    anchor_l = clean(anchor).lower()
    ctx_l = clean(context[:1200]).lower()
    score = 0
    if is_container_url(url):
        score += 25
    if detail_path_signal(url):
        score += 40
    if any(w in (path + " " + anchor_l) for w in EVENT_WORDS):
        score += 25
    if DATE_RE.search(ctx_l):
        score += 15
    if len(canonical(anchor_l)) >= 5 and canonical(anchor_l) not in GENERIC and not ACTION_RE.fullmatch(anchor_l):
        score += 10
    if info_text(anchor_l) or info_text(ctx_l[:180]):
        score -= 40
    if url_key(url) == url_key(base_url):
        score -= 30
    return score


def discover_links(page, base_url, source):
    found = {}
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', page, re.I):
        url = normalize_url(m.group(1), base_url)
        if not url or not same_domain(url, source["domains"]):
            continue
        context = page[max(0, m.start() - 600): min(len(page), m.end() + 900)]
        score = link_score(base_url, url, m.group(2), context)
        if score < 25:
            continue
        key = url_key(url)
        if score > found.get(key, (-999, ""))[0]:
            found[key] = (score, url)
    return sorted(found.values(), key=lambda x: -x[0])[:50]


def crawl_source(source, location, deadline):
    queue = []
    queued, fetched = set(), set()
    events = []
    fetched_preview = []
    def push(url, score):
        url = normalize_url(url)
        key = url_key(url)
        if url and key not in queued and key not in fetched and same_domain(url, source["domains"]) and not bad_url(url):
            queued.add(key)
            queue.append((score, url))
    for seed in source.get("seeds", []):
        push(seed, 80)
    while queue and len(fetched) < MAX_PAGES_PER_SOURCE and len(events) < MAX_EVENTS_PER_SOURCE and time.monotonic() < deadline:
        queue.sort(key=lambda x: -x[0])
        _score, url = queue.pop(0)
        key = url_key(url)
        if key in fetched:
            continue
        fetched.add(key)
        try:
            page = fetch(url)
        except Exception:
            continue
        fetched_preview.append({"url": url, "title": shorten(page_title(page, url), 90), "container": is_container_url(url)})
        events.extend(analyze_page(source, url, page, location))
        for score, link in discover_links(page, url, source):
            push(link, score)
    return {"events": events, "debug": {"source": source["name"], "pages_fetched": len(fetched), "queue_seen": len(queued), "accepted": len(events), "fetched_preview": fetched_preview[:10], "accepted_preview": [{"title": e.get("title"), "when": e.get("when"), "url": e.get("url")} for e in events[:8]]}}


def event_key(item):
    return "::".join([clean(item.get("source_name")).lower(), clean(item.get("venue")).lower(), canonical(item.get("title"))])


def dedupe(events):
    grouped = {}
    for item in events:
        if is_container_url(item.get("url") or "") or not item.get("sessions") or not title_valid(clean(item.get("title")), item.get("url") or ""):
            continue
        key = event_key(item)
        if key not in grouped or int(item.get("score", 0)) > int(grouped[key].get("score", 0)):
            grouped[key] = item
    out = list(grouped.values())
    used = {}
    for idx, item in enumerate(out, 1):
        url = item.get("url") or ""
        used[url.lower()] = used.get(url.lower(), 0) + 1
        if used[url.lower()] > 1:
            p = urlparse(url)
            item["url"] = urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", p.query, f"event-{idx}"))
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
    events = dedupe(events)
    events.sort(key=lambda x: (not bool(x.get("priority_location")), -int(x.get("score", 0)), x.get("date", ""), x.get("source_name", ""), x.get("title", "").lower()))
    sources = [{"type": "source", "title": s["name"], "url": s["seeds"][0], "source": s["source"], "venue": s["venue"]} for s in SOURCES]
    return events, sources, debug


def main():
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events, sources, debug = collect(location)
    payload = {"version": 14, "ok": True, "extractor": "detail-page-analyzing-crawler-v14", "updated_at": now_iso(), "location": location, "count": len(events), "results": events, "items": events, "sources": sources, "debug_by_source": debug, "settings": {"listing_pages_are_frontier_only": True, "emit_detail_pages_only": True, "venue_consistency_check": True}}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")


if __name__ == "__main__":
    main()
