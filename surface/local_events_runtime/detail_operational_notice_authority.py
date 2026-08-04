from __future__ import annotations

import re
from typing import Any

from . import extract as _extract
from . import review_detail_navigation_authority as _navigation
from . import review_effective_fields_authority as _effective

_APPLIED = False

_OPERATIONAL_DATE_NOTICE_RE = re.compile(
    r"\b(?:notice|closure|temporarily\s+closed|will\s+be\s+closed|closed\s+on|"
    r"private\s+programme|private\s+program|private\s+event|maintenance|"
    r"unavailable|not\s+available|last\s+admission|kind\s+understanding)\b",
    re.I,
)


def _operational_notice(value: object) -> bool:
    text = _extract.clean(value)
    return bool(text and _OPERATIONAL_DATE_NOTICE_RE.search(text))


def _candidate_rows(payload: dict[str, Any]) -> list[str]:
    rows: list[object] = []
    raw_dates = payload.get("dates")
    if isinstance(raw_dates, list):
        rows.extend(raw_dates)
    rows.extend(_navigation._payload_lines(payload))

    output: list[str] = []
    for raw in rows:
        text = _extract.clean(raw)
        if text and text not in output:
            output.append(text)
    return output


def _event_date_line(value: object) -> bool:
    text = _extract.clean(value)
    if not text or len(text) > 240:
        return False
    if _operational_notice(text) or _effective._DATE_NOISE_RE.search(text):
        return False
    if _navigation._label_key(text) in _navigation._ALL_FIELD_LABELS:
        return False
    return bool(_effective._line_dates(text))


def _detail_date_line(payload: dict[str, Any]) -> str:
    """Select a real activity date, never an operational closure notice."""

    for text in _candidate_rows(payload):
        if _event_date_line(text):
            return text
    return ""


def _facts_have_date(facts: dict[str, Any]) -> bool:
    """Do not settle detail collection while only notice dates are available."""

    return any(_event_date_line(text) for text in _candidate_rows(facts))


def _raw_when(payload: dict[str, Any]) -> str:
    """Keep the activity date and its hours while excluding closure-notice text."""

    base_picker = _effective._BASE_RAW_WHEN
    base = _extract.clean(base_picker(payload)) if callable(base_picker) else ""
    date_line = _detail_date_line(payload)
    if not date_line:
        return ""

    values = [date_line]
    if (
        base
        and base != date_line
        and not _operational_notice(base)
        and not _effective._line_dates(base)
    ):
        values.append(base)

    already_has_time = any(
        _navigation._UNLABELLED_TIME_RE.search(value)
        for value in values
    )
    if not already_has_time:
        for line in _navigation._payload_lines(payload):
            text = _extract.clean(line)
            if (
                text
                and text not in values
                and not _operational_notice(text)
                and not _effective._line_dates(text)
                and _navigation._UNLABELLED_TIME_RE.search(text)
            ):
                values.append(text)
                break

    return " · ".join(values)


def apply() -> None:
    """Install the final operational-notice exclusion for Review detail dates."""

    global _APPLIED
    _effective._detail_date_line = _detail_date_line
    _effective._facts_have_date = _facts_have_date
    _effective._raw_when = _raw_when
    _navigation._raw_when = _raw_when
    _APPLIED = True


__all__ = [
    "apply",
    "_detail_date_line",
    "_facts_have_date",
    "_operational_notice",
    "_raw_when",
]
