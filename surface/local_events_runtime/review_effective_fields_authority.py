from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import event_review as _review
from .detail_summary_authority import useful_event_summary

_APPLIED = False
_BASE_STATE_PAYLOAD = None
_BASE_REPLACE_EVENTS = None

COLLECTOR_RUNTIME_FILENAME = "local_event_collector_results.json"
DISPLAY_RUNTIME_FILENAME = "local_event_search_results.json"


def _read_results(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("results") if isinstance(payload, dict) else []
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _canonical(value: object) -> str:
    try:
        return _review.canonical_url(value)
    except (TypeError, ValueError):
        return ""


def _runtime_by_url(store: _review.EventReviewStore) -> dict[str, dict[str, Any]]:
    """Return effective runtime rows indexed by canonical detail URL.

    The collector snapshot is loaded first and the public kiosk projection second,
    so the map reflects exactly what the homepage currently renders when both files
    contain the same activity.
    """

    index: dict[str, dict[str, Any]] = {}
    runtime_root = store.root.parent
    for filename in (COLLECTOR_RUNTIME_FILENAME, DISPLAY_RUNTIME_FILENAME):
        for row in _read_results(runtime_root / filename):
            url = _canonical(row.get("url") or row.get("detail_url"))
            if url:
                index[url] = row
    return index


def _effective_summary(current: object, runtime_row: dict[str, Any] | None) -> str:
    existing = useful_event_summary(current)
    if existing:
        return existing
    if not runtime_row:
        return ""
    return useful_event_summary(runtime_row.get("summary"))


def _effective_candidate_dict(
    raw: dict[str, Any],
    runtime_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result = dict(raw)
    url = _canonical(result.get("detail_url"))
    runtime_row = runtime_index.get(url)
    summary = _effective_summary(result.get("summary"), runtime_row)
    if summary:
        result["summary"] = summary
    elif not useful_event_summary(result.get("summary")):
        result["summary"] = ""
    return result


def _effective_candidate_model(
    candidate: _review.EventCandidate,
    runtime_index: dict[str, dict[str, Any]],
) -> _review.EventCandidate:
    summary = _effective_summary(
        candidate.summary,
        runtime_index.get(_canonical(candidate.detail_url)),
    )
    if summary == candidate.summary:
        return candidate
    return candidate.model_copy(update={"summary": summary})


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Expose Review evidence with the same effective narrative as the kiosk."""

    payload = dict(_BASE_STATE_PAYLOAD(store))
    runtime_index = _runtime_by_url(store)
    payload["events"] = [
        _effective_candidate_dict(dict(row), runtime_index)
        for row in payload.get("events") or []
        if isinstance(row, dict)
    ]
    return payload


def replace_events(
    store: _review.EventReviewStore,
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    """Persist real runtime narrative when a fresh Preview returned only a fallback."""

    runtime_index = _runtime_by_url(store)
    effective = [
        _effective_candidate_model(candidate, runtime_index)
        for candidate in candidates
    ]
    return _BASE_REPLACE_EVENTS(store, effective, collection)


def apply() -> None:
    """Install one effective summary contract for Review state and kiosk output."""

    global _APPLIED, _BASE_STATE_PAYLOAD, _BASE_REPLACE_EVENTS
    if _APPLIED:
        return

    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events
    _review.EventReviewStore.state_payload = state_payload
    _review.EventReviewStore.replace_events = replace_events
    _APPLIED = True


__all__ = [
    "COLLECTOR_RUNTIME_FILENAME",
    "DISPLAY_RUNTIME_FILENAME",
    "apply",
    "replace_events",
    "state_payload",
]
