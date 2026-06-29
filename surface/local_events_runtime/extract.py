from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

from .browser import MissingPlaywright, render_listing_cards

TODAY = date.today()
MAX_SECONDS = float(os.environ.get("LOCAL_EVENTS_MAX_SECONDS", "115"))
MAX_EVENTS_PER_SOURCE = int(os.environ.get("LOCAL_EVENTS_MAX_EVENTS_PER_SOURCE", "14"))
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
FULL_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
END_YEAR_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
SAME_MONTH_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b", re.I)
TEXT_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*(20\d{{2}})?\b", re.I)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
DATE_LINE_RE = re.compile(r"\b20\d{2}-\d{1,2}-\d{1,2}\b|" + rf"\b\d{{1,2}}\s+(?:{MONTH_WORD})[a-z]*\s*(?:{SEP})?\s*\d{{0,2}}\s*(?:{MONTH_WORD})?[a-z]*\s*\d{{0,4}}\b", re.I)
TIME_RE = re.compile(r"\b(?:\d{1,2}(?::|\.)\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|daily|selected dates|all day|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.I)
BAD_LINE_RE = re.compile(r"\b(previous programme|next programme|related|recommended|last updated|newsletter|privacy|terms of use|copyright|©|cookie)\b", re.I)
GENERIC_TITLE_RE = re.compile(r"^(events?|exhibitions?(?:\s*&\s*programmes?)?|programmes?|programs?|activities?|view all|overview|what'?s on|read more|learn more|find out more|view details|details|more|book now)$", re.I)
CATEGORY_PREFIX_RE = re.compile(r"^(?:exhibitions?(?:\s*&\s*programmes?)?|programmes?|programs?|events?|activities?)\s+", re.I)
VENUE_RE = re.compile(r"\b(museum|gallery|galleries|zoo|safari|park|library|safra|punggol|waterway|mandai|level|foyer|hall|theatre|theater|room|atrium|concourse|centre|center|esplanade|kallang|stadium|arena|gardens)\b", re.I)
VENUE_PHRASE_RE = re.compile(
    r"\b(?:(?:B\d+|L\d+|Level\s*\d+|Basement\s*\d+)\s+)?"
    r"[A-Z][A-Za-z0-9&,'’()\-/ ]{0,80}?"
    r"(?:Gallery|Galleries|Room|Hall|Theatre|Theater|Foyer|Atrium|Concourse|Library|Museum|Park|Zoo|Safari|Centre|Center|Stadium|Arena|Gardens)"
    r"(?:\s+[A-Z][A-Za-z0-9&,'’()\-/ ]{0,30})?\b",
    re.I,
)
SUMMARY_START_RE = re.compile(r"\b(?:Embark|Join|Discover|Explore|Experience|Learn|Enjoy|Celebrate|Step|Take|Find|Visit|Come|Uncover|Journey|Be part|Catch|Watch)\b", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object) -> str:
    text = html.unescape(str(value or "")).replace("\\/", "/").replace("\\u002F", "/")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r", "\n")
    return [clean(item) for item in raw.split("\n") if clean(item)]


def norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def semantic_key(event: dict[str, Any]) -> str:
    return "|".join([
        norm_key(event.get("source_name")),
        norm_key(event.get("title")),
        norm_key(event.get("when")),
    ])


def short(value: object, limit: int) -> str:
    text = clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_date(day: str, month_name: str, year: str | int | None = None) -> date | None:
    month = MONTHS.get(str(month_name).lower()[:3])
    if not month:
        return None
    full_year = int(year) if year else TODAY.year
    try:
        return date(full_year, month, int(day))
    except ValueError:
        return None


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
        add(parse_date(d1, m1, y1)); add(parse_date(d2, m2, y2))
    for d1, m1, d2, m2, y in END_YEAR_RANGE_RE.findall(text):
        add(parse_date(d1, m1, y)); add(parse_date(d2, m2, y))
    for d1, d2, m, y in SAME_MONTH_RANGE_RE.findall(text):
        year = y or inherited
        add(parse_date(d1, m, year)); add(parse_date(d2, m, year))
    for d, m, y in TEXT_DATE_RE.findall(text):
        year = y or inherited
        add(parse_date(d, m, year))
    for y, m, d in ISO_DATE_RE.findall(text):
        try:
            add(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return sorted(out)


def current_date_label(label: str) -> bool:
    dates = label_dates(label)
    return bool(dates and max(dates) >= TODAY - timedelta(days=PAST_GRACE_DAYS))


def best_start_date(label: str) -> str:
    dates = label_dates(label)
    future = [item for item in dates if item >= TODAY - timedelta(days=PAST_GRACE_DAYS)]
    return (min(future or dates or [TODAY])).isoformat()


def title_from_url(url: str) -> str:
    leaf = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
    leaf = re.sub(r"\.html$", "", leaf)
    parts = [part for part in re.split(r"[-_]+", leaf) if part and not part.isdigit()]
    return " ".join(part.capitalize() for part in parts)


def normalise_title(raw: object) -> str:
    title = clean(raw)
    title = re.sub(r"^(previous programme|next programme)\s+", "", title, flags=re.I)
    title = CATEGORY_PREFIX_RE.sub("", title)
    return clean(title)


def date_fragments(text: str) -> list[str]:
    found: list[tuple[int, int, str]] = []
    patterns = [FULL_RANGE_RE, END_YEAR_RANGE_RE, SAME_MONTH_RANGE_RE, ISO_DATE_RE, TEXT_DATE_RE]
    for priority, pattern in enumerate(patterns):
        for match in pattern.finditer(text):
            frag = clean(match.group(0))
            if not frag or not label_dates(frag) or not current_date_label(frag):
                continue
            found.append((priority, match.start(), frag))
    unique: list[str] = []
    for _, _, frag in sorted(found, key=lambda item: (item[0], item[1], -len(item[2]))):
        if any(frag != existing and frag in existing for existing in unique):
            continue
        if frag not in unique:
            unique.append(frag)
    return unique


def score_when(fragment: str, source_line: str) -> int:
    score = 10
    if re.search(r"\b20\d{2}\b", fragment):
        score += 35
    if FULL_RANGE_RE.search(fragment) or END_YEAR_RANGE_RE.search(fragment):
        score += 60
    if TIME_RE.search(source_line):
        score += 8
    return score


def pick_title(card: dict[str, Any]) -> str:
    candidates: list[str] = []
    candidates.extend(card.get("headings") or [])
    candidates.extend(card.get("image_alts") or [])
    candidates.append(card.get("link_text") or "")
    for line in lines(card.get("text") or ""):
        if DATE_LINE_RE.search(line) or TIME_RE.search(line) or BAD_LINE_RE.search(line):
            continue
        if len(line) < 4:
            continue
        candidates.append(line)
    candidates.append(title_from_url(card.get("url") or ""))

    for raw in candidates:
        title = normalise_title(raw)
        if title and not GENERIC_TITLE_RE.match(title):
            return short(title, 140)
    return ""


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
    scored: list[tuple[int, str, str]] = []
    for line in lines(card.get("text") or ""):
        if BAD_LINE_RE.search(line):
            continue
        for fragment in date_fragments(line):
            scored.append((score_when(fragment, line), fragment, line))
    if not scored:
        return "", ""
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return short(scored[0][1], 180), scored[0][2]


def find_after(text: str, needle: str) -> str:
    if not needle:
        return ""
    idx = clean(text).lower().find(clean(needle).lower())
    if idx < 0:
        return ""
    return clean(text)[idx + len(clean(needle)):]


def pick_venue(source: dict[str, Any], card: dict[str, Any], when: str, when_line: str) -> str:
    candidates: list[str] = []
    tails = []
    if when_line:
        tails.append(find_after(when_line, when) or when_line)
    for line in lines(card.get("text") or ""):
        if line == when_line:
            continue
        if DATE_LINE_RE.search(line) or TIME_RE.search(line):
            continue
        tails.append(line)

    for text in tails:
        for match in VENUE_PHRASE_RE.finditer(text):
            phrase = short(match.group(0), 140)
            if phrase and not DATE_LINE_RE.search(phrase):
                candidates.append(phrase)
    for line in tails:
        if VENUE_RE.search(line) and not DATE_LINE_RE.search(line):
            candidates.append(short(line, 140))
    if candidates:
        candidates.sort(key=lambda item: (len(item), item))
        return candidates[0]
    return str(source.get("default_venue") or source.get("name") or "")


def remove_known_prefixes(text: str, title: str, when: str, where: str) -> str:
    value = clean(text)
    for token in (title, when, where):
        tail = find_after(value, token)
        if tail and len(tail) >= 20:
            value = tail
    match = SUMMARY_START_RE.search(value)
    if match:
        value = value[match.start():]
    value = re.sub(r"^(?:view details|learn more|read more|book now)\b", "", value, flags=re.I).strip(" -–—|•")
    return clean(value)


def pick_summary(card: dict[str, Any], title: str, when: str, where: str) -> str:
    text = card.get("text") or ""
    collapsed = clean(text)
    focused = remove_known_prefixes(collapsed, title, when, where)
    if len(focused) >= 30:
        return short(focused, 260)

    for line in lines(text):
        if BAD_LINE_RE.search(line):
            continue
        if title and title.lower() in line.lower():
            continue
        if when and when.lower() in line.lower():
            continue
        if where and where.lower() in line.lower():
            continue
        if DATE_LINE_RE.search(line) or GENERIC_TITLE_RE.match(line):
            continue
        if len(line) >= 35:
            return short(line, 260)
    return "Open the official page for details."


def event_from_card(source: dict[str, Any], card: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    title = pick_title(card)
    when, when_line = pick_when(card)
    if not title:
        return None, "title_not_found"
    if not when:
        return None, "current_date_not_found_in_card"
    where = pick_venue(source, card, when, when_line)
    summary = pick_summary(card, title, when, where)
    url = card.get("url") or ""
    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": url,
        "summary": summary,
        "start_date": best_start_date(when),
        "kind": "event",
        "source_type": "rendered_dom_card",
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": card.get("detail_url_count", 0),
    }, "accepted"


def bump(debug: dict[str, Any], reason: str) -> None:
    counts = debug.setdefault("reason_counts", {})
    counts[reason] = counts.get(reason, 0) + 1


def collect_source(source: dict[str, Any], debug_dir: Path, deadline: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    debug: dict[str, Any] = {
        "source": source.get("name"),
        "adapter": "rendered_dom_card",
        "listing_urls": source.get("listing_urls") or [],
        "listing_fetched": 0,
        "cards_found": 0,
        "accepted": 0,
        "accepted_preview": [],
        "not_output_preview": [],
        "reason_counts": {},
        "screenshots": [],
    }
    accepted: list[dict[str, Any]] = []
    seen = set()
    semantic_seen = set()

    for listing_url in source.get("listing_urls") or []:
        if time.time() >= deadline or len(accepted) >= MAX_EVENTS_PER_SOURCE:
            break
        try:
            rendered = render_listing_cards(source, listing_url, debug_dir)
        except MissingPlaywright as exc:
            reason = str(exc)
            bump(debug, reason)
            debug["not_output_preview"].append({"url": listing_url, "reason": reason})
            continue
        except Exception as exc:
            reason = f"render_error:{type(exc).__name__}:{exc}"
            bump(debug, f"render_error:{type(exc).__name__}")
            debug["not_output_preview"].append({"url": listing_url, "reason": reason})
            continue

        debug["listing_fetched"] += 1
        if rendered.get("prepare"):
            debug["prepare"] = rendered.get("prepare")
        if rendered.get("screenshot"):
            debug["screenshots"].append(rendered["screenshot"])
        cards = rendered.get("cards") or []
        debug["cards_found"] += len(cards)

        for card in cards:
            if len(accepted) >= MAX_EVENTS_PER_SOURCE:
                break
            key = card.get("url") or ""
            if not key or key in seen:
                continue
            seen.add(key)
            event, reason = event_from_card(source, card)
            if event:
                skey = semantic_key(event)
                if skey in semantic_seen:
                    bump(debug, "duplicate_semantic_event")
                    if len(debug["not_output_preview"]) < 30:
                        debug["not_output_preview"].append({"url": card.get("url"), "link_text": card.get("link_text"), "reason": "duplicate_semantic_event", "title": event.get("title"), "when": event.get("when"), "detail_url_count": card.get("detail_url_count")})
                    continue
                semantic_seen.add(skey)
            bump(debug, reason)
            if event:
                accepted.append(event)
                debug["accepted_preview"].append({"title": event["title"], "url": event["url"], "when": event["when"], "where": event["where"], "detail_url_count": event.get("debug_detail_url_count")})
            elif len(debug["not_output_preview"]) < 30:
                debug["not_output_preview"].append({"url": card.get("url"), "link_text": card.get("link_text"), "reason": reason, "screenshot": card.get("screenshot"), "detail_url_count": card.get("detail_url_count")})

    debug["accepted"] = len(accepted)
    return accepted, debug


def local_score(item: dict[str, Any], location: str) -> int:
    text = " ".join(str(item.get(key, "")) for key in ("title", "where", "summary", "source_name")).lower()
    terms = [term for term in re.split(r"[^a-z0-9]+", location.lower()) if len(term) >= 3]
    return sum(1 for term in terms if term in text)


def git_head(config_path: Path) -> str:
    try:
        root = config_path.resolve().parents[1]
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def runtime_info(config_path: Path) -> dict[str, Any]:
    return {
        "writer": "surface.local_events_runtime.extract.collect_events",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "python": sys.executable,
        "module_file": __file__,
        "git_head": git_head(config_path),
    }


def collect_events(config_path: Path, location: str, debug_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    deadline = time.time() + MAX_SECONDS
    all_items: list[dict[str, Any]] = []
    debug = []
    seen = set()
    semantic_seen = set()

    for source in config.get("sources") or []:
        if time.time() >= deadline or len(all_items) >= MAX_TOTAL_EVENTS:
            break
        items, source_debug = collect_source(source, debug_dir, deadline)
        debug.append(source_debug)
        for item in items:
            key = item.get("url") or ""
            skey = semantic_key(item)
            if not key or key in seen or skey in semantic_seen:
                continue
            seen.add(key)
            semantic_seen.add(skey)
            all_items.append(item)
            if len(all_items) >= MAX_TOTAL_EVENTS:
                break

    all_items.sort(key=lambda item: (-local_score(item, location), str(item.get("source_name", "")), str(item.get("start_date", "")), str(item.get("title", ""))))
    return {
        "ok": True,
        "version": 41,
        "extractor": "rendered-dom-card-v41",
        "updated_at": now_iso(),
        "location": location,
        "runtime": runtime_info(config_path),
        "event_source_config": config_path.name,
        "source_count": len(config.get("sources") or []),
        "count": len(all_items),
        "sources": [{"title": item.get("name"), "url": item.get("official_home")} for item in config.get("sources") or []],
        "results": all_items,
        "debug_by_source": debug,
    }
