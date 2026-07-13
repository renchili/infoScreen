from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

from . import browser as _browser

DATE_WORD_RE = re.compile(
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
    re.I,
)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
WEEKDAY_RE = re.compile(
    r"\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\s*,?\s*",
    re.I,
)
NON_TEXT_RE = re.compile(r"\s+")

TITLE_KEYS = (
    "eventtitle",
    "programmetitle",
    "displaytitle",
    "cardtitle",
    "heading",
    "title",
    "name",
    "note",
)
START_KEYS = (
    "eventstartdate",
    "startdatetime",
    "startdate",
    "datefrom",
    "fromdate",
    "start",
)
END_KEYS = (
    "eventenddate",
    "enddatetime",
    "enddate",
    "dateto",
    "todate",
    "end",
)
DATE_TEXT_KEYS = (
    "daterange",
    "displaydate",
    "eventdate",
    "datetext",
    "period",
    "duration",
    "schedule",
    "date",
    "note",
)
VENUE_KEYS = (
    "venue",
    "location",
    "place",
    "where",
    "site",
    "attraction",
)
URL_KEYS = (
    "detailurl",
    "pageurl",
    "ctaurl",
    "href",
    "link",
    "url",
    "path",
)
SUMMARY_KEYS = (
    "shortdescription",
    "description",
    "summary",
    "excerpt",
    "intro",
    "subtitle",
)


def clean(value: object) -> str:
    return NON_TEXT_RE.sub(" ", str(value or "")).strip()


def key_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def scalar_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return clean(value)
    if isinstance(value, dict):
        for key in ("name", "title", "label", "value", "text", "displayName", "address"):
            if key in value:
                text = scalar_text(value.get(key))
                if text:
                    return text
        parts = [scalar_text(item) for item in list(value.values())[:8]]
        return clean(" ".join(item for item in parts if item))
    if isinstance(value, list):
        parts = [scalar_text(item) for item in value[:6]]
        return clean(" ".join(item for item in parts if item))
    return ""


def date_like(value: object) -> bool:
    text = clean(value)
    return bool(text and (ISO_DATE_RE.search(text) or DATE_WORD_RE.search(text)))


def _nested_fields(obj: dict[str, Any], depth: int = 0, parent_key: str = "") -> list[tuple[str, object]]:
    fields: list[tuple[str, object]] = []
    if depth > 2:
        return fields

    for raw_key, value in obj.items():
        key = key_name(raw_key)
        fields.append((key, value))

        if isinstance(value, dict):
            fields.extend(_nested_fields(value, depth + 1, key))
        elif isinstance(value, list) and depth < 2:
            should_descend = any(token in key for token in ("date", "time", "schedule", "venue", "location", "place"))
            if should_descend:
                for item in value[:8]:
                    if isinstance(item, dict):
                        fields.extend(_nested_fields(item, depth + 1, key))
    return fields


def first_field(fields: list[tuple[str, object]], keys: Iterable[str], *, reject_date: bool = False) -> str:
    wanted = tuple(key_name(item) for item in keys)
    for target in wanted:
        for key, value in fields:
            if key != target:
                continue
            text = scalar_text(value)
            if not text:
                continue
            if reject_date and date_like(text):
                continue
            return text
    return ""


