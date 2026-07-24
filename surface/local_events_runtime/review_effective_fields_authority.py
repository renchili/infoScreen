from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import detail_date_authority as _detail_dates
from . import event_review as _review
from . import extract as _extract
from .detail_summary_authority import useful_event_summary

_APPLIED = False
_BASE_DETAIL_CANDIDATE = None
_BASE_LOAD = None
_BASE_STATE_PAYLOAD = None
_BASE_REPLACE_EVENTS = None

COLLECTOR_RUNTIME_FILENAME = "local_event_collector_results.json"
DISPLAY_RUNTIME_FILENAME = "local_event_search_results.json"

_TIME_RANGE_RE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*[\-–—]\s*"
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.I,
)


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
    """Return effective runtime rows indexed by canonical detail URL."""

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


def _detail_text(raw: dict[str, Any]) -> str:
    values: list[str] = []
    for value in (raw.get("summary"), raw.get("detail_page_title")):
        text = _extract.clean(value)
        if text and text not in values:
            values.append(text)

    evidence = raw.get("evidence")
    if isinstance(evidence, dict):
        text = _extract.clean(evidence.get("text"))
        if text and text not in values:
            values.append(text)
    return "\n".join(values)


def _recover_when(raw: dict[str, Any]) -> tuple[str, str]:
    current = _extract.clean(raw.get("when"))
    if current:
        return current, current

    text = _detail_text(raw)
    if not text:
        return "", ""
    pseudo_card = {
        "text": text,
        "text_lines": [
            _extract.clean(line)
            for line in text.splitlines()
            if _extract.clean(line)
        ],
    }
    when, source_line = _extract.pick_when(pseudo_card)
    when = _extract.clean(when)
    if not when:
        return "", ""

    time_match = _TIME_RANGE_RE.search(source_line or text)
    if time_match and time_match.group(0).casefold() not in when.casefold():
        when = f"{when} · {_extract.clean(time_match.group(0))}"
    return when, _extract.clean(source_line)


