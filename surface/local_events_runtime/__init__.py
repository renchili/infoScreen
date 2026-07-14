from __future__ import annotations

import re
from datetime import date

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds

OPEN_ENDED_DATE_RE = re.compile(r"\b(?:from|since|ongoing|permanent)\b", re.I)
OPEN_ENDED_START_RE = re.compile(r"^\s*(?:from|since|ongoing|permanent)\b", re.I)
BAD_OPEN_DATE_LINE_RE = re.compile(
    r"\b(?:entry requirements|school group visits|last admission|book your time slots?|book your tickets?)\b",
    re.I,
)
CLOSED_RANGE_RE = re.compile(r"(?:\bto\b|\buntil\b|\btill\b|[-–—])", re.I)
WEEKDAY_PREFIX_RE = re.compile(
    r"\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\s*,?\s*",
    re.I,
)
COMPLETE_DETAIL_DATE_RE = re.compile(
    r"\b20\d{2}-\d{1,2}-\d{1,2}\b|"
    + rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_extract.MONTH_WORD})[a-z]*\b|"
    + rf"\b(?:{_extract.MONTH_WORD})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b",
    re.I,
)
NARRATIVE_VENUE_RE = re.compile(
    r"\b(?:presents?|explore|discover|celebrates?|considers?|invites?|journey|exhibition|performance|live at|co-curated|with ryan|newly revamped)\b",
    re.I,
)
GARDENS_SOURCE_ID = "gardensbythebay"
GARDENS_CARD_NOISE_RE = re.compile(
    r"^(?:view details?|learn more|read more|find out more|book now|buy tickets?|admission\b.*|tickets?\b.*|free\b.*)$",
    re.I,
)
NON_EVENT_CARPARK_RE = re.compile(r"\b(?:car\s*parks?|carparks?)\b", re.I)


_original_label_dates = _extract.label_dates
_original_score_when = _extract.score_when
_original_pick_venue = _extract.pick_venue
_original_event_looks_wrong = _extract.event_looks_wrong
_original_event_from_card = _extract.event_from_card
_original_collect_events = _extract.collect_events


def _strip_weekdays(value: object) -> str:
    return _extract.clean(WEEKDAY_PREFIX_RE.sub("", str(value or "")))


def _label_dates(label: str):
    return _original_label_dates(_strip_weekdays(label))


def _open_ended_date_label(label: str) -> bool:
    text = _extract.clean(label)
    dates = _extract.label_dates(text)
    return bool(
        len(dates) == 1
        and OPEN_ENDED_START_RE.search(text)
        and not CLOSED_RANGE_RE.search(text)
        and dates[0] <= _extract.TODAY
    )


def _current_date_label(label: str) -> bool:
    dates = _extract.label_dates(label)
    if not dates:
        return False
    if _open_ended_date_label(label):
        return True
    return max(dates) >= _extract.TODAY - _extract.timedelta(days=_extract.PAST_GRACE_DAYS)


def _date_fragments(text: str) -> list[str]:
    line = _extract.clean(text)
    if BAD_OPEN_DATE_LINE_RE.search(line):
        return []

    search_line = _strip_weekdays(line)
    found: list[tuple[int, int, str]] = []
    patterns = [
        _extract.FULL_RANGE_RE,
        _extract.END_YEAR_RANGE_RE,
        _extract.SAME_MONTH_RANGE_RE,
        _extract.MONTH_FIRST_RANGE_RE,
        _extract.ISO_DATE_RE,
        _extract.TEXT_DATE_RE,
        _extract.MONTH_FIRST_DATE_RE,
    ]
    for priority, pattern in enumerate(patterns):
        for match in pattern.finditer(search_line):
            fragment = _extract.clean(match.group(0))
            candidate = fragment
            if (
                priority in {5, 6}
                and OPEN_ENDED_START_RE.search(line)
                and len(_extract.label_dates(line)) == 1
                and len(line) <= 120
            ):
                candidate = line
            if not candidate or not _extract.label_dates(candidate) or not _current_date_label(candidate):
                continue
            found.append((priority, match.start(), candidate))

    unique: list[str] = []
    for _, _, fragment in sorted(found, key=lambda item: (item[0], item[1], -len(item[2]))):
        if any(fragment != existing and fragment in existing for existing in unique):
            continue
        if fragment not in unique:
            unique.append(fragment)
    return unique


def _pick_when(card: dict) -> tuple[str, str]:
    card_lines = _extract.lines(card.get("text") or "")
    scored: list[tuple[int, str, str]] = []

    for index, line in enumerate(card_lines):
        windows = [line]
        if index + 1 < len(card_lines):
            windows.append(" ".join(card_lines[index:index + 2]))
        if index + 2 < len(card_lines):
            windows.append(" ".join(card_lines[index:index + 3]))

        for window in windows:
            if BAD_OPEN_DATE_LINE_RE.search(window):
                continue
            for fragment in _date_fragments(window):
                score = _extract.score_when(fragment, window)
                normalized = _strip_weekdays(fragment)
                if (
                    _extract.FULL_RANGE_RE.search(normalized)
                    or _extract.END_YEAR_RANGE_RE.search(normalized)
                    or _extract.SAME_MONTH_RANGE_RE.search(normalized)
                    or _extract.MONTH_FIRST_RANGE_RE.search(normalized)
                ):
                    score += 100
                scored.append((score, fragment, window))

    if not scored:
        return "", ""
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return _extract.short(scored[0][1], 180), scored[0][2]


