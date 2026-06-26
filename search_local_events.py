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
YEAR = str(datetime.now().year)
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "70"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "12"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "4"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

TEMPLATE_RE = re.compile(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}")
TAG_RE = re.compile(r"<[^>]+>")
BROKEN_ATTR_RE = re.compile(r"\b(?:hPriority|decoding|loading|alt|src|srcset|width|height|class|style|href|aria-[\w-]+|data-[\w-]+)=[\"'][^\"']*[\"']\s*/?", re.I)
DATE_RE = re.compile(
    r"("
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b\d{1,2}\s*(?:-|to|–|—)\s*\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*\d{0,4}\b|"
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(?:-|to|–|—)?\s*\d{0,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?[a-z]*\s*\d{0,4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s*\d{0,4}\b|"
    r"\btoday\b|\btomorrow\b|\btonight\b|\bthis weekend\b"
    r")",
    re.I,
)

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

SOURCES = [
    ("Children's Museum Singapore", "Children's Museum Singapore", "Children's Museum Singapore", ["heritage.sg"], ["https://www.heritage.sg/childrensmuseum/whatson"]),
    ("National Gallery Singapore", "National Gallery Singapore", "National Gallery Singapore", ["nationalgallery.sg"], ["https://www.nationalgallery.sg/sg/en/whats-on.html"]),
    ("National Museum Singapore", "National Museum Singapore", "National Museum Singapore", ["nhb.gov.sg"], ["https://www.nhb.gov.sg/nationalmuseum/whats-on"]),
    ("Asian Civilisations Museum", "Asian Civilisations Museum", "Asian Civilisations Museum", ["nhb.gov.sg"], ["https://www.nhb.gov.sg/acm/whats-on"]),
    ("Peranakan Museum", "Peranakan Museum", "Peranakan Museum", ["nhb.gov.sg"], ["https://www.nhb.gov.sg/peranakanmuseum/whats-on"]),
    ("ArtScience Museum", "ArtScience Museum", "ArtScience Museum", ["marinabaysands.com"], ["https://www.marinabaysands.com/museum/events.html", "https://www.marinabaysands.com/museum/exhibitions.html"]),
    ("Science Centre Singapore", "Science Centre Singapore", "Science Centre Singapore", ["science.edu.sg"], ["https://www.science.edu.sg/whats-on"]),
    ("NLB Punggol Regional Library", "NLB", "Punggol Regional Library", ["nlb.gov.sg"], ["https://www.nlb.gov.sg/main/whats-on"]),
    ("One Punggol", "One Punggol", "One Punggol", ["onepunggol.sg"], ["https://www.onepunggol.sg/events", "https://www.onepunggol.sg/happenings"]),
    ("onePA / People's Association", "onePA", "People's Association CCs", ["onepa.gov.sg"], ["https://www.onepa.gov.sg/events", "https://www.onepa.gov.sg/courses"]),
    ("SAFRA Punggol", "SAFRA Punggol", "SAFRA Punggol", ["safra.sg"], ["https://www.safra.sg/whats-on"]),
    ("Waterway Point", "Waterway Point", "Waterway Point", ["waterwaypoint.com.sg"], ["https://www.waterwaypoint.com.sg/happenings"]),
]

EVENT_WORDS = set("event events programme program workshop activity course class club session talk tour story storytelling storytime family children kids festival performance concert carnival reading exhibition show camp meet meeting walk trail experience".split())
GENERIC_TITLES = {
    "events", "event", "what's on", "whats on", "things to do", "programmes", "programs",
    "activities", "activities and events", "home", "homepage", "visit us", "contact us", "about us",
    "children's season 2026", "childrens season 2026", "all events", "view all", "address",
    "opening hours", "operating hours", "location", "directions", "getting here", "facilities",
}
INFO_WORDS = (
    "address", "opening hours", "operating hours", "closed for disinfection", "last entry",
    "directions", "getting here", "visit us", "home visit us", "facilities", "amenities",
    "parking", "contact us", "admission", "tickets and admission",
)
BAD_PATH_PARTS = ("/privacy", "/terms", "/contact", "/about", "/career", "/login", "/directions", "/parking")
LISTING_PATH_PARTS = ("/whatson/activities", "/whatson/childrens-season---listing-page", "/whats-on/view-all", "/whats-on/overview")
LISTING_EXACT = {"/events", "/event", "/happenings", "/whats-on", "/whatson", "/activities", "/things-to-do", "/programmes", "/programs"}
BAD_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js")
ACTION_TEXT_RE = re.compile(r"\b(register|registration|book|booking|ticket|tickets|details|learn more|find out more|read more|view more|view all|open|share)\b", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    text = BROKEN_ATTR_RE.sub(" ", text)
    text = TEMPLATE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_template(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_template(v) for v in value.values())
    if isinstance(value, list):
        return any(has_template(v) for v in value)
    return bool(TEMPLATE_RE.search(str(value or "")))


def shorten(value: object, limit: int) -> str:
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def canonical(value: object) -> str:
    text = clean(value).lower()
    text = DATE_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: object, base: str = "") -> str:
    raw = html.unescape(str(url or "")).strip()
    if base:
        raw = urljoin(base, raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urllib.parse.urlencode(query), ""))


def host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def same_domain(url: str, domains: list[str]) -> bool:
    h = host(url)
    return bool(h) and any(h.endswith(d) for d in domains)


def url_key(url: str) -> str:
    p = urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", p.query, "")).lower()


def is_listing(url: str) -> bool:
    p = urlparse(url).path.lower().rstrip("/")
    return p in LISTING_EXACT or any(part in p for part in LISTING_PATH_PARTS)


def bad_url(url: str) -> bool:
    p = urlparse(url).path.lower()
    return any(p.endswith(ext) for ext in BAD_EXT) or any(part in p for part in BAD_PATH_PARTS)


def fetch(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(1_600_000)
        ctype = response.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w.-]+)", ctype, re.I)
        enc = m.group(1) if m else "utf-8"
        return raw.decode(enc, "replace")


