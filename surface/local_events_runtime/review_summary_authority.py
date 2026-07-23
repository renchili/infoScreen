from __future__ import annotations

from typing import Any

from . import review_publish_authority as _publisher
from .detail_payload_authority import useful_event_summary

_APPLIED = False
_BASE_REVIEW_EVENT = None


def _review_event(candidate: Any) -> dict[str, Any]:
    """Remove site CTA text before a reviewed row can override kiosk content."""

    event = dict(_BASE_REVIEW_EVENT(candidate))
    event["summary"] = useful_event_summary(event.get("summary"))
    return event


def apply() -> None:
    """Make narrative detail text the only Review-authoritative summary."""

    global _APPLIED, _BASE_REVIEW_EVENT
    if _APPLIED:
        return
    _BASE_REVIEW_EVENT = _publisher._review_event
    _publisher._review_event = _review_event
    _APPLIED = True


__all__ = ["apply"]
