from __future__ import annotations

import re

from . import extract as _extract

OPEN_ENDED_DATE_RE = re.compile(r"\b(?:from|since|ongoing|permanent)\b", re.I)
BAD_OPEN_DATE_LINE_RE = re.compile(
    r"\b(?:entry requirements|school group visits|last admission|book your time slots?|book your tickets?)\b",
    re.I,
)


def _open_ended_date_label(label: str) -> bool:
    text = _extract.clean(label)
    dates = _extract.label_dates(text)
    return bool(dates and OPEN_ENDED_DATE_RE.search(text) and min(dates) <= _extract.TODAY)


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

    found: list[tuple[int, int, str]] = []
    patterns = [
        _extract.FULL_RANGE_RE,
        _extract.END_YEAR_RANGE_RE,
        _extract.SAME_MONTH_RANGE_RE,
        _extract.ISO_DATE_RE,
        _extract.TEXT_DATE_RE,
    ]
    for priority, pattern in enumerate(patterns):
        for match in pattern.finditer(line):
            fragment = _extract.clean(match.group(0))
            candidate = line if priority == 4 and OPEN_ENDED_DATE_RE.search(line) and len(line) <= 220 else fragment
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


_original_score_when = _extract.score_when
_original_collect_events = _extract.collect_events


def _score_when(fragment: str, source_line: str) -> int:
    score = _original_score_when(fragment, source_line)
    if OPEN_ENDED_DATE_RE.search(fragment) or OPEN_ENDED_DATE_RE.search(source_line):
        score += 45
    return score


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


_extract.current_date_label = _current_date_label
_extract.date_fragments = _date_fragments
_extract.score_when = _score_when


def collect_events(*args, **kwargs):
    return _preserve_source_order(_original_collect_events(*args, **kwargs))


__all__ = ["collect_events"]