def meta(page: str, names: list[str]) -> str:
    for name in names:
        e = re.escape(name)
        patterns = (
            rf'<meta[^>]+(?:name|property)=["\']{e}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{e}["\']',
        )
        for pat in patterns:
            m = re.search(pat, page, re.I | re.S)
            if m and clean(m.group(1)):
                return clean(m.group(1))
    return ""


def extract_title(page: str, fallback: str = "") -> str:
    values = [meta(page, ["og:title", "twitter:title"])]
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page, re.I)
    if h1:
        values.append(clean(h1.group(1)))
    t = re.search(r"<title[^>]*>([\s\S]*?)</title>", page, re.I)
    if t:
        values.append(clean(t.group(1)))
    values.append(fallback)
    for value in values:
        title = re.sub(r"\s*[|\-–]\s*(NLB|National Library Board|onePA|One Punggol|SAFRA|Singapore)\s*$", "", clean(value), flags=re.I)
        if title and not has_template(title):
            return title
    return ""


def extract_summary(page: str) -> str:
    for value in (meta(page, ["og:description", "description", "twitter:description"]),):
        text = shorten(value, 260)
        if text and not has_template(text) and not looks_like_info_text(text):
            return text
    return "Open the official page for details."


def parse_date_label(label: str) -> list[date]:
    text = clean(label).lower()
    out: list[date] = []
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
        if y < 100:
            y += 2000
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
    seen = set()
    uniq = []
    for d in out:
        if d.isoformat() not in seen:
            seen.add(d.isoformat())
            uniq.append(d)
    return uniq


def future_label(label: str) -> bool:
    dates = parse_date_label(label)
    return bool(dates and max(dates) >= TODAY - timedelta(days=PAST_GRACE_DAYS))


