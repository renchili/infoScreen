#!/usr/bin/env python3
"""Field-first local event crawler entrypoint.

The crawler already discovers the right official URLs. The bug was that fetched
detail pages were judged from route/label previews before their fields were
located. This wrapper fixes the order: fetch official page -> locate title/date/
venue/summary -> then decide expiry and dedupe.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse

import search_local_events_v21 as crawler


BLOCK_RE = re.compile(
    r"</?(?:br|p|div|section|article|main|header|footer|h1|h2|h3|h4|li|ul|ol|table|tr|td|th|span)[^>]*>",
    re.I,
)
TIME_RE = re.compile(
    r"\b(?:\d{1,2}(?:\.\d{2})?\s*(?:am|pm)|daily|all day|selected dates|last admission|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b",
    re.I,
)
VENUE_RE = re.compile(
    r"\b(?:gallery|galleries|museum|level|foyer|green|b1|l1|l2|room|hall|theatre|"
    r"zoo|safari|paradise|cove|concourse|atrium|basement)\b",
    re.I,
)
RANGE_WITH_TWO_YEARS_RE = re.compile(
    rf"\b\d{{1,2}}\s+(?:{crawler.MW})[a-z]*\s+20\d{{2}}\s*(?:-|–|—|to|until|till)\s*"
    rf"\d{{1,2}}\s+(?:{crawler.MW})[a-z]*\s+20\d{{2}}\b",
    re.I,
)
OPEN_START_RE = re.compile(
    rf"\b(?:from|since|starting|starts)\s+\d{{1,2}}\s+(?:{crawler.MW})[a-z]*\s+20\d{{2}}\b",
    re.I,
)


def _visible_lines(page: str) -> list[str]:
    text = crawler.SCRIPT_STYLE_RE.sub(" ", page)
    text = BLOCK_RE.sub("\n", text)
    text = crawler.TAG_RE.sub(" ", text)
    text = crawler.clean(text)
    text = re.sub(r"\s+(From\s+\d{1,2}\s+(?:%s))" % crawler.MW, r"\n\1", text, flags=re.I)
    text = re.sub(r"\s+(\d{1,2}\s+(?:%s)[a-z]*\s+20\d{2}\s*(?:-|–|—|to|until|till)\s*\d{1,2}\s+(?:%s)[a-z]*\s+20\d{2})" % (crawler.MW, crawler.MW), r"\n\1", text, flags=re.I)
    text = re.sub(r"\s+(\d{1,2}\s+(?:%s)[a-z]*\s*(?:-|–|—|to|until|till)\s*\d{1,2}\s+(?:%s)[a-z]*\s+20\d{2})" % (crawler.MW, crawler.MW), r"\n\1", text, flags=re.I)
    return [x.strip(" |•\t") for x in text.splitlines() if x.strip(" |•\t")]


def _title_tokens(title: str) -> list[str]:
    title = crawler.clean(title)
    bits = [title]
    if ":" in title:
        bits.append(title.split(":", 1)[0].strip())
    if "|" in title:
        bits.append(title.split("|", 1)[0].strip())
    return [x for x in bits if len(x) >= 4]


def _detail_block(page: str, title: str) -> list[str]:
    lines = _visible_lines(page)
    if not lines:
        return []
    title_l = title.lower()
    tokens = [x.lower() for x in _title_tokens(title)]
    start = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if low == title_l or any(tok and tok in low for tok in tokens):
            start = i
            break
    return lines[start : min(len(lines), start + 120)]


def _parse_dates_from_label(label: str, ongoing_hint: bool = False) -> dict | None:
    label = crawler.clean(label)
    dates = crawler.label_dates(label)
    if not dates:
        return None
    ongoing = bool(ongoing_hint or OPEN_START_RE.search(label))
    if ongoing or max(dates) >= crawler.TODAY - crawler.timedelta(days=crawler.PAST_GRACE):
        return {"label": label, "dates": dates, "ongoing": ongoing}
    return None


def _date_line_score(lines: list[str], idx: int) -> int:
    line = lines[idx]
    window = " ".join(lines[idx : min(len(lines), idx + 6)])
    score = 0
    if RANGE_WITH_TWO_YEARS_RE.search(line):
        score += 12
    if OPEN_START_RE.search(line):
        score += 10
    if crawler.DATE_RE.search(line):
        score += 6
    if TIME_RE.search(window):
        score += 5
    if VENUE_RE.search(window):
        score += 6
    if len(line) <= 80:
        score += 2
    if re.search(r"\b(entry requirements|copyright|last updated|terms|conditions)\b", line, re.I):
        score -= 8
    return score


def _sessions_from_detail_block(page: str, title: str) -> list[dict]:
    block = _detail_block(page, title)
    scored: list[tuple[int, int, str]] = []
    for i, line in enumerate(block):
        if crawler.DATE_RE.search(line) or OPEN_START_RE.search(line) or RANGE_WITH_TWO_YEARS_RE.search(line):
            scored.append((_date_line_score(block, i), i, line))
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]))
    sessions = []
    for _, _, line in scored[:3]:
        session = _parse_dates_from_label(line, bool(OPEN_START_RE.search(line)))
        if session and session["label"].lower() not in {s["label"].lower() for s in sessions}:
            sessions.append(session)
    return sessions


def _sessions_from_text_smart(text: str, limit: int = 12) -> list[dict]:
    cleaned = crawler.clean(text)[:300000]
    sessions = []
    seen = set()

    def add(label: str, ongoing_hint: bool = False):
        label = crawler.clean(label)
        k = label.lower()
        if not label or k in seen:
            return
        seen.add(k)
        session = _parse_dates_from_label(label, ongoing_hint)
        if session:
            sessions.append(session)

    for match in RANGE_WITH_TWO_YEARS_RE.finditer(cleaned):
        add(match.group(0), False)
        if len(sessions) >= limit:
            return sessions[:limit]
    for match in OPEN_START_RE.finditer(cleaned):
        add(match.group(0), True)
        if len(sessions) >= limit:
            return sessions[:limit]
    for match in crawler.DATE_RE.finditer(cleaned):
        add(match.group(0), False)
        if len(sessions) >= limit:
            break
    return sessions[:limit]


def _location_from_block(source: dict, page: str, title: str, obj=None) -> str:
    if obj:
        loc = crawler.loc_from_obj(obj)
        if loc:
            return loc
    block = _detail_block(page, title)
    for i, line in enumerate(block):
        if crawler.DATE_RE.search(line) or OPEN_START_RE.search(line):
            for candidate in block[i + 1 : i + 8]:
                value = crawler.clean(candidate)
                if VENUE_RE.search(value) and not crawler.DATE_RE.search(value) and not TIME_RE.search(value):
                    return crawler.short(value, 120)
    return crawler.location(source, page, obj)


def _event_is_current(sessions: list[dict]) -> bool:
    dates = []
    for session in sessions:
        if session.get("ongoing"):
            return True
        dates.extend(session.get("dates") or [])
    return bool(dates and max(dates) >= crawler.TODAY - crawler.timedelta(days=crawler.PAST_GRACE))


def _best_date(sessions: list[dict]):
    for session in sessions:
        if session.get("ongoing"):
            return min(session.get("dates") or [crawler.TODAY])
    return crawler.best_date(sessions)


def _make_event(source, url, title, sessions, page, obj=None, structured=False):
    title = crawler.clean(title)
    if not title or not sessions:
        return None
    if not _event_is_current(sessions):
        return None
    if crawler.generic_title(title, url):
        return None
    if not structured and not crawler.detail(url):
        return None
    return {
        "title": crawler.short(title, 140),
        "when": crawler.when(sessions),
        "where": _location_from_block(source, page, title, obj),
        "host": source["name"],
        "source_name": source["name"],
        "url": url,
        "summary": crawler.summary(page),
        "start_date": _best_date(sessions).isoformat(),
        "kind": "event",
        "source_type": "official_registry",
        "structured": bool(structured),
    }


def _analyze(source, url, page, label=""):
    events = []

    for obj in crawler.json_objs(page):
        for node in crawler.walk(obj):
            if crawler.is_event_obj(node):
                title = crawler.clean(node.get("name") or node.get("headline") or "")
                date_text = " - ".join(
                    str(node.get(k) or "")
                    for k in ("startDate", "endDate", "doorTime", "datePublished", "description")
                )
                sessions = _sessions_from_text_smart(date_text, 4)
                event = _make_event(source, url, title, sessions, page, node, True)
                if event:
                    events.append(event)

    if events:
        return events

    title = crawler.title_of(page, label)
    sessions = _sessions_from_detail_block(page, title)
    if not sessions:
        sessions = _sessions_from_text_smart(page + " " + str(label or ""), 16)
    event = _make_event(source, url, title, sessions, page, None, False)
    return [event] if event else []


def _score(source, url, label, context):
    if not crawler.same(url, source["domains"]) or crawler.static(url):
        return -999
    parsed = crawler.urlparse(url)
    route = urllib.parse.unquote((parsed.path + " " + parsed.query).replace("-", " ").replace("_", " ")).lower()
    text = crawler.clean(str(label or "") + " " + str(context or "")[:1800]).lower()
    score = 0
    if crawler.detail(url):
        score += 80
    if crawler.listing(url):
        score += 45
    if crawler.EVENT_RE.search(route):
        score += 20
    if crawler.EVENT_RE.search(text):
        score += 20
    if crawler.DATE_RE.search(text):
        score += 25
    if crawler.CURRENT_RE.search(text) or crawler.CURRENT_RE.search(route):
        score += 25
    if any(term in text or term in route for term in crawler.LOCAL_TERMS):
        score += 8
    return score


def _main():
    crawler.old_signal = lambda url, text: False
    crawler.score = _score
    crawler.sessions_from_text = _sessions_from_text_smart
    crawler.make_event = _make_event
    crawler.analyze = _analyze

    location = " ".join(sys.argv[1:]).strip() or "Punggol Singapore"
    deadline = time.time() + crawler.MAX_SECONDS
    sources = crawler.load_sources()
    all_items = []
    debug = []
    seen = set()

    for source in sources:
        if time.time() >= deadline or len(all_items) >= crawler.MAX_TOTAL:
            break
        items, dbg = crawler.crawl(source, location, deadline)
        debug.append(dbg)
        for item in items:
            ck = crawler.canonical(item["url"])
            if ck in seen:
                continue
            seen.add(ck)
            all_items.append(item)
            if len(all_items) >= crawler.MAX_TOTAL:
                break

    all_items = crawler.sort_results(all_items, location)[: crawler.MAX_TOTAL]
    payload = {
        "ok": True,
        "version": 22,
        "extractor": "official-registry-field-locator-v22",
        "updated_at": crawler.now_iso(),
        "location": location,
        "source_registry": crawler.REG.name,
        "source_count": len(sources),
        "per_source_limit": crawler.MAX_PER_SOURCE,
        "count": len(all_items),
        "sources": [{"title": s["name"], "url": s["official_site"]} for s in sources],
        "results": all_items,
        "debug_by_source": debug,
    }
    crawler.OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
