#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

TODAY = date.today()
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "75"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "12"))
MAX_TOTAL_EVENTS = int(os.environ.get("LOCAL_EVENTS_MAX_TOTAL_EVENTS", "80"))
PAST_GRACE_DAYS = int(os.environ.get("LOCAL_EVENTS_PAST_GRACE_DAYS", "1"))

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
MONTH_WORD = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december"
SEP = r"(?:-|–|—|to|until|till)"

SCRIPT_STYLE_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", re.I)
SCRIPT_JSON_RE = re.compile(r"<script[^>]+type=[\"']application/(?:ld\+)?json[\"'][^>]*>([\s\S]*?)</script>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", re.I)
META_RE = re.compile(r"<meta[^>]+(?:name|property)=[\"']([^\"']+)[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I | re.S)
FULL_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
END_YEAR_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
SAME_MONTH_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b", re.I)
TEXT_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b", re.I)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
DATE_HINT_RE = re.compile(r"\b20\d{2}-\d{1,2}-\d{1,2}\b|" + rf"\b\d{{1,2}}\s+(?:{MONTH_WORD})[a-z]*\s*(?:{SEP})?\s*\d{{0,2}}\s*(?:{MONTH_WORD})?[a-z]*\s*\d{{0,4}}\b", re.I)
TIME_HINT_RE = re.compile(r"\b(?:\d{1,2}(?::|\.)\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|daily|selected dates|all day|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.I)
EVENT_PATH_RE = re.compile(r"/(?:whats-on|whatson|events?|event|exhibitions?|exhibition|programmes?|programs?|activities?|guided-tours|discover-mandai/events)/", re.I)
BAD_CONTEXT_RE = re.compile(r"\b(previous programme|next programme|related|recommended|last updated|newsletter|privacy|terms of use|copyright|©)\b", re.I)
GENERIC_TITLE_RE = re.compile(r"^(events?|exhibitions?|programmes?|programs?|activities?|view all|overview|what'?s on|read more|learn more|find out more)$", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object) -> str:
    text = html.unescape(str(value or "")).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    text = SCRIPT_STYLE_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"#\{[^}]+\}|\{\{[^}]+\}\}|\$\{[^}]+\}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def short(value: object, limit: int) -> str:
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def norm_url(value: object, base: str = "") -> str:
    raw = html.unescape(str(value or "")).strip().replace("\\/", "/").replace("\\u002F", "/")
    if raw.startswith("//"):
        raw = "https:" + raw
    if base:
        raw = urljoin(base, raw)
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", urllib.parse.urlencode(query), ""))


def host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def same_domain(url: str, domains: list[str]) -> bool:
    h = host(url)
    return bool(h) and any(h == domain or h.endswith("." + domain) for domain in domains)


def key_url(url: str) -> str:
    parsed = urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, "")).lower()