def extract_sessions(text: str, url: str) -> list[dict]:
    labels = []
    seen = set()
    def add(value: object) -> None:
        label = clean(value)
        if not label or re.fullmatch(r"\d{4}", label) or not future_label(label):
            return
        key = label.lower()
        if key in seen:
            return
        seen.add(key)
        labels.append(label)
    for m in re.finditer(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", text):
        add(m.group(0))
        if len(labels) >= 8:
            break
    for m in DATE_RE.finditer(text):
        add(m.group(1))
        if len(labels) >= 8:
            break
    sessions = []
    for label in labels:
        dates = parse_date_label(label)
        item = {"date": label, "when": label, "label": label, "url": url}
        if dates:
            item["start_date"] = min(dates).isoformat()
            item["end_date"] = max(dates).isoformat()
        sessions.append(item)
    sessions.sort(key=lambda x: x.get("start_date", "9999-12-31"))
    return sessions


def summarize_sessions(sessions: list[dict]) -> str:
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
    if len(labels) > 4:
        shown += f" / +{len(labels) - 4} more"
    return f"{len(labels)} sessions: {shown}"


def looks_like_info_text(text: object) -> bool:
    lower = clean(text).lower()
    return any(word in lower for word in INFO_WORDS) or "hpriority" in lower or "decoding=" in lower


def title_is_event(title: str, url: str) -> bool:
    title_key = canonical(title)
    if not title or title_key in GENERIC_TITLES:
        return False
    if looks_like_info_text(title):
        return False
    if ACTION_TEXT_RE.fullmatch(title.strip()):
        return False
    blob = f"{title} {urlparse(url).path}".lower()
    return any(word in blob for word in EVENT_WORDS)


def make_event(name: str, source_name: str, venue: str, title: str, summary: str, sessions: list[dict], url: str, location: str, score_base: int = 60) -> dict | None:
    title = clean(title)
    summary = clean(summary) if summary else "Open the official page for details."
    if summary != "Open the official page for details." and looks_like_info_text(summary):
        summary = "Open the official page for details."
    if has_template({"title": title, "summary": summary}) or not title_is_event(title, url) or not sessions or is_listing(url):
        return None
    loc_words = [w for w in re.split(r"\W+", location.lower()) if len(w) >= 4]
    blob = f"{title} {summary} {urlparse(url).path}".lower()
    priority = any(w in blob for w in loc_words)
    score = score_base + len(sessions) + (12 if priority else 0)
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
        "who": source_name,
        "organizer": source_name,
        "why": shorten(summary, 260),
        "description": shorten(summary, 260),
        "how": "Official page",
        "summary": shorten(summary, 260),
        "poster_summary": shorten(summary, 220),
        "source": source_name,
        "source_name": name,
        "url": url,
        "score": score,
        "priority_location": priority,
    }


def build_detail_event(name: str, source_name: str, venue: str, domains: list[str], url: str, page: str, location: str) -> dict | None:
    url = normalize_url(url)
    if not url or is_listing(url) or not same_domain(url, domains) or bad_url(url):
        return None
    title = extract_title(page)
    summary = extract_summary(page)
    sessions = extract_sessions(" ".join([title, summary, clean(page[:90000])]), url)
    return make_event(name, source_name, venue, title, summary, sessions, url, location, 70)


def title_from_anchor(anchor_text: str, url: str) -> str:
    title = clean(anchor_text)
    if not title or len(title) < 4:
        return ""
    if ACTION_TEXT_RE.search(title) and len(title.split()) <= 5:
        return ""
    if not title_is_event(title, url):
        return ""
    return title


def extract_listing_candidates(page: str, base_url: str, domains: list[str]) -> list[tuple[str, str, list[dict]]]:
    out = []
    seen = set()
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', page, re.I):
        url = normalize_url(m.group(1), base_url)
        if not url or is_listing(url) or url_key(url) in seen or not same_domain(url, domains) or bad_url(url):
            continue
        context = page[max(0, m.start() - 700): min(len(page), m.end() + 900)]
        title = title_from_anchor(m.group(2), url)
        if not title:
            continue
        # Keep only the local card date, never the whole HTML block as description.
        sessions = extract_sessions(clean(context), url)
        if not sessions:
            continue
        seen.add(url_key(url))
        out.append((url, title, sessions))
    return out