def _repair_fields(
    raw: dict[str, Any],
    runtime_row: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recover fields before lifecycle filtering or Review publication."""

    result = dict(raw)
    runtime = runtime_row or {}

    if not _extract.clean(result.get("title")):
        result["title"] = _extract.clean(runtime.get("title"))

    if not _extract.clean(result.get("when")):
        result["when"] = _extract.clean(runtime.get("when"))
    recovered_when, when_line = _recover_when(result)
    if recovered_when:
        result["when"] = recovered_when

    if not _extract.clean(result.get("where")):
        result["where"] = _extract.clean(runtime.get("where"))
    if not _extract.clean(result.get("where")):
        source_name = _extract.clean(
            (source or {}).get("name")
            or (source or {}).get("default_venue")
            or result.get("source_name")
        )
        pseudo_source = {
            "name": source_name,
            "default_venue": _extract.clean(
                (source or {}).get("default_venue") or source_name
            ),
        }
        result["where"] = _extract.clean(
            _extract.pick_venue(
                pseudo_source,
                {
                    "text": _detail_text(result),
                    "text_lines": [
                        _extract.clean(line)
                        for line in _detail_text(result).splitlines()
                        if _extract.clean(line)
                    ],
                },
                _extract.clean(result.get("when")),
                when_line,
            )
        )

    summary = _effective_summary(result.get("summary"), runtime_row)
    if summary:
        result["summary"] = summary
    elif not useful_event_summary(result.get("summary")):
        result["summary"] = ""
    return result


def _effective_candidate_dict(
    raw: dict[str, Any],
    runtime_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    url = _canonical(raw.get("detail_url"))
    return _repair_fields(raw, runtime_index.get(url))


def _effective_candidate_model(
    candidate: _review.EventCandidate,
    runtime_index: dict[str, dict[str, Any]],
) -> _review.EventCandidate:
    repaired = _repair_fields(
        candidate.model_dump(mode="json"),
        runtime_index.get(_canonical(candidate.detail_url)),
    )
    updates = {
        key: repaired.get(key, getattr(candidate, key))
        for key in ("title", "when", "where", "summary")
        if repaired.get(key, getattr(candidate, key)) != getattr(candidate, key)
    }
    return candidate.model_copy(update=updates) if updates else candidate


def _expired(candidate: _review.EventCandidate) -> bool:
    """Apply the final open-ended-aware lifecycle rule after field recovery."""

    return bool(_detail_dates._candidate_expired(candidate))


def _active_candidates(
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> tuple[list[_review.EventCandidate], dict[str, Any]]:
    active = [candidate for candidate in candidates if not _expired(candidate)]
    removed = len(candidates) - len(active)
    metadata = dict(collection)
    metadata["candidate_count"] = len(active)
    metadata["expired_candidate_count"] = int(
        metadata.get("expired_candidate_count") or 0
    ) + removed
    return active, metadata


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    """Recover detail fields so the lifecycle decision sees the real date."""

    result = dict(
        _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )
    )
    return {
        key: str(value or "") if key != "status" else value
        for key, value in _repair_fields(result, source=source).items()
    }


def load(store: _review.EventReviewStore) -> _review.ReviewState:
    """Repair legacy blank fields, then remove past Review candidates."""

    state = _BASE_LOAD(store)
    runtime_index = _runtime_by_url(store)
    effective = [
        _effective_candidate_model(candidate, runtime_index)
        for candidate in state.events
    ]
    state.events, state.event_collection = _active_candidates(
        effective,
        state.event_collection,
    )
    return state


def state_payload(store: _review.EventReviewStore) -> dict[str, Any]:
    """Expose only current Review evidence with effective fields."""

    payload = dict(_BASE_STATE_PAYLOAD(store))
    runtime_index = _runtime_by_url(store)
    effective = [
        _effective_candidate_dict(dict(row), runtime_index)
        for row in payload.get("events") or []
        if isinstance(row, dict)
    ]
    payload["events"] = [
        row
        for row in effective
        if not _detail_dates._candidate_expired(
            _review.EventCandidate.model_validate(row)
        )
    ]
    collection = dict(payload.get("event_collection") or {})
    removed = len(effective) - len(payload["events"])
    collection["candidate_count"] = len(payload["events"])
    collection["expired_candidate_count"] = int(
        collection.get("expired_candidate_count") or 0
    ) + removed
    payload["event_collection"] = collection
    return payload


def replace_events(
    store: _review.EventReviewStore,
    candidates: list[_review.EventCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    """Persist recovered fields but never persist already-ended candidates."""

    runtime_index = _runtime_by_url(store)
    effective = [
        _effective_candidate_model(candidate, runtime_index)
        for candidate in candidates
    ]
    active, metadata = _active_candidates(effective, collection)
    return _BASE_REPLACE_EVENTS(store, active, metadata)


def apply() -> None:
    """Install one effective field and lifecycle contract for Review and kiosk."""

    global _APPLIED, _BASE_DETAIL_CANDIDATE, _BASE_LOAD
    global _BASE_STATE_PAYLOAD, _BASE_REPLACE_EVENTS
    if _APPLIED:
        return

    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _BASE_LOAD = _review.EventReviewStore.load
    _BASE_STATE_PAYLOAD = _review.EventReviewStore.state_payload
    _BASE_REPLACE_EVENTS = _review.EventReviewStore.replace_events

    _review.event_from_card = _extract.event_from_card
    _review._detail_candidate = _detail_candidate
    _review.EventReviewStore.load = load
    _review.EventReviewStore.state_payload = state_payload
    _review.EventReviewStore.replace_events = replace_events
    _APPLIED = True


__all__ = [
    "COLLECTOR_RUNTIME_FILENAME",
    "DISPLAY_RUNTIME_FILENAME",
    "apply",
    "load",
    "replace_events",
    "state_payload",
    "_detail_candidate",
    "_repair_fields",
]
