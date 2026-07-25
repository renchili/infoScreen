from __future__ import annotations

import re
from typing import Any

from . import review_publish_authority as _publisher

_APPLIED = False
_BASE_REVIEW_EVENT = None
_OPERATIONAL_RE = re.compile(
    r"\b(?:terms?|conditions?|registration|ticketing|admission|refund|"
    r"cancellation|safety|enquir(?:y|ies)|contact|privacy|cookie)\b|@",
    re.I,
)
_CTA_RE = re.compile(
    r"\b(?:book now|buy tickets?|register now|sign up|learn more|read more|"
    r"find out more|plan your visit)\b",
    re.I,
)


def _review_event(candidate: Any) -> dict[str, Any]:
    """Remove operational copy while preserving concise real activity summaries."""

    from .detail_summary_authority import useful_event_summary

    event = dict(_BASE_REVIEW_EVENT(candidate))
    raw = " ".join(str(event.get("summary") or "").split())
    summary = useful_event_summary(raw)
    if (
        not summary
        and len(raw) >= 20
        and not _OPERATIONAL_RE.search(raw)
        and not _CTA_RE.search(raw)
    ):
        summary = raw
    event["summary"] = summary
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