def extract_links(page: str, base_url: str, domains: list[str]) -> list[str]:
    out = []
    seen = set()
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', page, re.I):
        url = normalize_url(m.group(1), base_url)
        anchor = clean(m.group(2)).lower()
        if not url or url_key(url) in seen or not same_domain(url, domains) or bad_url(url):
            continue
        path = urlparse(url).path.lower()
        if is_listing(url) or any(w in (path + " " + anchor) for w in EVENT_WORDS) or DATE_RE.search(anchor):
            seen.add(url_key(url))
            out.append(url)
    return out[:40]


def crawl_source(src: tuple, location: str, deadline: float) -> tuple[list[dict], dict]:
    name, source_name, venue, domains, seeds = src
    events = []
    queue = []
    seen = set()
    fetched = []
    def push(url: str) -> None:
        url = normalize_url(url)
        key = url_key(url)
        if url and key not in seen and same_domain(url, domains) and not bad_url(url):
            seen.add(key)
            queue.append(url)
    for seed in seeds:
        push(seed)
    while queue and len(fetched) < MAX_PAGES_PER_SOURCE and len(events) < MAX_EVENTS_PER_SOURCE and time.monotonic() < deadline:
        url = queue.pop(0)
        try:
            page = fetch(url)
        except Exception:
            continue
        fetched.append({"url": url, "title": shorten(extract_title(page, url), 90)})
        for candidate_url, candidate_title, candidate_sessions in extract_listing_candidates(page, url, domains):
            item = make_event(name, source_name, venue, candidate_title, "Open the official page for details.", candidate_sessions, candidate_url, location, 76)
            if item:
                events.append(item)
                push(candidate_url)
        item = build_detail_event(name, source_name, venue, domains, url, page, location)
        if item:
            events.append(item)
        for link in extract_links(page, url, domains):
            push(link)
    debug = {"source": name, "pages_fetched": len(fetched), "accepted": len(events), "fetched_preview": fetched[:8], "accepted_preview": [{"title": e.get("title"), "when": e.get("when"), "url": e.get("url")} for e in events[:8]]}
    return events, debug


def event_key(item: dict) -> str:
    return "::".join([clean(item.get("source_name")).lower(), clean(item.get("venue")).lower(), canonical(item.get("title"))])


def dedupe(events: list[dict]) -> list[dict]:
    grouped = {}
    for item in events:
        if has_template(item) or is_listing(item.get("url") or "") or not item.get("sessions") or not title_is_event(clean(item.get("title")), item.get("url") or ""):
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
            p = urlparse(url)
            item["url"] = urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", p.query, f"event-{idx}"))
    return out


def collect(location: str) -> tuple[list[dict], list[dict], list[dict]]:
    deadline = time.monotonic() + MAX_SECONDS
    events = []
    debug = []
    for src in SOURCES:
        if time.monotonic() >= deadline:
            break
        source_events, source_debug = crawl_source(src, location, deadline)
        events.extend(source_events)
        debug.append(source_debug)
    events = dedupe(events)
    events.sort(key=lambda x: (not bool(x.get("priority_location")), -int(x.get("score", 0)), x.get("date", ""), x.get("source_name", ""), x.get("title", "").lower()))
    sources = [{"type": "source", "title": name, "url": seeds[0], "source": source_name, "venue": venue} for name, source_name, venue, _domains, seeds in SOURCES]
    return events, sources, debug


def main() -> None:
    location = " ".join(sys.argv[1:]).strip() or DEFAULT_LOCATION
    events, sources, debug = collect(location)
    payload = {
        "version": 12,
        "ok": True,
        "extractor": "official-local-event-conservative-v12",
        "updated_at": now_iso(),
        "location": location,
        "count": len(events),
        "results": events,
        "items": events,
        "sources": sources,
        "debug_by_source": debug,
        "settings": {"listing_pages_are_sources_only": True, "no_html_context_summary": True},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"local events updated count={len(events)} sources={len(sources)} location={location}")


if __name__ == "__main__":
    main()