def fetch_text(url: str, timeout: int = 12, max_bytes: int = 2_500_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-SG,en-US;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(max_bytes)
        content_type = response.headers.get("Content-Type", "")
        match = re.search(r"charset=([\w.-]+)", content_type, re.I)
        return raw.decode(match.group(1) if match else "utf-8", "replace")


def visible_lines(page: str) -> list[str]:
    text = SCRIPT_STYLE_RE.sub(" ", page)
    text = re.sub(r"</?(?:br|p|div|section|article|main|header|footer|h1|h2|h3|h4|li|ul|ol|table|tr|td|th|span)[^>]*>", "\n", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\\/", "/").replace("\\u002F", "/")
    text = re.sub(rf"\s+(?=(?:From\s+)?\d{{1,2}}\s+(?:{MONTH_WORD}))", "\n", text, flags=re.I)
    text = re.sub(r"\s+(?=(?:Daily|Fridays?|Saturdays?|Sundays?)\s*[-–])", "\n", text, flags=re.I)
    return [clean(line) for line in text.splitlines() if clean(line)]


def meta_map(page: str) -> dict[str, str]:
    out = {}
    for key, value in META_RE.findall(page):
        k = clean(key).lower()
        v = clean(value)
        if k and v and k not in out:
            out[k] = v
    return out


def tag_texts(page: str, tag: str) -> list[str]:
    return [clean(match.group(1)) for match in re.finditer(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", page, re.I) if clean(match.group(1))]


def parse_date(day: str, month_name: str, year: str | int | None = None, roll: bool = True) -> date | None:
    month = MONTHS.get(str(month_name).lower()[:3])
    if not month:
        return None
    full_year = int(year) if year else TODAY.year
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


def label_dates(label: str) -> list[date]:
    text = clean(label)
    out: list[date] = []
    inherited = None
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    if years:
        inherited = years[-1]

    def add(value: date | None) -> None:
        if value and value not in out:
            out.append(value)

    for d1, m1, y1, d2, m2, y2 in FULL_RANGE_RE.findall(text):
        add(parse_date(d1, m1, y1, False)); add(parse_date(d2, m2, y2, False))
    for d1, m1, d2, m2, y in END_YEAR_RANGE_RE.findall(text):
        add(parse_date(d1, m1, y, False)); add(parse_date(d2, m2, y, False))
    for d1, d2, m, y in SAME_MONTH_RANGE_RE.findall(text):
        year = y or inherited
        add(parse_date(d1, m, year, not bool(year))); add(parse_date(d2, m, year, not bool(year)))
    for d, m, y in TEXT_DATE_RE.findall(text):
        year = y or inherited
        add(parse_date(d, m, year, not bool(year)))
    for y, m, d in ISO_DATE_RE.findall(text):
        try:
            add(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return sorted(out)


def is_current_date_label(label: str) -> bool:
    dates = label_dates(label)
    return bool(dates and max(dates) >= TODAY - timedelta(days=PAST_GRACE_DAYS))


def best_start_date(label: str) -> str:
    dates = label_dates(label)
    future = [item for item in dates if item >= TODAY - timedelta(days=PAST_GRACE_DAYS)]
    return (min(future or dates or [TODAY])).isoformat()


def best_date_label(text: str) -> str:
    chunks = []
    for line in visible_lines(text):
        if BAD_CONTEXT_RE.search(line):
            continue
        if DATE_HINT_RE.search(line):
            chunks.append(line)
    for raw in re.findall(r'"(?:startDate|endDate|date|dateText|start_date|end_date)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text, re.I):
        value = clean(raw)
        if value:
            chunks.insert(0, value)
    scored: list[tuple[int, str]] = []
    for chunk in chunks:
        if not label_dates(chunk):
            continue
        score = 10
        if FULL_RANGE_RE.search(chunk) or END_YEAR_RANGE_RE.search(chunk):
            score += 50
        if TIME_HINT_RE.search(chunk):
            score += 8
        if is_current_date_label(chunk):
            score += 30
        scored.append((score, chunk))
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return short(scored[0][1], 180)


def title_from_page(page: str, fallback: str = "") -> str:
    metas = meta_map(page)
    candidates = [metas.get("og:title", ""), metas.get("twitter:title", ""), *tag_texts(page, "h1")[:2], *tag_texts(page, "title")[:1], fallback]
    for item in candidates:
        title = re.sub(r"\s*[|–-]\s*(Asian Civilisations Museum|ACM|National Museum of Singapore|Mandai|Singapore)\s*$", "", clean(item), flags=re.I)
        title = re.sub(r"^(previous programme|next programme)\s+", "", title, flags=re.I)
        if title and not GENERIC_TITLE_RE.match(title):
            return short(title, 140)
    return ""


def venue_from_text(source: dict, text: str) -> str:
    source_name = source.get("default_venue") or source.get("name") or ""
    for line in visible_lines(text)[:120]:
        if DATE_HINT_RE.search(line) or TIME_HINT_RE.search(line):
            continue
        if re.search(r"\b(museum|gallery|galleries|zoo|safari|park|library|safra|punggol|waterway|mandai|level|foyer|hall|theatre|room|atrium)\b", line, re.I):
            return short(line, 140)
    return str(source_name)


def json_ld_events(page: str) -> list[dict]:
    out = []

    def walk(obj):
        if isinstance(obj, dict):
            kind = obj.get("@type") or obj.get("type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item).lower() == "event" for item in kinds):
                out.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    for raw in SCRIPT_JSON_RE.findall(page):
        try:
            walk(json.loads(html.unescape(raw)))
        except Exception:
            continue
    return out


def event_from_json_ld(source: dict, url: str, page: str) -> list[dict]:
    events = []
    for obj in json_ld_events(page):
        title = clean(obj.get("name") or obj.get("headline") or "")
        start = clean(obj.get("startDate") or obj.get("start_date") or "")
        end = clean(obj.get("endDate") or obj.get("end_date") or "")
        label = " - ".join(item for item in [start, end] if item)
        if not title or not label or not label_dates(label) or not is_current_date_label(label):
            continue
        location = obj.get("location") or {}
        if isinstance(location, dict):
            where = clean(location.get("name") or location.get("address") or "")
        else:
            where = clean(location)
        events.append(make_event(source, url, title, label, where or venue_from_text(source, page), clean(obj.get("description") or "")))
    return events


def make_event(source: dict, url: str, title: str, when: str, where: str, summary: str = "") -> dict:
    return {
        "title": short(title, 140),
        "when": short(when, 180),
        "where": short(where or source.get("default_venue") or source.get("name") or "", 140),
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": url,
        "summary": short(summary or "Open the official page for details.", 260),
        "start_date": best_start_date(when),
        "kind": "event",
        "source_type": "verified_event_source",
    }


def event_from_page(source: dict, url: str, page: str, fallback_title: str = "", fallback_context: str = "") -> dict | None:
    structured = event_from_json_ld(source, url, page)
    if structured:
        return structured[0]
    title = title_from_page(page, fallback_title)
    date_label = best_date_label(page)
    if not title or not date_label or not is_current_date_label(date_label):
        return None
    metas = meta_map(page)
    summary = metas.get("og:description") or metas.get("description") or clean(fallback_context)
    return make_event(source, url, title, date_label, venue_from_text(source, page), summary)


def event_from_card(source: dict, url: str, title: str, context: str) -> dict | None:
    title = re.sub(r"^(previous programme|next programme)\s+", "", clean(title), flags=re.I)
    if not title or GENERIC_TITLE_RE.match(title) or BAD_CONTEXT_RE.search(title):
        return None
    date_label = best_date_label(context)
    if not date_label or not is_current_date_label(date_label):
        return None
    return make_event(source, url, title, date_label, venue_from_text(source, context), context)


def extract_link_cards(page: str, base_url: str, source: dict) -> list[dict]:
    domains = [str(item).lower().replace("www.", "") for item in source.get("allowed_domains") or []]
    found = {}
    decoded = html.unescape(page).replace("\\/", "/").replace("\\u002F", "/")
    for match in HREF_RE.finditer(decoded):
        url = norm_url(match.group(1), base_url)
        if not url or not same_domain(url, domains):
            continue
        path = urllib.parse.unquote(urlparse(url).path)
        if not EVENT_PATH_RE.search(path):
            continue
        label = clean(match.group(2))
        context = decoded[max(0, match.start() - 1200):match.end() + 1600]
        score = 0
        if label and not GENERIC_TITLE_RE.match(label):
            score += 30
        if DATE_HINT_RE.search(context):
            score += 50
        if TIME_HINT_RE.search(context):
            score += 8
        if BAD_CONTEXT_RE.search(label):
            score -= 80
        key = key_url(url)
        item = {"url": url, "label": label, "context": context, "score": score}
        if key not in found or score > found[key]["score"]:
            found[key] = item
    return sorted(found.values(), key=lambda item: (-item["score"], item["url"]))


def collect_source(source: dict, deadline: float) -> tuple[list[dict], dict]:
    debug = {
        "source": source.get("name"),
        "adapter": source.get("adapter"),
        "listing_urls": source.get("listing_urls") or [],
        "listing_fetched": 0,
        "cards_found": 0,
        "detail_fetched": 0,
        "accepted": 0,
        "accepted_preview": [],
        "not_output_preview": [],
    }
    accepted: list[dict] = []
    seen = set()

    for listing_url in source.get("listing_urls") or []:
        if time.time() >= deadline:
            break
        try:
            listing = fetch_text(listing_url)
            debug["listing_fetched"] += 1
        except Exception as exc:
            debug["not_output_preview"].append({"url": listing_url, "reason": f"listing_fetch_error:{type(exc).__name__}"})
            continue
        cards = extract_link_cards(listing, listing_url, source)
        debug["cards_found"] += len(cards)
        for card in cards:
            if time.time() >= deadline or len(accepted) >= MAX_EVENTS_PER_SOURCE:
                break
            url = card["url"]
            key = key_url(url)
            if key in seen:
                continue
            seen.add(key)

            event = event_from_card(source, url, card.get("label", ""), card.get("context", ""))
            reason = "card_missing_current_date"
            try:
                detail = fetch_text(url)
                debug["detail_fetched"] += 1
                detail_event = event_from_page(source, url, detail, card.get("label", ""), card.get("context", ""))
                if detail_event:
                    event = detail_event
            except Exception as exc:
                reason = f"detail_fetch_error:{type(exc).__name__}"

            if event:
                accepted.append(event)
                debug["accepted_preview"].append({"title": event["title"], "url": event["url"], "when": event["when"]})
            elif len(debug["not_output_preview"]) < 30:
                debug["not_output_preview"].append({"url": url, "label": card.get("label"), "reason": reason})

    debug["accepted"] = len(accepted)
    return accepted, debug


def source_local_score(item: dict, location: str) -> int:
    text = " ".join(str(item.get(key, "")) for key in ("title", "where", "summary", "source_name")).lower()
    terms = [term for term in re.split(r"[^a-z0-9]+", location.lower()) if len(term) >= 3]
    return sum(1 for term in terms if term in text)


def collect_events(config_path: Path, location: str) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    deadline = time.time() + MAX_SECONDS
    all_items = []
    debug = []
    seen = set()

    for source in config.get("sources") or []:
        if time.time() >= deadline or len(all_items) >= MAX_TOTAL_EVENTS:
            break
        items, source_debug = collect_source(source, deadline)
        debug.append(source_debug)
        for item in items:
            key = key_url(item["url"])
            if key in seen:
                continue
            seen.add(key)
            all_items.append(item)
            if len(all_items) >= MAX_TOTAL_EVENTS:
                break

    all_items.sort(key=lambda item: (-source_local_score(item, location), str(item.get("source_name", "")), str(item.get("start_date", "")), str(item.get("title", ""))))
    return {
        "ok": True,
        "version": 31,
        "extractor": "verified-source-adapters-v31",
        "updated_at": now_iso(),
        "location": location,
        "event_source_config": config_path.name,
        "source_count": len(config.get("sources") or []),
        "count": len(all_items),
        "sources": [{"title": item.get("name"), "url": item.get("official_home")} for item in config.get("sources") or []],
        "results": all_items,
        "debug_by_source": debug,
    }
