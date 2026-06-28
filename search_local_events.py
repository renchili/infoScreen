#!/usr/bin/env python3
"""Official-source local event crawler for InfoScreen.

The crawler reads confirmed official homepages from official_source_registry.json.
It discovers same-domain event detail URLs, fetches each official page, then
extracts fields from the primary event content block. It does not attach dates
found in related/programmes/footer sections to the current detail page.
"""

from __future__ import annotations

import argparse
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
from xml.etree import ElementTree


BASE = Path(__file__).resolve().parent
OUT = BASE / "local_event_search_results.json"
REG = BASE / "official_source_registry.json"

DEFAULT_LOCATION = "Punggol Singapore"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TODAY = date.today()

MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "95"))
MAX_PAGES_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_PAGES_PER_SOURCE", "70"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "8"))
MAX_TOTAL_EVENTS = int(os.environ.get("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "60"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
MONTH_WORD = (
    "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    "aug|august|sep|sept|september|oct|october|nov|november|dec|december"
)
SEP = r"(?:-|–|—|to|until|till)"

ISO_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
DMY_SLASH_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
FULL_RANGE_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\s*{SEP}\s*"
    rf"(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b",
    re.I,
)
END_YEAR_RANGE_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*{SEP}\s*"
    rf"(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b",
    re.I,
)
SAME_MONTH_RANGE_RE = re.compile(
    rf"\b(\d{{1,2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b",
    re.I,
)
TEXT_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b", re.I)
TEXT_MONTH_FIRST_RE = re.compile(rf"\b({MONTH_WORD})[a-z]*\s+(\d{{1,2}}),?\s*(20\d{{2}})?\b", re.I)
DATE_SEARCH_RE = re.compile(
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    rf"\b\d{{1,2}}\s+(?:{MONTH_WORD})[a-z]*\s*(?:{SEP})?\s*"
    rf"\d{{0,2}}\s*(?:{MONTH_WORD})?[a-z]*\s*\d{{0,4}}\b|"
    rf"\b(?:{MONTH_WORD})[a-z]*\s+\d{{1,2}},?\s*\d{{0,4}}\b",
    re.I,
)
OPEN_START_RE = re.compile(
    rf"\b(?:from|since|starting|starts)\s+\d{{1,2}}\s+(?:{MONTH_WORD})[a-z]*\s+20\d{{2}}\b",
    re.I,
)
ONWARDS_RE = re.compile(
    rf"\b(?:\d{{1,2}}\s+(?:{MONTH_WORD})[a-z]*\s+20\d{{2}}|20\d{{2}}-\d{{1,2}}-\d{{1,2}})"
    r"\s+(?:onwards|onward)\b",
    re.I,
)

TIME_RE = re.compile(
    r"\b(?:\d{1,2}(?::|\.)\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|"
    r"daily|all day|selected dates|last admission|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|wed|thu|fri|sat|sun|weekend)\b",
    re.I,
)
VENUE_RE = re.compile(
    r"\b(?:gallery|galleries|museum|level|foyer|green|b1|l1|l2|room|hall|"
    r"theatre|theater|zoo|safari|paradise|cove|concourse|atrium|basement|"
    r"exhibit|trail|hut|night safari|singapore zoo|bird paradise|river wonders)\b",
    re.I,
)
EVENT_WORDS = (
    "event",
    "programme",
    "program",
    "workshop",
    "activity",
    "course",
    "class",
    "session",
    "talk",
    "tour",
    "storytelling",
    "storytime",
    "festival",
    "performance",
    "concert",
    "carnival",
    "reading",
    "exhibition",
    "show",
    "camp",
    "walk",
    "trail",
    "experience",
    "drop-in",
    "holiday",
    "screening",
    "guided",
    "open house",
    "lecture",
)
EVENT_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in EVENT_WORDS) + r")\b", re.I)
STATIC_RE = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|ico|pdf|zip|css|js|mp4|mp3|woff2?|ttf|eot)(?:\?|$)", re.I)
SCRIPT_STYLE_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
SCRIPT_JSON_RE = re.compile(r"<script[^>]+type=[\"']application/(?:ld\+)?json[\"'][^>]*>([\s\S]*?)</script>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", re.I)
JSON_URL_RE = re.compile(r"[\"'](?:href|url|link|path|slug|canonicalUrl|pageUrl)[\"']\s*:\s*[\"']([^\"']+)[\"']", re.I)
RAW_PATH_RE = re.compile(
    r"/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|"
    r"activities?|happenings?|courses|workshops?|things-to-do)/[^\"'<>\\\s]+",
    re.I,
)
ABS_URL_RE = re.compile(r"https?://[^\"'<>\\\s]+", re.I)
SITEMAP_RE = re.compile(r"^\s*Sitemap:\s*(\S+)\s*$", re.I | re.M)
LOC_RE = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.I)
LISTING_RE = re.compile(
    r"/(?:whats-on|whatson|events?|overview|view-all|exhibitions?|exhibition|"
    r"programmes?|programs?|activities?|happenings?|courses|workshops?)/?$",
    re.I,
)
DETAIL_RE = re.compile(
    r"/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|"
    r"programs?|activities?|happenings?|courses|workshops?|discover-mandai/events)/.+",
    re.I,
)
GENERIC_TITLE_RE = re.compile(
    r"^(events?|exhibitions?|programmes?|programs?|activities?|guided tours?|"
    r"past exhibitions?|family programmes?|school programmes?|for seniors|view all|"
    r"overview|what'?s on|sections|highlights)$",
    re.I,
)
PRIMARY_BOUNDARY_RE = re.compile(
    r"^(?:previous programme|next programme|visit .+ today|subscribe|subscribe to our newsletter|"
    r"keep up to date|sections|highlights|awards & accolades|connect with us|about\s*$|"
    r"doing business with us|for schools|help & support|managed by|follow us|"
    r"terms of use|privacy statement|copyright|©)\b",
    re.I,
)
NOT_PRIMARY_DATE_RE = re.compile(
    r"\b(?:last updated|copyright|terms|conditions|newsletter|sign-up|sign up|"
    r"programmes on selected dates|stay tuned|related|recommended)\b",
    re.I,
)