def parse_date_value(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number).date()
        except Exception:
            return None

    text = clean(value)
    if not text:
        return None

    match = ISO_DATE_RE.search(text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except Exception:
        pass

    for fmt in (
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalized_date_text(value: object) -> str:
    text = WEEKDAY_RE.sub("", clean(value))
    text = re.sub(r"\s*([–—])\s*", " - ", text)
    text = re.sub(r"\s+-\s+", " - ", text)
    return clean(text)


def format_date(value: date) -> str:
    return f"{value.day} {value.strftime('%b')} {value.year}"


def format_date_range(start: date | None, end: date | None, fallback: str) -> str:
    if start and end:
        if start == end:
            return format_date(start)
        if start.year == end.year:
            return f"{start.day} {start.strftime('%b')} - {end.day} {end.strftime('%b')} {end.year}"
        return f"{format_date(start)} - {format_date(end)}"
    if start:
        return format_date(start)
    if end:
        return format_date(end)
    return normalized_date_text(fallback)


def iter_dicts(value: object, depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child, depth + 1)


def structured_event_from_object(obj: dict[str, Any], listing_url: str, default_venue: str) -> dict[str, Any] | None:
    fields = _nested_fields(obj)
    title = first_field(fields, TITLE_KEYS, reject_date=True)
    if not title or len(title) < 4 or len(title) > 180:
        return None

    start_raw = first_field(fields, START_KEYS)
    end_raw = first_field(fields, END_KEYS)
    date_text = first_field(fields, DATE_TEXT_KEYS)
    start = parse_date_value(start_raw)
    end = parse_date_value(end_raw)

    if not start and not end and not date_like(date_text):
        return None

    when = format_date_range(start, end, date_text)
    if not when:
        return None

    raw_url = first_field(fields, URL_KEYS)
    official_url = urljoin(listing_url, raw_url) if raw_url else listing_url
    if not official_url.startswith(("http://", "https://")):
        official_url = listing_url

    venue = first_field(fields, VENUE_KEYS) or default_venue
    summary = first_field(fields, SUMMARY_KEYS)

    return {
        "title": clean(title),
        "when": when,
        "where": clean(venue) or default_venue,
        "url": official_url,
        "summary": clean(summary),
        "start_date": start.isoformat() if start else "",
        "end_date": end.isoformat() if end else "",
    }


def extract_structured_events(payloads: Iterable[object], listing_url: str, default_venue: str, limit: int = 100) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for payload in payloads:
        for obj in iter_dicts(payload):
            event = structured_event_from_object(obj, listing_url, default_venue)
            if not event:
                continue
            key = (
                clean(event.get("title")).lower(),
                clean(event.get("start_date") or event.get("when")),
                clean(event.get("end_date")),
            )
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
            if len(events) >= limit:
                return events
    return events


def event_card(event: dict[str, Any], source_id: str, index: int) -> dict[str, Any]:
    text_lines = [
        clean(event.get("title")),
        clean(event.get("when")),
        clean(event.get("where")),
        clean(event.get("summary")),
    ]
    text_lines = [item for item in text_lines if item]
    digest = hashlib.sha1(json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "id": f"{source_id}-official-json-{index}-{digest}",
        "url": event.get("url") or "",
        "link_text": event.get("title") or "",
        "headings": [event.get("title") or ""],
        "image_alts": [],
        "text": "\n".join(text_lines),
        "text_lines": text_lines,
        "detail_url_count": 0,
        "detail_urls": [],
        "page_index": 0,
        "page_url": event.get("url") or "",
        "rect": {"x": 0, "y": 0, "width": 0, "height": 0},
        "role": "detail",
        "extraction_mode": "official_network_json",
        "structured_event": event,
        "screenshot": "",
    }


def render_official_network_cards(source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 60) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - deployment dependent
        raise _browser.MissingPlaywright("missing_playwright_python_package: python3 -m pip install --user playwright") from exc

    debug_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^a-z0-9]+", "-", str(source.get("id") or source.get("name") or "source").lower()).strip("-") or "source"
    default_venue = str(source.get("default_venue") or source.get("name") or "")
    payloads: list[object] = []
    response_urls: list[str] = []

    def capture_response(response) -> None:
        try:
            resource_type = str(response.request.resource_type or "")
            content_type = str(response.headers.get("content-type") or "").lower()
            if resource_type not in {"xhr", "fetch"} and "json" not in content_type:
                return
            data = response.json()
            if not isinstance(data, (dict, list)):
                return
            payloads.append(data)
            response_urls.append(response.url)
        except Exception:
            return

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
            page.on("response", capture_response)
            try:
                page.goto(url, wait_until="networkidle", timeout=_browser.NAV_TIMEOUT_MS)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=_browser.DOM_TIMEOUT_MS)
            page.wait_for_timeout(max(_browser.LOAD_WAIT_MS, 1200))

            pagination: list[dict[str, Any]] = []
            for page_index in range(_browser.MAX_LISTING_PAGES):
                prepare = page.evaluate(_browser.PREPARE_PAGE_JS, {"maxRounds": _browser.LOAD_MORE_ROUNDS})
                page.wait_for_timeout(600)
                page_info: dict[str, Any] = {"page_index": page_index, "url": page.url, "prepare": prepare}
                pagination.append(page_info)
                if page_index >= _browser.MAX_LISTING_PAGES - 1:
                    break
                next_result = page.evaluate(
                    _browser.CLICK_NEXT_PAGE_JS,
                    {"allowedDomains": source.get("allowed_domains") or [], "pageIndex": page_index},
                )
                page_info["next"] = next_result
                if not next_result.get("clicked"):
                    break
                try:
                    page.wait_for_load_state("networkidle", timeout=_browser.NEXT_WAIT_MS)
                except Exception:
                    page.wait_for_timeout(_browser.NEXT_WAIT_MS)
                page.wait_for_timeout(600)

            events = extract_structured_events(payloads, url, default_venue, limit=max_cards)
            cards = [event_card(event, source_id, index) for index, event in enumerate(events)]
            return {
                "ok": True,
                "url": url,
                "rendered_pages": len(pagination),
                "pagination": pagination,
                "prepare": {"official_json_responses": len(response_urls)},
                "structured_response_urls": response_urls,
                "screenshot": "",
                "screenshots": [],
                "cards": cards,
            }
        finally:
            browser.close()
