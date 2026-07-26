from __future__ import annotations

import re
from typing import Any

from . import detail_date_authority as _detail_dates
from . import extract as _extract
from . import listing_membership_authority as _membership

_APPLIED = False
_BASE_CANDIDATE_EXPIRED = None
_BASE_EXPLICIT_VENUE = None

_VENUE_HINT_RE = re.compile(
    r"\b(?:museum|gallery|galleries|level|room|hall|theatre|theater|"
    r"auditorium|atrium|foyer|lobby|library|centre|center|park|gardens?|zoo)\b",
    re.I,
)
_NON_VENUE_RE = re.compile(
    r"^(?:admission|ticket|tickets|free|paid|book|register|programme|program|"
    r"event|events|exhibition|exhibitions|terms?|conditions?|last updated)\b",
    re.I,
)


def _card_lines(card: dict[str, Any]) -> list[str]:
    raw = card.get("text_lines")
    if isinstance(raw, list):
        return [_extract.clean(value) for value in raw if _extract.clean(value)]
    return _extract.lines(card.get("text") or "")


def explicit_venue(card: dict[str, Any]) -> str:
    """Recognise an unlabelled venue line in an official detail document.

    NHB detail pages often render date, venue, and admission as three adjacent lines
    without ``Location`` labels. The old parser recognised the date fragment but did
    not count ``Asian Civilisations Museum`` as an explicit venue, leaving a correctly
    loaded detail page marked incomplete.
    """

    venue = _BASE_EXPLICIT_VENUE(card)
    if venue:
        return venue

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(_card_lines(card)):
        if not line or len(line) > 180 or len(line.split()) > 24:
            continue
        if _NON_VENUE_RE.search(line):
            continue
        if _extract.DATE_LINE_RE.search(line) or _extract.TIME_RE.fullmatch(line):
            continue
        if not _VENUE_HINT_RE.search(line):
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


def apply() -> None:
    """Install shared open-date lifecycle and unlabelled-venue repair."""

    global _APPLIED, _BASE_CANDIDATE_EXPIRED, _BASE_EXPLICIT_VENUE
    if _APPLIED:
        return

    _BASE_CANDIDATE_EXPIRED = _detail_dates._candidate_expired
    _BASE_EXPLICIT_VENUE = _membership._explicit_venue
    _detail_dates._candidate_expired = candidate_expired
    _membership._explicit_venue = explicit_venue
    _APPLIED = True


__all__ = ["apply", "candidate_expired", "explicit_venue"]