def _candidate_title(raw: object) -> str:
    title = _extract.normalise_title(raw)
    if not title or _extract.GENERIC_TITLE_RE.match(title):
        return ""
    if _extract.DATE_LINE_RE.search(title):
        return ""
    return _extract.short(title, 140)


def _pick_title(card: dict) -> str:
    ordered: list[object] = []
    ordered.extend(card.get("headings") or [])
    ordered.append(card.get("link_text") or "")
    ordered.append(_extract.title_from_url(card.get("url") or ""))
    ordered.extend(card.get("image_alts") or [])

    for line in _extract.lines(card.get("text") or ""):
        if _extract.DATE_LINE_RE.search(line) or _extract.TIME_RE.search(line) or _extract.BAD_LINE_RE.search(line):
            continue
        if len(line) >= 4:
            ordered.append(line)

    for raw in ordered:
        title = _candidate_title(raw)
        if title:
            return title
    return ""


def _pick_venue(source: dict, card: dict, when: str, when_line: str) -> str:
    venue = _original_pick_venue(source, card, when, when_line)
    default = str(source.get("default_venue") or source.get("name") or "")
    if len(venue) > 80 or len(venue.split()) > 12 or NARRATIVE_VENUE_RE.search(venue):
        return default
    return venue


def _event_looks_wrong(source: dict, card: dict, title: str, when: str) -> str:
    url = _extract.clean(card.get("url") or "")
    text = _extract.clean(card.get("text") or "")
    combined = " ".join([title, url, text[:500]])
    if NON_EVENT_CARPARK_RE.search(combined):
        return "non_event_carpark_facility"

    reason = _original_event_looks_wrong(source, card, title, when)
    if reason:
        return reason
    source_id = _extract.clean(source.get("id") or "").lower()
    if source_id == "mandai" and "#nhb" in url:
        return "synthetic_mandai_location_card"
    return ""


def _iso_date(value: object) -> date | None:
    text = _extract.clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _gardens_closed_range(card: dict) -> tuple[str, date, date, int] | None:
    lines = _extract.lines(card.get("text") or "")
    range_patterns = (
        _extract.FULL_RANGE_RE,
        _extract.END_YEAR_RANGE_RE,
        _extract.SAME_MONTH_RANGE_RE,
        _extract.MONTH_FIRST_RANGE_RE,
    )
    candidates: list[tuple[int, int, int, str, date, date]] = []

    for start_index in range(len(lines)):
        for width in (1, 2, 3):
            end_index = start_index + width
            if end_index > len(lines):
                continue
            window = _strip_weekdays(" ".join(lines[start_index:end_index]))
            for priority, pattern in enumerate(range_patterns):
                match = pattern.search(window)
                if not match:
                    continue
                label = _extract.clean(match.group(0))
                dates = _extract.label_dates(label)
                if len(dates) < 2:
                    continue
                range_start = min(dates)
                range_end = max(dates)
                if range_end < _extract.TODAY - _extract.timedelta(days=_extract.PAST_GRACE_DAYS):
                    continue
                candidates.append((priority, width, start_index, label, range_start, range_end))

    if not candidates:
        return None
    _, width, start_index, label, range_start, range_end = min(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )
    return label, range_start, range_end, start_index + width


def _gardens_venue_after_range(card: dict, title: str, line_index: int) -> str:
    lines = _extract.lines(card.get("text") or "")
    title_key = _extract.norm_key(title)

    for line in lines[line_index:]:
        if not line or _extract.norm_key(line) == title_key:
            continue
        if _extract.DATE_LINE_RE.search(line) or _extract.TIME_RE.search(line) or _extract.BAD_LINE_RE.search(line):
            continue
        if _extract.GENERIC_TITLE_RE.match(line) or _extract.FAKE_TITLE_RE.match(line):
            continue
        if GARDENS_CARD_NOISE_RE.match(line):
            continue
        if len(line) > 80 or len(line.split()) > 10:
            continue
        return line
    return ""


def _apply_gardens_card_fields(source: dict, card: dict, event: dict) -> dict:
    if _extract.clean(source.get("id") or "").lower() != GARDENS_SOURCE_ID:
        return event

    closed_range = _gardens_closed_range(card)
    if not closed_range:
        return event

    label, range_start, range_end, next_line_index = closed_range
    repaired = dict(event)
    repaired["when"] = label
    repaired["start_date"] = range_start.isoformat()
    repaired["end_date"] = range_end.isoformat()

    venue = _gardens_venue_after_range(card, repaired.get("title") or "", next_line_index)
    if venue:
        repaired["where"] = venue
    return repaired


