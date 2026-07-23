from __future__ import annotations

from typing import Any

from . import review_publish_authority as _publisher

_APPLIED = False
_BASE_REVIEW_EVENT = None


def _review_event(candidate: Any) -> dict[str, Any]:
    """Remove CTA, terms, contact, registration, and safety text before publish."""

    from .detail_summary_authority import useful_event_summary

    event = dict(_BASE_REVIEW_EVENT(candidate))
    event["summary"] = useful_event_summary(event.get("summary"))
    return event


def apply() -> None:
    """Make narrative detail text the only Review-authoritative summary."""

    global _APPLIED, _BASE_REVIEW_EVENT
    if _APPLIED:
        return

    # The canonical job calls this authority directly. Apply the detail authority
    # here as well so scheduled, HTTP, Studio, and direct job paths use one rule.
    from .detail_summary_authority import apply as apply_detail_summary_authority

    apply_detail_summary_authority()
    _BASE_REVIEW_EVENT = _publisher._review_event
    _publisher._review_event = _review_event
    _APPLIED = True


__all__ = ["apply"]
