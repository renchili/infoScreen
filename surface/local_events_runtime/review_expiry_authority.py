from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

from . import event_review as _review
from . import extract as _extract
from . import review_publish_authority as _publisher

_APPLIED = False
_BASE_STATE_PAYLOAD = None
_BASE_CLEAN_COLLECTOR_PAYLOAD = None
_BASE_ORDERED_CANDIDATES = None
_OPEN_ENDED_RE = re.compile(r"\b(?:from|since|ongoing|permanent)\b", re.I)


def _iso_date(value: object) -> date | None:
    text = _extract.clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def event_is_expired(value: object) -> bool:
    """Return whether one Event row or Review candidate has definitely ended."""

    if isinstance(value, dict):
        when = _extract.clean(value.get("when"))
        start = _iso_date(value.get("start_date"))
        end = _iso_date(value.get("end_date"))
    else:
        when = _extract.clean(getattr(value, "when", ""))
        start = _iso_date(getattr(value, "start_date", ""))
        end = _iso_date(getattr(value, "end_date", ""))

    if _OPEN_ENDED_RE.search(when):
        return False

    dates = _extract.label_dates(when)
    effective_end = end or (max(dates) if dates else start)
    return bool(effective_end and effective_end < date.today())


def _active_rows(rows: Iterable[Any]) -> tuple[list[Any], int]:
    active: list[Any] = []
    removed = 0
    for row in rows:
        if event_is_expired(row):
            removed += 1
            continue
        active.append(row)
    return active, removed


def _state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Expose only current Event candidates while retaining historical state on disk."""

    payload = dict(_BASE_STATE_PAYLOAD(store))
    rows = payload.get("events")
    active, removed = _active_rows(rows if isinstance(rows, list) else [])
    payload["events"] = active
    payload["expired_event_count"] = removed
    return payload


def _clean_collector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Prevent stale collector snapshots from restoring ended activities."""

    cleaned = dict(_BASE_CLEAN_COLLECTOR_PAYLOAD(payload))
    rows = cleaned.get("results")
    active, removed = _active_rows(rows if isinstance(rows, list) else [])
    cleaned["results"] = active
    cleaned["count"] = len(active)
    cleaned["expired_events_removed"] = int(
        cleaned.get("expired_events_removed") or 0
    ) + removed
    return cleaned


def _ordered_candidates(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
    decisions: Iterable[str],
) -> list[_review.EventCandidate]:
    """Exclude ended Review candidates from confirmed or rejected projection work."""

    rows = _BASE_ORDERED_CANDIDATES(store, state, decisions)
    active, _ = _active_rows(rows)
    return active


def apply() -> None:
    """Install one expiry rule across Studio state and kiosk publication."""

    global _APPLIED
    global _BASE_STATE_PAYLOAD
    global _BASE_CLEAN_COLLECTOR_PAYLOAD
    global _BASE_ORDERED_CANDIDATES

    if _APPLIED:
        _review.EventReviewStore.state_payload = _state_payload
        _publisher.clean_collector_payload = _clean_collector_payload
        _publisher._ordered_candidates = _ordered_candidates
        return

    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_CLEAN_COLLECTOR_PAYLOAD = _publisher.clean_collector_payload
    _BASE_ORDERED_CANDIDATES = _publisher._ordered_candidates

    _review.EventReviewStore.state_payload = _state_payload
    _publisher.clean_collector_payload = _clean_collector_payload
    _publisher._ordered_candidates = _ordered_candidates
    _APPLIED = True


__all__ = ["apply", "event_is_expired"]