def _structured_event_from_card(source: dict, card: dict):
    structured = card.get("structured_event")
    if not isinstance(structured, dict):
        return None

    title = _extract.clean(structured.get("title"))
    when = _extract.clean(structured.get("when"))
    if not title:
        return None, "title_not_found"
    if not when:
        return None, "current_date_not_found_in_card"

    bad = _event_looks_wrong(source, card, title, when)
    if bad:
        return None, bad

    start = _iso_date(structured.get("start_date"))
    end = _iso_date(structured.get("end_date")) or start
    if end and end < _extract.TODAY - _extract.timedelta(days=_extract.PAST_GRACE_DAYS):
        return None, "past_date"
    if not end and not _current_date_label(when):
        return None, "past_date"

    where = _extract.clean(structured.get("where")) or str(source.get("default_venue") or source.get("name") or "")
    summary = _extract.clean(structured.get("summary")) or "Open the official page for details."
    url = _extract.clean(structured.get("url"))
    start_date = start.isoformat() if start else _extract.best_start_date(when)

    return {
        "title": title,
        "when": when,
        "where": where,
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": url,
        "summary": summary,
        "start_date": start_date,
        "end_date": end.isoformat() if end else "",
        "kind": "event",
        "source_type": "official_structured_data",
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": 0,
    }, "accepted"


def _event_from_card(source: dict, card: dict):
    structured_result = _structured_event_from_card(source, card)
    if structured_result is not None:
        return structured_result

    event, reason = _original_event_from_card(source, card)
    if not event:
        return event, reason

    when = _extract.clean(event.get("when") or "")
    if not _current_date_label(when):
        return None, "past_date"
    if len(when) > 120:
        fragments = _date_fragments(when)
        if not fragments:
            return None, "date_label_too_verbose"
        when = fragments[0]
        event = dict(event)
        event["when"] = when
        event["start_date"] = _extract.best_start_date(when)

    return _apply_gardens_card_fields(source, card, event), reason


def _score_when(fragment: str, source_line: str) -> int:
    score = _original_score_when(fragment, source_line)
    if _open_ended_date_label(fragment) or _open_ended_date_label(source_line):
        score += 45
    return score


def _render_listing_cards(source: dict, url: str, debug_dir, max_cards: int = 60):
    return _official_feeds.render_structured_first_cards(source, url, debug_dir, max_cards=max_cards)


def _source_order(payload: dict) -> dict[str, int]:
    order: dict[str, int] = {}
    for index, item in enumerate(payload.get("sources") or []):
        title = _extract.norm_key((item or {}).get("title"))
        if title and title not in order:
            order[title] = index
    return order


def _preserve_source_order(payload: dict) -> dict:
    results = payload.get("results")
    if not isinstance(results, list):
        return payload

    order = _source_order(payload)
    indexed = list(enumerate(results))

    def order_for(item: dict) -> int:
        source = _extract.norm_key((item or {}).get("source_name") or (item or {}).get("host"))
        return order.get(source, 10_000)

    def key(pair: tuple[int, dict]) -> tuple[int, int]:
        index, item = pair
        existing = item.get("source_order") if isinstance(item, dict) else None
        if isinstance(existing, int):
            return (existing, index)
        return (order_for(item), index)

    sorted_pairs = sorted(indexed, key=key)
    sorted_results = []
    for original_index, item in sorted_pairs:
        if isinstance(item, dict):
            item = dict(item)
            item["source_order"] = order_for(item)
            item["result_order"] = original_index
        sorted_results.append(item)

    payload = dict(payload)
    payload["results"] = sorted_results
    payload["order_policy"] = "event_sources_config_order"
    payload["extractor"] = f"{payload.get('extractor', 'rendered-dom-card')}-source-order"
    return payload


_browser.DETAIL_DATE_RE = COMPLETE_DETAIL_DATE_RE
_extract.label_dates = _label_dates
_extract.current_date_label = _current_date_label
_extract.date_fragments = _date_fragments
_extract.pick_when = _pick_when
_extract.score_when = _score_when
_extract.pick_title = _pick_title
_extract.pick_venue = _pick_venue
_extract.event_looks_wrong = _event_looks_wrong
_extract.event_from_card = _event_from_card
_extract.render_listing_cards = _render_listing_cards


def collect_events(*args, **kwargs):
    payload = dict(_original_collect_events(*args, **kwargs))
    payload["version"] = 49
    payload["extractor"] = "structured-first-v49"
    return _preserve_source_order(payload)


event_from_card = _extract.event_from_card
label_dates = _extract.label_dates
card_has_date = _browser.card_has_date

__all__ = ["collect_events", "event_from_card", "label_dates", "card_has_date"]