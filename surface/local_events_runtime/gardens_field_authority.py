from __future__ import annotations

import re
import sys
from typing import Any

from . import _apply_gardens_card_fields as _base_apply_gardens_card_fields
from . import extract as _extract

_GARDENS_SOURCE_ID = "gardensbythebay"
_GARDENS_TIME_NOTE_RE = re.compile(
    r"^(?:(?:various|multiple|selected|different)\s+"
    r"(?:timings?|times?|sessions?)|"
    r"(?:timings?|times?|sessions?)\s+(?:vary|varies))$",
    re.I,
)
_APPLIED = False


def _without_time_notes(card: dict[str, Any]) -> dict[str, Any]:
    """Remove standalone schedule notes before the existing venue scan.

    Gardens listing cards place entries such as ``Various timings`` between the
    date range and the actual venue. Those entries describe the schedule and must
    not become the Event location. All other card lines retain their original
    order and continue through the existing Gardens field parser.
    """

    lines = _extract.lines(card.get("text") or "")
    filtered = [
        line
        for line in lines
        if not _GARDENS_TIME_NOTE_RE.fullmatch(_extract.clean(line))
    ]
    if filtered == lines:
        return card

    repaired = dict(card)
    repaired["text"] = "\n".join(filtered)
    repaired["text_lines"] = filtered
    return repaired


def apply_gardens_card_fields(
    source: dict[str, Any],
    card: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    """Apply the existing Gardens field repair after removing timing notes."""

    if _extract.clean(source.get("id") or "").lower() != _GARDENS_SOURCE_ID:
        return _base_apply_gardens_card_fields(source, card, event)
    return _base_apply_gardens_card_fields(source, _without_time_notes(card), event)


def apply() -> None:
    """Install the Gardens field repair for production and review collectors."""

    global _APPLIED
    if _APPLIED:
        return

    package = sys.modules.get(__package__)
    if package is None:
        raise RuntimeError("local_events_runtime_package_not_loaded")
    package._apply_gardens_card_fields = apply_gardens_card_fields
    _APPLIED = True


__all__ = ["apply", "apply_gardens_card_fields"]
