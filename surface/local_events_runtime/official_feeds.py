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
EVENT_TYPE_RE = re.compile(r"\b(?:event|programme|program|exhibition|activity|workshop|festival|performance|concert|talk|tour)\b", re.I)
NON_TEXT_RE = re.compile(r"\s+")
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTH_WORD = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december"
SEP = r"(?:-|–|—|to|until|till)"
FULL_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
END_YEAR_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
SAME_MONTH_RANGE_RE = re.compile(rf"\b(\d{{1,2}})\s*{SEP}\s*(\d{{1,2}})\s+({MONTH_WORD})[a-z]*\s+(20\d{{2}})\b", re.I)
MONTH_FIRST_RANGE_RE = re.compile(rf"\b({MONTH_WORD})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP}\s*(?:({MONTH_WORD})[a-z]*\.?\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?\s+(20\d{{2}})\b", re.I)

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
TYPE_KEYS = ("@type", "type", "contenttype", "itemtype")
WRAPPER_KEYS = {"attributes", "fields", "properties", "data", "item", "content"}

EMBEDDED_JSON_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  function add(origin, value) {
    if (!value || typeof value !== "object") return;
    try {
      const raw = JSON.stringify(value);
      if (!raw || raw.length < 20 || raw.length > 1500000) return;
      const key = origin + "\n" + raw.slice(0, 800);
      if (seen.has(key)) return;
      seen.add(key);
      out.push({origin, value: JSON.parse(raw)});
    } catch (e) {}
  }

  for (const script of Array.from(document.querySelectorAll("script"))) {
    const type = String(script.getAttribute("type") || "").toLowerCase();
    const id = String(script.id || "").toLowerCase();
    const raw = String(script.textContent || "").trim();
    if (!raw || raw.length < 20 || raw.length > 1500000) continue;
    if (!(type.includes("json") || id === "__next_data__" || id.includes("state") || id.includes("data"))) continue;
    try { add("script:" + (id || type || "json"), JSON.parse(raw)); } catch (e) {}
  }

  const globals = [
    "__NEXT_DATA__",
    "__NUXT__",
    "__APOLLO_STATE__",
    "__INITIAL_STATE__",
    "__PRELOADED_STATE__",
    "__INITIAL_DATA__"
  ];
  for (const name of globals) {
    try { add("window:" + name, window[name]); } catch (e) {}
  }
  return out.slice(0, 100);
}
"""


def clean(value: object) -> str:
    return NON_TEXT_RE.sub(" ", str(value or "")).strip()


def key_name(value: object) -> str:
    text = str(value or "").lower().strip()
    if text == "@type":
        return "@type"
    return re.sub(r"[^a-z0-9]+", "", text)


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
    if isinstance(value, list):
        parts = [scalar_text(item) for item in value[:6]]
        return clean(" ".join(item for item in parts if item))
    return ""


def object_fields(obj: dict[str, Any]) -> list[tuple[str, object]]:
    fields: list[tuple[str, object]] = []
    for raw_key, value in obj.items():
        key = key_name(raw_key)
        fields.append((key, value))
        if key in WRAPPER_KEYS and isinstance(value, dict):
            fields.extend((key_name(child_key), child_value) for child_key, child_value in value.items())
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


def field_present(fields: list[tuple[str, object]], keys: Iterable[str]) -> bool:
    wanted = {key_name(item) for item in keys}
    return any(key in wanted and scalar_text(value) for key, value in fields)


def date_like(value: object) -> bool:
    text = clean(value)
    return bool(text and (ISO_DATE_RE.search(text) or DATE_WORD_RE.search(text)))


def parse_date_parts(day: str, month_name: str, year: str | int) -> date | None:
    month = MONTHS.get(str(month_name).lower()[:3])
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def normalized_date_text(value: object) -> str:
    text = WEEKDAY_RE.sub("", clean(value))
    text = re.sub(r"\s*([–—])\s*", " - ", text)
    text = re.sub(r"\s+-\s+", " - ", text)
    return clean(text)


def parse_text_range(value: object) -> tuple[date | None, date | None]:
    text = normalized_date_text(value)
    match = FULL_RANGE_RE.search(text)
    if match:
        return (
            parse_date_parts(match.group(1), match.group(2), match.group(3)),
            parse_date_parts(match.group(4), match.group(5), match.group(6)),
        )
    match = END_YEAR_RANGE_RE.search(text)
    if match:
        year = match.group(5)
        return (
            parse_date_parts(match.group(1), match.group(2), year),
            parse_date_parts(match.group(3), match.group(4), year),
        )
    match = SAME_MONTH_RANGE_RE.search(text)
    if match:
        return (
            parse_date_parts(match.group(1), match.group(3), match.group(4)),
            parse_date_parts(match.group(2), match.group(3), match.group(4)),
        )
    match = MONTH_FIRST_RANGE_RE.search(text)
    if match:
        start_month = match.group(1)
        end_month = match.group(3) or start_month
        return (
            parse_date_parts(match.group(2), start_month, match.group(5)),
            parse_date_parts(match.group(4), end_month, match.group(5)),
        )
    return None, None


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
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


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


def explicit_event_type(fields: list[tuple[str, object]]) -> bool:
    type_text = " ".join(first_field(fields, (key,)) for key in TYPE_KEYS)
    return bool(EVENT_TYPE_RE.search(type_text))


def structured_event_from_object(obj: dict[str, Any], listing_url: str, default_venue: str) -> dict[str, Any] | None:
    fields = object_fields(obj)
    title = first_field(fields, TITLE_KEYS, reject_date=True)
    if not title or len(title) < 4 or len(title) > 180:
        return None

    has_explicit_date_field = field_present(fields, START_KEYS + END_KEYS + DATE_TEXT_KEYS)
    if not has_explicit_date_field:
        return None
    if not explicit_event_type(fields) and not field_present(fields, START_KEYS + END_KEYS):
        date_text_probe = first_field(fields, DATE_TEXT_KEYS)
        if not date_like(date_text_probe):
            return None

    start_raw = first_field(fields, START_KEYS)
    end_raw = first_field(fields, END_KEYS)
    date_text = first_field(fields, DATE_TEXT_KEYS)
    start = parse_date_value(start_raw)
    end = parse_date_value(end_raw)
    range_start, range_end = parse_text_range(date_text)
    start = start or range_start
    end = end or range_end

    if not start and not end and not date_like(date_text):
        return None
    when = format_date_range(start, end, date_text)
    if not when:
        return None

    raw_url = first_field(fields, URL_KEYS)
    if raw_url:
        official_url = urljoin(listing_url, raw_url)
    else:
        digest = hashlib.sha1(f"{title}|{when}".encode("utf-8")).hexdigest()[:12]
        official_url = f"{listing_url.split('#', 1)[0]}#structured-{digest}"
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
    text_lines = [clean(event.get("title")), clean(event.get("when")), clean(event.get("where")), clean(event.get("summary"))]
    text_lines = [item for item in text_lines if item]
    digest = hashlib.sha1(json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "id": f"{source_id}-structured-{index}-{digest}",
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
        "extraction_mode": "official_structured_data",
        "structured_event": event,
        "screenshot": "",
    }


def card_title(card: dict[str, Any]) -> str:
    for value in (card.get("link_text"), *(card.get("headings") or [])):
        title = clean(value).lower()
        if title:
            return re.sub(r"[^a-z0-9]+", " ", title).strip()
    return ""


def prefer_structured_cards(structured_cards: list[dict[str, Any]], dom_cards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    structured_titles = {card_title(card) for card in structured_cards if card_title(card)}
    merged = list(structured_cards)
    for card in dom_cards:
        title = card_title(card)
        if title and title in structured_titles:
            continue
        merged.append(card)
        if len(merged) >= limit:
            break
    return merged[:limit]


def render_structured_first_cards(source: dict[str, Any], url: str, debug_dir: Path, max_cards: int = 60) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - deployment dependent
        raise _browser.MissingPlaywright("missing_playwright_python_package: python3 -m pip install --user playwright") from exc

    debug_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^a-z0-9]+", "-", str(source.get("id") or source.get("name") or "source").lower()).strip("-") or "source"
    default_venue = str(source.get("default_venue") or source.get("name") or "")
    allowed = [str(item).lower().replace("www.", "") for item in source.get("allowed_domains") or []]
    adapter = str(source.get("adapter") or "rendered_dom_card")
    official_home = str(source.get("official_home") or "")
    load_more_rounds = int(source.get("load_more_rounds", 1 if adapter == "nhb" else _browser.LOAD_MORE_ROUNDS))

    pending_responses: list[Any] = []
    drained_response_count = 0
    network_payloads: list[object] = []
    network_urls: list[str] = []
    network_errors = 0
    embedded_payloads: list[object] = []
    embedded_signatures: set[str] = set()
    embedded_origins: list[str] = []

    def record_response(response) -> None:
        if len(pending_responses) >= 300:
            return
        try:
            resource_type = str(response.request.resource_type or "")
            content_type = str(response.headers.get("content-type") or "").lower()
            if resource_type in {"xhr", "fetch"} or "json" in content_type:
                pending_responses.append(response)
        except Exception:
            return

    def drain_network_payloads() -> None:
        nonlocal drained_response_count, network_errors
        while drained_response_count < len(pending_responses) and len(network_payloads) < 200:
            response = pending_responses[drained_response_count]
            drained_response_count += 1
            try:
                data = response.json()
                if not isinstance(data, (dict, list)):
                    continue
                network_payloads.append(data)
                network_urls.append(response.url)
            except Exception:
                network_errors += 1

    with sync_playwright() as playwright:
        browser = _browser.launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
            page.on("response", record_response)
            try:
                page.goto(url, wait_until="networkidle", timeout=_browser.NAV_TIMEOUT_MS)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=_browser.DOM_TIMEOUT_MS)
            page.wait_for_timeout(max(_browser.LOAD_WAIT_MS, 1200))
            drain_network_payloads()

            all_cards: list[dict[str, Any]] = []
            seen_cards: set[str] = set()
            screenshots: list[str] = []
            pagination: list[dict[str, Any]] = []
            rendered_pages = 0

            for page_index in range(_browser.MAX_LISTING_PAGES):
                prepare = page.evaluate(_browser.PREPARE_PAGE_JS, {"maxRounds": load_more_rounds})
                page.wait_for_timeout(600)
                drain_network_payloads()

                for item in page.evaluate(EMBEDDED_JSON_JS) or []:
                    if not isinstance(item, dict) or not isinstance(item.get("value"), (dict, list)):
                        continue
                    origin = clean(item.get("origin"))
                    signature = origin + "\n" + json.dumps(item["value"], ensure_ascii=False, sort_keys=True)[:600]
                    if signature in embedded_signatures:
                        continue
                    embedded_signatures.add(signature)
                    embedded_origins.append(origin)
                    embedded_payloads.append(item["value"])

                events = extract_structured_events(
                    [*network_payloads, *embedded_payloads],
                    url,
                    default_venue,
                    limit=max_cards,
                )
                structured_cards = [event_card(event, source_id, index) for index, event in enumerate(events)]

                dom_cards = page.evaluate(
                    _browser.CARD_JS,
                    {
                        "allowedDomains": allowed,
                        "maxCards": max_cards,
                        "sourceId": source_id,
                        "pageIndex": page_index,
                        "adapter": adapter,
                        "officialHome": official_home,
                    },
                )
                if adapter == "nhb":
                    dom_cards = _browser.enrich_nhb_detail_cards(browser, dom_cards)
                page_cards = prefer_structured_cards(structured_cards, dom_cards, max_cards)

                if _browser.PAGE_SCREENSHOTS:
                    screenshot = debug_dir / f"{source_id}-{hashlib.sha1((url + str(page_index)).encode()).hexdigest()[:10]}-page-{page_index}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    screenshots.append(str(screenshot))

                rendered_pages += 1
                new_count = 0
                for card in page_cards:
                    key = (card.get("url") or "") + "\n" + (card.get("text") or "")[:500]
                    if not key.strip() or key in seen_cards:
                        continue
                    seen_cards.add(key)
                    all_cards.append(card)
                    new_count += 1
                    if len(all_cards) >= max_cards:
                        break

                pagination.append(
                    {
                        "page_index": page_index,
                        "url": page.url,
                        "prepare": prepare,
                        "cards": len(page_cards),
                        "new_cards": new_count,
                        "structured_cards": len(structured_cards),
                        "dom_cards": len(dom_cards),
                    }
                )
                if len(all_cards) >= max_cards or page_index >= _browser.MAX_LISTING_PAGES - 1:
                    break

                next_result = page.evaluate(_browser.CLICK_NEXT_PAGE_JS, {"allowedDomains": allowed, "pageIndex": page_index})
                pagination[-1]["next"] = next_result
                if not next_result.get("clicked"):
                    break
                try:
                    page.wait_for_load_state("networkidle", timeout=_browser.NEXT_WAIT_MS)
                except Exception:
                    page.wait_for_timeout(_browser.NEXT_WAIT_MS)
                page.wait_for_timeout(600)
                drain_network_payloads()

            structured_debug = {
                "network_candidate_response_count": len(pending_responses),
                "network_payload_count": len(network_payloads),
                "network_parse_errors": network_errors,
                "network_response_urls": network_urls,
                "embedded_payload_count": len(embedded_payloads),
                "embedded_origins": embedded_origins,
                "event_count": sum(1 for card in all_cards if card.get("structured_event")),
                "fallback_dom_used": any(not card.get("structured_event") for card in all_cards),
            }
            return {
                "ok": True,
                "url": url,
                "rendered_pages": rendered_pages,
                "pagination": pagination,
                "prepare": {"structured": structured_debug},
                "screenshot": screenshots[0] if screenshots else "",
                "screenshots": screenshots,
                "cards": all_cards,
                "structured": structured_debug,
            }
        finally:
            browser.close()