ENTRY_PATHS = (
    "/whats-on",
    "/whats-on/overview",
    "/whats-on/view-all",
    "/events",
    "/event",
    "/exhibition",
    "/exhibitions",
    "/programmes",
    "/activities",
    "/en/events",
    "/en/events.html",
    "/en/whats-on",
    "/en/discover-mandai/events",
    "/en/discover-mandai/events.html",
)
LOCAL_TERMS = ("punggol", "waterway", "one punggol", "punggol regional library", "safra punggol")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_line(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip(" |•\t")


def short(value: object, limit: int) -> str:
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def norm(url: object, base: str = "") -> str:
    value = html.unescape(str(url or "")).strip()
    value = value.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    if value.startswith("//"):
        value = "https:" + value
    if base:
        value = urljoin(base, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", urllib.parse.urlencode(query), "")
    )


def host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def root(url: str) -> str:
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc.lower(), "/", "", "", ""))


def key_url(url: str) -> str:
    parsed = urlparse(url)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, "")
    ).lower()


def same_domain(url: str, domains: list[str]) -> bool:
    h = host(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def is_static(url: str) -> bool:
    path = urllib.parse.unquote(urlparse(url).path)
    return bool(STATIC_RE.search(path)) or "/api/media/" in path or "/content/dam/" in path or "/_jcr_content/" in path


def is_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/") or "/"
    if LISTING_RE.search(path):
        return True
    return bool(parsed.query and re.search(r"\b(category|filter|time|date|type|page)=", parsed.query, re.I))


def is_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    return bool(DETAIL_RE.search(path)) and not is_listing_url(url) and not is_static(url)


def fetch(url: str, timeout: int = 10, max_bytes: int = 2_500_000) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,*/*",
            "Accept-Language": "en-SG,en-US;q=0.9,en;q=0.8",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if content_type and not re.search(r"text|html|json|xml|javascript", content_type, re.I):
            raise ValueError("non_text_content")
        raw = response.read(max_bytes)
        match = re.search(r"charset=([\w.-]+)", content_type, re.I)
        return raw.decode(match.group(1) if match else "utf-8", "replace")


def meta_content(page: str, names: list[str]) -> str:
    for name in names:
        escaped = re.escape(name)
        patterns = (
            rf"<meta[^>]+(?:name|property)=[\"']{escaped}[\"'][^>]+content=[\"']([^\"']+)[\"']",
            rf"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"']{escaped}[\"']",
        )
        for pattern in patterns:
            match = re.search(pattern, page, re.I | re.S)
            if match:
                value = clean(match.group(1))
                if value:
                    return value
    return ""


def tag_texts(page: str, tag: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", page, re.I):
        value = clean(match.group(1))
        if value:
            values.append(value)
    return values


def strip_title_suffix(title: str) -> str:
    title = clean(title)
    title = re.sub(
        r"\s*[|–-]\s*(Asian Civilisations Museum|ACM|National Museum of Singapore|"
        r"National Museum Singapore|Mandai Wildlife Reserve|Mandai Wildlife Group|Singapore)\s*$",
        "",
        title,
        flags=re.I,
    )
    return clean(title)


def title_of(page: str, fallback: str = "") -> str:
    candidates = [
        meta_content(page, ["og:title", "twitter:title"]),
        *tag_texts(page, "h1")[:2],
    ]

    headings = tag_texts(page, "h1")[:1] + tag_texts(page, "h2")[:1]
    if len(headings) >= 2 and headings[0].lower() not in headings[1].lower():
        candidates.append(clean(f"{headings[0]} {headings[1]}"))

    title_tags = tag_texts(page, "title")
    candidates.extend(title_tags[:1])
    candidates.append(fallback)

    for item in candidates:
        title = strip_title_suffix(item)
        if title and "#{" not in title and "{{" not in title and not GENERIC_TITLE_RE.match(title):
            return title
    return ""


def summary_of(page: str, block_lines: list[str] | None = None) -> str:
    meta = meta_content(page, ["og:description", "description", "twitter:description"])
    if meta and "#{" not in meta:
        return short(meta, 260)

    for line in block_lines or []:
        text = clean(line)
        if len(text) >= 80 and not DATE_SEARCH_RE.search(text) and not TIME_RE.search(text):
            return short(text, 260)

    return "Open the official page for details."


def visible_lines(page: str) -> list[str]:
    text = SCRIPT_STYLE_RE.sub(" ", page)
    text = re.sub(r"</?(?:br|p|div|section|article|main|header|footer|h1|h2|h3|h4|li|ul|ol|table|tr|td|th|span)[^>]*>", "\n", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    # Preserve compact date/time rows that sites often render without separators.
    text = re.sub(rf"\s+(?=(?:From\s+)?\d{{1,2}}\s+(?:{MONTH_WORD}))", "\n", text, flags=re.I)
    text = re.sub(r"\s+(?=(?:Daily|Fridays?|Saturdays?|Sundays?)\s*[-–])", "\n", text, flags=re.I)
    text = re.sub(
        r"\s+(?=Asian Civilisations Museum\b|National Museum of Singapore\b|Night Safari\b|Singapore Zoo\b)",
        "\n",
        text,
        flags=re.I,
    )
    lines = []
    for raw in text.splitlines():
        line = clean_line(raw)
        if line:
            lines.append(line)
    return lines


def title_tokens(title: str) -> list[str]:
    base = clean(title).lower()
    tokens = [base]
    for separator in (":", "|", " - ", " – "):
        if separator in base:
            tokens.append(base.split(separator, 1)[0].strip())
    words = [word for word in re.findall(r"[a-z0-9]+", base) if len(word) >= 4]
    if len(words) >= 2:
        tokens.append(" ".join(words[:2]))
    return [token for token in tokens if len(token) >= 4]


def primary_block(page: str, title: str) -> tuple[list[str], dict[str, object]]:
    lines = visible_lines(page)
    if not lines:
        return [], {"primary_block_found": False, "reason": "no_visible_lines"}

    tokens = title_tokens(title)
    start = 0
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(token and token in lowered for token in tokens):
            start = index
            break

    block: list[str] = []
    for line in lines[start:]:
        if block and PRIMARY_BOUNDARY_RE.search(line):
            break
        block.append(line)
        if len(block) >= 90:
            break

    return block, {
        "primary_block_found": bool(block),
        "block_start": start,
        "block_preview": block[:12],
    }


def month_number(name: str) -> int | None:
    return MONTHS.get(str(name).lower()[:3])


def make_date(day: str, month_name: str, year: str | int | None = None, roll: bool = True) -> date | None:
    month = month_number(month_name)
    if not month:
        return None
    full_year = int(year) if year else TODAY.year
    if full_year < 100:
        full_year += 2000
    try:
        parsed = date(full_year, month, int(day))
    except ValueError:
        return None
    if roll and not year and parsed < TODAY - timedelta(days=PAST_GRACE_DAYS):
        try:
            parsed = date(full_year + 1, month, int(day))
        except ValueError:
            return None
    return parsed


def add_date(out: list[date], value: date | None) -> None:
    if value and value not in out:
        out.append(value)


def label_dates(label: str) -> list[date]:
    text = clean(label)
    found: list[date] = []
    explicit_years = [int(item) for item in re.findall(r"\b(20\d{2})\b", text)]
    inherited_year = explicit_years[-1] if explicit_years else None

    for y, m, d in ISO_RE.findall(text):
        try:
            add_date(found, date(int(y), int(m), int(d)))
        except ValueError:
            pass

    for d, m, y in DMY_SLASH_RE.findall(text):
        yy = int(y)
        if yy < 100:
            yy += 2000
        try:
            add_date(found, date(yy, int(m), int(d)))
        except ValueError:
            pass

    for d1, m1, y1, d2, m2, y2 in FULL_RANGE_RE.findall(text):
        add_date(found, make_date(d1, m1, y1, False))
        add_date(found, make_date(d2, m2, y2, False))

    for d1, m1, d2, m2, y in END_YEAR_RANGE_RE.findall(text):
        add_date(found, make_date(d1, m1, y, False))
        add_date(found, make_date(d2, m2, y, False))

    for d1, d2, m, y in SAME_MONTH_RANGE_RE.findall(text):
        year = y or inherited_year
        add_date(found, make_date(d1, m, year, not bool(year)))
        add_date(found, make_date(d2, m, year, not bool(year)))

    for d, m, y in TEXT_DATE_RE.findall(text):
        year = y or inherited_year
        add_date(found, make_date(d, m, year, not bool(year)))

    for m, d, y in TEXT_MONTH_FIRST_RE.findall(text):
        year = y or inherited_year
        add_date(found, make_date(d, m, year, not bool(year)))

    return sorted(found)


def has_open_ended_date(label: str) -> bool:
    return bool(OPEN_START_RE.search(label) or ONWARDS_RE.search(label))


def date_score(lines: list[str], index: int) -> int:
    line = lines[index]
    window = " ".join(lines[max(0, index - 2) : min(len(lines), index + 5)])
    score = 0
    if FULL_RANGE_RE.search(line) or END_YEAR_RANGE_RE.search(line):
        score += 40
    if ONWARDS_RE.search(line) or OPEN_START_RE.search(line):
        score += 34
    if SAME_MONTH_RANGE_RE.search(line):
        score += 20
    if DATE_SEARCH_RE.search(line):
        score += 10
    if TIME_RE.search(window):
        score += 8
    if VENUE_RE.search(window):
        score += 8
    if index <= 18:
        score += 8
    if len(line) > 180:
        score -= 24
    if NOT_PRIMARY_DATE_RE.search(line):
        score -= 30
    return score


def session_from_label(label: str, ongoing_hint: bool = False) -> dict[str, object] | None:
    text = clean(label)
    dates = label_dates(text)
    if not dates:
        return None
    ongoing = bool(ongoing_hint or has_open_ended_date(text))
    return {"label": text, "dates": dates, "ongoing": ongoing}


def sessions_from_block(block: list[str]) -> list[dict[str, object]]:
    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(block):
        if not DATE_SEARCH_RE.search(line) and not OPEN_START_RE.search(line) and not ONWARDS_RE.search(line):
            continue
        score = date_score(block, index)
        if score > 0:
            scored.append((score, index, line))

    if not scored:
        return []

    scored.sort(key=lambda item: (-item[0], item[1]))
    session = session_from_label(scored[0][2], has_open_ended_date(scored[0][2]))
    return [session] if session else []


def sessions_from_text(text: str, limit: int = 12) -> list[dict[str, object]]:
    cleaned = clean(text)[:300000]
    sessions: list[dict[str, object]] = []
    seen: set[str] = set()

    for match in DATE_SEARCH_RE.finditer(cleaned):
        label = clean(match.group(0))
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        session = session_from_label(label, has_open_ended_date(label))
        if session:
            sessions.append(session)
        if len(sessions) >= limit:
            break

    return sessions


def event_is_current(sessions: list[dict[str, object]]) -> bool:
    dates: list[date] = []
    for session in sessions:
        if session.get("ongoing"):
            return True
        dates.extend(session.get("dates") or [])
    return bool(dates and max(dates) >= TODAY - timedelta(days=PAST_GRACE_DAYS))


def best_date(sessions: list[dict[str, object]]) -> date:
    all_dates: list[date] = []
    future_dates: list[date] = []
    for session in sessions:
        dates = session.get("dates") or []
        all_dates.extend(dates)
        future_dates.extend([item for item in dates if item >= TODAY - timedelta(days=PAST_GRACE_DAYS)])
    return min(future_dates or all_dates or [TODAY])


def when_text(sessions: list[dict[str, object]]) -> str:
    labels: list[str] = []
    for session in sessions:
        label = clean(session.get("label") or "")
        if label and label not in labels:
            labels.append(label)
    return " / ".join(labels[:4]) + (f" / +{len(labels) - 4} more" if len(labels) > 4 else "")


def venue_from_block(source: dict[str, object], block: list[str], sessions: list[dict[str, object]]) -> str:
    session_labels = {clean(session.get("label") or "").lower() for session in sessions}
    for index, line in enumerate(block):
        if clean(line).lower() not in session_labels and not DATE_SEARCH_RE.search(line):
            continue
        nearby = list(reversed(block[max(0, index - 3) : index])) + block[index + 1 : index + 8]
        for candidate in nearby:
            value = clean(candidate)
            if not value:
                continue
            if DATE_SEARCH_RE.search(value) or TIME_RE.search(value) or NOT_PRIMARY_DATE_RE.search(value):
                continue
            if VENUE_RE.search(value):
                return short(value, 140)

    txt = " ".join(block[:40])
    for name in [source.get("default_venue") or source.get("name") or "", *(source.get("aliases") or [])]:
        if name and re.search(r"\b" + re.escape(str(name)) + r"\b", txt, re.I):
            return str(name)

    return str(source.get("default_venue") or source.get("name") or "")


def structured_json_objects(page: str) -> list[object]:
    objects: list[object] = []
    for match in SCRIPT_JSON_RE.finditer(page):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except Exception:
            pass
    return objects


def walk_json(value: object):
    stack = [value]
    while stack:
        item = stack.pop()
        yield item
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def is_event_object(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    raw_type = value.get("@type") or value.get("type")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    return any(str(item).lower() == "event" for item in types)


def iso_date_from_value(value: object) -> date | None:
    text = clean(value)
    match = ISO_RE.search(text)
    if not match:
        return None
    y, m, d = match.groups()
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def structured_session(node: dict[str, object]) -> list[dict[str, object]]:
    start = iso_date_from_value(node.get("startDate") or node.get("datePublished"))
    end = iso_date_from_value(node.get("endDate") or node.get("doorTime")) or start
    if not start:
        return []
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    return [{"label": label, "dates": sorted({start, end} if end else {start})}]


def structured_location(node: dict[str, object]) -> str:
    loc = node.get("location")
    if isinstance(loc, str):
        return short(loc, 140)
    if isinstance(loc, dict):
        return short(loc.get("name") or loc.get("address") or "", 140)
    return ""


def build_event(
    source: dict[str, object],
    url: str,
    title: str,
    sessions: list[dict[str, object]],
    page: str,
    block: list[str],
    structured: bool = False,
    node: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, str]:
    title = clean(title)
    if not title:
        return None, "parser_error:title_not_found"
    if GENERIC_TITLE_RE.match(title):
        return None, "parser_error:generic_title"
    if not sessions:
        return None, "parser_error:date_not_found"
    if not event_is_current(sessions):
        return None, "expired_event"
    if not structured and not is_detail_url(url):
        return None, "not_detail_page"

    venue = structured_location(node or {}) or venue_from_block(source, block, sessions)
    return (
        {
            "title": short(title, 140),
            "when": when_text(sessions),
            "where": short(venue, 140),
            "host": source["name"],
            "source_name": source["name"],
            "url": url,
            "summary": summary_of(page, block),
            "start_date": best_date(sessions).isoformat(),
            "kind": "event",
            "source_type": "official_registry",
            "structured": bool(structured),
        },
        "accepted",
    )


def analyze_page(source: dict[str, object], url: str, page: str, label: str = "") -> tuple[list[dict[str, object]], dict[str, object]]:
    events: list[dict[str, object]] = []
    diagnostics: dict[str, object] = {
        "url": url,
        "candidate_fetched": True,
        "structured_event_found": False,
        "primary_block_found": False,
        "primary_date_found": False,
    }

    for obj in structured_json_objects(page):
        for node in walk_json(obj):
            if is_event_object(node):
                diagnostics["structured_event_found"] = True
                title = clean(node.get("name") or node.get("headline") or "")
                sessions = structured_session(node)
                event, reason = build_event(source, url, title, sessions, page, [], True, node)
                if event:
                    events.append(event)
                else:
                    diagnostics["structured_skip_reason"] = reason

    if events:
        return events, diagnostics

    title = title_of(page, label)
    block, block_diag = primary_block(page, title)
    diagnostics.update(block_diag)
    sessions = sessions_from_block(block)

    if not sessions:
        sessions = sessions_from_text(" ".join(block[:80]), 4)

    diagnostics["primary_date_found"] = bool(sessions)
    if sessions:
        diagnostics["primary_date_label"] = sessions[0].get("label")

    event, reason = build_event(source, url, title, sessions, page, block, False, None)
    if event:
        return [event], diagnostics

    diagnostics["reason"] = reason
    return [], diagnostics


def score_url(source: dict[str, object], url: str, label: str, context: str) -> int:
    if not url or not same_domain(url, source["domains"]) or is_static(url):
        return -999

    parsed = urlparse(url)
    route = urllib.parse.unquote((parsed.path + " " + parsed.query).replace("-", " ").replace("_", " ")).lower()
    text = clean(str(label or "") + " " + str(context or "")[:1800]).lower()

    score = 0
    if is_detail_url(url):
        score += 80
    if is_listing_url(url):
        score += 45
    if EVENT_RE.search(route):
        score += 20
    if EVENT_RE.search(text):
        score += 20
    if DATE_SEARCH_RE.search(text):
        score += 18
    if re.search(r"\b(today|upcoming|current|ongoing|now showing|latest|new|2026|2027)\b", text + " " + route, re.I):
        score += 20
    if any(term in text or term in route for term in LOCAL_TERMS):
        score += 8
    return score


def discovered_links(source: dict[str, object], page: str, base_url: str) -> list[tuple[int, str, str]]:
    found: dict[str, tuple[int, str, str]] = {}

    def add(raw: str, label: str, context: str) -> None:
        url = norm(raw, base_url)
        score = score_url(source, url, label, context) if url else -999
        if score < 35:
            return
        key = key_url(url)
        item = (score, url, short(label, 140))
        if key not in found or score > found[key][0]:
            found[key] = item

    for match in HREF_RE.finditer(page):
        context = page[max(0, match.start() - 900) : match.end() + 1400]
        add(match.group(1), clean(match.group(2)), context)

    decoded = html.unescape(page).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    for regex in (JSON_URL_RE, RAW_PATH_RE, ABS_URL_RE):
        for match in regex.finditer(decoded):
            raw = match.group(1) if regex is JSON_URL_RE else match.group(0)
            context = decoded[max(0, match.start() - 700) : match.end() + 1000]
            add(raw, match.group(0), context)

    return sorted(found.values(), key=lambda item: (-item[0], item[1]))


def sitemap_urls_from_xml(xml: str) -> list[str]:
    urls = LOC_RE.findall(xml)
    if urls:
        return urls

    try:
        root_node = ElementTree.fromstring(xml)
    except Exception:
        return []

    out: list[str] = []
    for node in root_node.iter():
        if node.tag.lower().endswith("loc") and node.text:
            out.append(node.text.strip())
    return out


def sitemap_links(source: dict[str, object], deadline: float) -> list[tuple[int, str, str]]:
    root_url = root(source["official_site"])
    initial = [urljoin(root_url, "/sitemap.xml"), urljoin(root_url, "/sitemap_index.xml")]

    try:
        robots = fetch(urljoin(root_url, "/robots.txt"), 6, 400000)
        initial.extend(norm(item, root_url) for item in SITEMAP_RE.findall(robots))
    except Exception:
        pass

    pending = [(url, 0) for url in dict.fromkeys(url for url in initial if url and same_domain(url, source["domains"]))]
    seen: set[str] = set()
    found: dict[str, tuple[int, str, str]] = {}

    while pending and time.time() < deadline and len(seen) < 20 and len(found) < 160:
        url, depth = pending.pop(0)
        key = key_url(url)
        if key in seen:
            continue
        seen.add(key)
        try:
            xml = fetch(url, 8, 2_500_000)
        except Exception:
            continue

        for loc in sitemap_urls_from_xml(xml):
            candidate = norm(loc, url)
            if not candidate or not same_domain(candidate, source["domains"]) or is_static(candidate):
                continue
            if ("sitemap" in candidate.lower() or candidate.lower().endswith(".xml")) and depth < 2:
                pending.append((candidate, depth + 1))
                continue
            score = score_url(source, candidate, candidate, "")
            if score >= 35:
                found[key_url(candidate)] = (score + 10, candidate, "sitemap")

    return sorted(found.values(), key=lambda item: (-item[0], item[1]))


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    path = urllib.parse.unquote(parsed.path.lower()).rstrip("/")
    path = re.sub(r"\.html$", "", path)
    path = re.sub(r"^/en/discover-mandai", "", path)
    path = re.sub(r"^/whats-on/(exhibition|exhibitions|programme|programmes|event|events)/", r"/\1/", path)
    path = path.replace("/exhibitions/", "/exhibition/")
    path = path.replace("/programmes/", "/programme/")
    path = path.replace("/events/", "/event/")
    return host(url) + path


def load_sources() -> list[dict[str, object]]:
    data = json.loads(REG.read_text(encoding="utf-8"))
    sources: list[dict[str, object]] = []

    for entry in data.get("institutions") or []:
        if entry.get("status") != "confirmed":
            continue
        official_site = norm(entry.get("official_site"))
        name = clean(entry.get("name"))
        if not official_site or not name:
            continue

        domains: list[str] = []
        for domain in [host(official_site), *[str(item).lower().replace("www.", "").strip() for item in entry.get("allowed_domains") or []]]:
            if domain and domain not in domains:
                domains.append(domain)

        seeds = [official_site]
        for subsite in entry.get("official_subsites") or []:
            if isinstance(subsite, dict):
                url = norm(subsite.get("url"))
                if url and same_domain(url, domains) and url not in seeds:
                    seeds.append(url)

        sources.append(
            {
                "name": name,
                "default_venue": name,
                "aliases": [clean(item) for item in entry.get("aliases") or [] if clean(item)],
                "official_site": official_site,
                "domains": domains,
                "seeds": seeds,
            }
        )

    if not sources:
        raise SystemExit("official_source_registry.json has no confirmed institutions")
    return sources


def crawl_source(source: dict[str, object], deadline: float) -> tuple[list[dict[str, object]], dict[str, object]]:
    queue: list[tuple[int, str, str]] = []
    queued: set[str] = set()
    fetched: set[str] = set()
    results: list[dict[str, object]] = []
    result_keys: set[str] = set()

    debug: dict[str, object] = {
        "source": source["name"],
        "official_site": source["official_site"],
        "domains": source["domains"],
        "seeds": [],
        "runtime_entry_preview": [],
        "sitemap_preview": [],
        "pages_fetched": 0,
        "queue_seen": 0,
        "discovered_preview": [],
        "fetched_preview": [],
        "accepted_preview": [],
        "not_output_preview": [],
    }

    def push(url: str, score: int, label: str) -> bool:
        normalized = norm(url)
        if not normalized or not same_domain(normalized, source["domains"]) or is_static(normalized):
            return False
        key = key_url(normalized)
        if key in queued or key in fetched:
            return False
        queued.add(key)
        queue.append((score, normalized, label))
        return True

    for seed in source["seeds"]:
        if push(seed, 100, "official-site"):
            debug["seeds"].append(seed)

    for base_url in [root(url) for url in source["seeds"]]:
        for path in ENTRY_PATHS:
            url = norm(path, base_url)
            score = score_url(source, url, path, "upcoming current today")
            if score >= 35 and push(url, score + 5, "common-entry") and len(debug["runtime_entry_preview"]) < 30:
                debug["runtime_entry_preview"].append({"score": score + 5, "url": url, "label": "common-entry"})

    for score, url, label in sitemap_links(source, deadline):
        if push(url, score, label) and len(debug["sitemap_preview"]) < 30:
            debug["sitemap_preview"].append({"score": score, "url": url, "label": label})

    debug["queue_seen"] = len(queued)

    while (
        queue
        and time.time() < deadline
        and len(fetched) < MAX_PAGES_PER_SOURCE
        and len(results) < MAX_EVENTS_PER_SOURCE
    ):
        queue.sort(key=lambda item: (-item[0], item[1]))
        score, url, label = queue.pop(0)
        key = key_url(url)
        if key in fetched:
            continue
        fetched.add(key)

        try:
            page = fetch(url)
        except Exception as exc:
            if len(debug["not_output_preview"]) < 30:
                debug["not_output_preview"].append(
                    {"url": url, "reason": f"fetch_error:{type(exc).__name__}", "label": label}
                )
            continue

        debug["pages_fetched"] += 1
        if len(debug["fetched_preview"]) < 40:
            debug["fetched_preview"].append({"url": url, "score": score, "label": label})

        events, diag = analyze_page(source, url, page, label)
        if events:
            for event in events:
                event_key = canonical_url(event["url"])
                if event_key in result_keys:
                    continue
                result_keys.add(event_key)
                results.append(event)
                if len(debug["accepted_preview"]) < 30:
                    debug["accepted_preview"].append(
                        {
                            "title": event["title"],
                            "url": event["url"],
                            "when": event["when"],
                            "where": event.get("where"),
                        }
                    )
                if len(results) >= MAX_EVENTS_PER_SOURCE:
                    break
        elif is_detail_url(url) and len(debug["not_output_preview"]) < 30:
            debug["not_output_preview"].append(
                {
                    "url": url,
                    "reason": diag.get("reason") or "parser_error:unknown",
                    "label": label,
                    "primary_date_label": diag.get("primary_date_label"),
                    "primary_block_found": diag.get("primary_block_found"),
                }
            )

        for link_score, link_url, link_label in discovered_links(source, page, url):
            link_key = key_url(link_url)
            if link_key in fetched or link_key in queued:
                continue
            queued.add(link_key)
            queue.append((link_score, link_url, link_label))
            if len(debug["discovered_preview"]) < 40:
                debug["discovered_preview"].append({"score": link_score, "url": link_url, "label": link_label})

        debug["queue_seen"] = len(queued)

    debug["accepted"] = len(results)
    return results, debug


def sort_results(items: list[dict[str, object]], location: str) -> list[dict[str, object]]:
    def local_score(item: dict[str, object]) -> int:
        text = " ".join(str(item.get(key, "")) for key in ("title", "where", "summary", "source_name")).lower()
        return sum(1 for term in LOCAL_TERMS if term in text)

    return sorted(
        items,
        key=lambda item: (
            -local_score(item),
            str(item.get("source_name", "")),
            str(item.get("start_date", "")),
            str(item.get("title", "")),
        ),
    )


def collect(location: str) -> dict[str, object]:
    deadline = time.time() + MAX_SECONDS
    sources = load_sources()
    all_items: list[dict[str, object]] = []
    debug: list[dict[str, object]] = []
    seen: set[str] = set()

    for source in sources:
        if time.time() >= deadline or len(all_items) >= MAX_TOTAL_EVENTS:
            break
        items, source_debug = crawl_source(source, deadline)
        debug.append(source_debug)

        for item in items:
            key = canonical_url(item["url"])
            if key in seen:
                continue
            seen.add(key)
            all_items.append(item)
            if len(all_items) >= MAX_TOTAL_EVENTS:
                break

    all_items = sort_results(all_items, location)[:MAX_TOTAL_EVENTS]
    return {
        "ok": True,
        "version": 24,
        "extractor": "official-registry-template-blocks-v24",
        "updated_at": now_iso(),
        "location": location,
        "source_registry": REG.name,
        "source_count": len(sources),
        "per_source_limit": MAX_EVENTS_PER_SOURCE,
        "count": len(all_items),
        "sources": [{"title": source["name"], "url": source["official_site"]} for source in sources],
        "results": all_items,
        "debug_by_source": debug,
    }


def assert_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def run_self_test() -> int:
    sample = """
    <html><head><title>Let's Play! The Art and Design of Asian Games | ACM</title></head>
    <body>
      <h1>Let's Play!</h1>
      <h2>The Art and Design of Asian Games</h2>
      <p>Intro copy.</p>
      <div>5 Sep 2025–7 Jun 2026</div>
      <div>Daily - 10am–7pm</div>
      <div>Asian Civilisations Museum</div>
      <a>previous programme Elegant Sounds</a>
      <h2>Programmes</h2>
      <div>31 January</div>
      <div>30 May–28 June 2026</div>
    </body></html>
    """
    title = title_of(sample)
    block, _ = primary_block(sample, title)
    sessions = sessions_from_block(block)
    assert_equal("primary_date", sessions[0]["label"], "5 Sep 2025–7 Jun 2026")
    assert_equal("venue", venue_from_block({"name": "Asian Civilisations Museum", "default_venue": "Asian Civilisations Museum", "aliases": []}, block, sessions), "Asian Civilisations Museum")

    dates_2021 = label_dates("16 April to 17 October 2021")
    assert_equal("historical_year_start", dates_2021[0].isoformat(), "2021-04-16")
    assert_equal("historical_year_end", dates_2021[-1].isoformat(), "2021-10-17")

    assert_equal(
        "canonical_alias",
        canonical_url("https://www.nationalmuseum.nhb.gov.sg/whats-on/exhibition/once-upon-a-tide"),
        canonical_url("https://www.nationalmuseum.nhb.gov.sg/exhibition/once-upon-a-tide"),
    )

    print("local-event self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("location", nargs="*", help="Location preference, e.g. Punggol Singapore")
    parser.add_argument("--self-test", action="store_true", help="Run parser self-tests without crawling or writing output.")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    location = " ".join(args.location).strip() or DEFAULT_LOCATION
    payload = collect(location)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
