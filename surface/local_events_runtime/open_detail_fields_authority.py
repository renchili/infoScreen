from __future__ import annotations

import re
from typing import Any

from . import browser as _browser
from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_membership_authority as _membership
from . import source_overrides as _source_overrides

_APPLIED = False
_BASE_CANDIDATE_EXPIRED = None
_BASE_EXPLICIT_VENUE = None
_BASE_PICK_WHEN = None
_BASE_PICK_VENUE = None

_EXPLICIT_YEAR_RE = re.compile(r"\b20\d{2}\b")
_VENUE_HINT_RE = re.compile(
    r"\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|"
    r"auditorium|atrium|foyer|lobby|library|centre|center|park|gardens?|zoo)\b",
    re.I,
)
_NON_VENUE_RE = re.compile(
    r"^(?:admission|ticket|tickets|free|paid|book|register|programme|program|"
    r"event|events|exhibition|exhibitions|terms?|conditions?|last updated|"
    r"in[-\s]?gallery|in[-\s]?museum|outdoor(?: installation| performances?)?|"
    r"performances?|drop-in(?: activities| experiences)?|registered programmes?|"
    r"exclusive promotion|giveaway)\b",
    re.I,
)
_SUMMARY_SORT_OLD = (
    "summaryRows.sort((left, right) => right.score - left.score || "
    "left.text.length - right.text.length);"
)
_SUMMARY_SORT_NEW = "summaryRows.sort((left, right) => right.score - left.score);"


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        return [_extract.clean(value) for value in raw if _extract.clean(value)]
    return _extract.lines(card.get("text") or "")


def _detail_date_rows(card: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for value in card.get("detail_dates") or []:
        text = _extract.clean(value)
        if text and text not in rows:
            rows.append(text)
    evidence = card.get("detail_evidence")
    if isinstance(evidence, dict):
        for value in evidence.get("date_candidates") or []:
            text = _extract.clean(value)
            if text and text not in rows:
                rows.append(text)
    return rows


def _primary_detail_date(card: dict[str, Any]) -> str:
    """Choose the first explicit-year activity range, never the busiest child row."""

    dated: list[tuple[int, str, list[Any], bool]] = []
    for index, row in enumerate(_detail_date_rows(card)):
        parsed = _extract.label_dates(row)
        if parsed:
            dated.append((index, row, parsed, bool(_EXPLICIT_YEAR_RE.search(row))))

    explicit_ranges = [item for item in dated if item[3] and len(item[2]) >= 2]
    if explicit_ranges:
        return explicit_ranges[0][1]

    explicit_singles = [item for item in dated if item[3] and len(item[2]) == 1]
    if len(explicit_singles) >= 2:
        first, second = explicit_singles[:2]
        if second[0] == first[0] + 1:
            start = min(first[2][0], second[2][0])
            end = max(first[2][0], second[2][0])
            return f"{start.day} {start.strftime('%b')} {start.year} – {end.day} {end.strftime('%b')} {end.year}"
    if explicit_singles:
        return explicit_singles[0][1]

    ranges = [item for item in dated if len(item[2]) >= 2]
    if ranges:
        return ranges[0][1]
    return dated[0][1] if dated else ""


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
    """Prefer the parent activity's first explicit-year date over child schedules."""

    primary = _primary_detail_date(card)
    if primary:
        return _extract.short(primary, 180), primary
    return _BASE_PICK_WHEN(card)


def _valid_venue(value: object) -> bool:
    text = _extract.clean(value)
    if not text or len(text) > 180 or len(text.split()) > 24:
        return False
    if _NON_VENUE_RE.search(text):
        return False
    if _extract.DATE_LINE_RE.search(text) or _extract.TIME_RE.fullmatch(text):
        return False
    return bool(_VENUE_HINT_RE.search(text))


def pick_venue(
    source: dict[str, Any],
    card: dict[str, Any],
    when: str,
    when_line: str,
) -> str:
    """Reject programme taxonomy such as ``In-gallery`` as a physical venue."""

    venue = _extract.clean(_BASE_PICK_VENUE(source, card, when, when_line))
    if _valid_venue(venue):
        return venue
    return _extract.clean(source.get("default_venue") or source.get("name"))


def explicit_venue(card: dict[str, Any]) -> str:
    """Recognise a real unlabelled venue line in an official detail document."""

    venue = _extract.clean(_BASE_EXPLICIT_VENUE(card))
    if _valid_venue(venue):
        return venue

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(_card_lines(card)):
        if not _valid_venue(line):
            continue

        score = 0
        if re.search(r"\bmuseum\b", line, re.I):
            score += 200
        if re.search(r"\b(?:gallery|galleries)\b", line, re.I):
            score += 100
        if re.search(r"\blevel\s+\d+\b", line, re.I):
            score += 80
        if re.search(r"\b\d{5,6}\b", line):
            score += 50
        score -= min(index, 50)
        candidates.append((score, -len(line), line))

    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def candidate_expired(candidate: Any) -> bool:
    """Never expire an explicit ongoing/start-only schedule by its start date."""

    when = _extract.clean(getattr(candidate, "when", ""))
    if when and _extract.current_date_label(when):
        return False
    return bool(_BASE_CANDIDATE_EXPIRED(candidate))


def _patched_summary_script(script: str) -> str:
    if _SUMMARY_SORT_OLD in script:
        return script.replace(_SUMMARY_SORT_OLD, _SUMMARY_SORT_NEW, 1)
    if _SUMMARY_SORT_NEW not in script:
        raise RuntimeError("detail_summary_order_patch_missing")
    return script


def _patch_detail_summary_order() -> None:
    """Keep the first equally scored primary paragraph ahead of later child text."""

    _detail_dates.ACTIVITY_DETAIL_JS = _patched_summary_script(
        _detail_dates.ACTIVITY_DETAIL_JS
    )
    _browser.DETAIL_CARD_JS = _patched_summary_script(_browser.DETAIL_CARD_JS)
    _source_overrides.AUTHORITATIVE_DETAIL_JS = _patched_summary_script(
        _source_overrides.AUTHORITATIVE_DETAIL_JS
    )


def apply() -> None:
    """Install shared primary-date, lifecycle, venue, and summary repairs."""

    global _APPLIED, _BASE_CANDIDATE_EXPIRED, _BASE_EXPLICIT_VENUE
    global _BASE_PICK_WHEN, _BASE_PICK_VENUE
    if _APPLIED:
        return

    _BASE_CANDIDATE_EXPIRED = _detail_dates._candidate_expired
    _BASE_EXPLICIT_VENUE = _membership._explicit_venue
    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_PICK_VENUE = _extract.pick_venue

    _patch_detail_summary_order()
    _extract.pick_when = pick_when
    _extract.pick_venue = pick_venue
    _detail_dates._candidate_expired = candidate_expired
    _membership._explicit_venue = explicit_venue
    _APPLIED = True


__all__ = [
    "apply",
    "candidate_expired",
    "explicit_venue",
    "pick_venue",
    "pick_when",
    "_patch_detail_summary_order",
    "_primary_detail_date",
]
