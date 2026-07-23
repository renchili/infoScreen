from __future__ import annotations

import re
import sys
from typing import Any

from . import extract as _extract

_OPEN_VALUE_RE = re.compile(
    r"^(?:ongoing|permanent|daily|selected dates?|weekends?|public holidays?)"
    r"(?:\s*[·|,\-–—]\s*.+)?$",
    re.I,
)
_WHEN_INLINE_RE = re.compile(r"^(?:when|date)\s*:?\s*(.+)$", re.I)
_WHEN_LABEL_RE = re.compile(r"^(?:when|date)\s*:?\s*$", re.I)

_APPLIED = False
_BASE_PICK_WHEN = None
_BASE_CURRENT_DATE_LABEL = None


def open_ended_value(value: object) -> str:
    """Return an explicit non-expiring schedule label, otherwise an empty string."""

    text = _extract.clean(value)
    return text if _OPEN_VALUE_RE.fullmatch(text) else ""


def pick_when(card: dict[str, Any]) -> tuple[str, str]:
    """Fall back to explicit open-ended labels when no calendar date is present."""

    when, source_line = _BASE_PICK_WHEN(card)
    if when:
        return when, source_line

    raw_lines = card.get("text_lines")
    lines = (
        [_extract.clean(item) for item in raw_lines if _extract.clean(item)]
        if isinstance(raw_lines, list)
        else _extract.lines(card.get("text") or "")
    )
    for index, line in enumerate(lines):
        inline = _WHEN_INLINE_RE.fullmatch(line)
        if inline:
            value = open_ended_value(inline.group(1))
            if value:
                return value, line
        if _WHEN_LABEL_RE.fullmatch(line):
            for candidate in lines[index + 1:index + 4]:
                if _WHEN_LABEL_RE.fullmatch(candidate):
                    break
                value = open_ended_value(candidate)
                if value:
                    return value, line
                if _extract.DATE_LINE_RE.search(candidate):
                    break
        value = open_ended_value(line)
        if value:
            return value, line
    return "", ""


def current_date_label(label: str) -> bool:
    """Treat explicit ongoing/recurring labels as current without inventing a date."""

    return bool(_BASE_CURRENT_DATE_LABEL(label) or open_ended_value(label))


def apply() -> None:
    """Install explicit open-ended date support before collectors bind functions."""

    global _APPLIED, _BASE_PICK_WHEN, _BASE_CURRENT_DATE_LABEL
    if _APPLIED:
        return

    _BASE_PICK_WHEN = _extract.pick_when
    _BASE_CURRENT_DATE_LABEL = _extract.current_date_label
    _extract.pick_when = pick_when
    _extract.current_date_label = current_date_label

    package = sys.modules.get(__package__)
    if package is not None:
        # The active package-level event parser resolves this private global at
        # call time, so patch both public and private names.
        package._current_date_label = current_date_label
        package.current_date_label = current_date_label
    _APPLIED = True


__all__ = ["apply", "current_date_label", "open_ended_value", "pick_when"]
