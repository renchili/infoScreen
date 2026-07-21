from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from . import event_review as _review
from . import extract as _extract
from . import listing_only_output_authority as _listing_output
from . import listing_only_runtime_authority as _listing_runtime
from . import output as _output
from . import review_runtime_authority as _runtime

_APPLIED = False
_BASE_SET_EVENT_DECISION = None


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": True, "results": []}
    return payload if isinstance(payload, dict) else {"ok": True, "results": []}


def _event_identity(event: dict[str, Any]) -> str:
    url = _runtime._canonical_url(event.get("url"))
    if event.get("listing_only") is True:
        return "listing:" + _extract.semantic_key(event)
    return "url:" + url


def _confirmed_events(state: _review.ReviewState) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for candidate in state.events:
        if candidate.decision != "confirmed":
            continue
        event = _runtime._confirmed_event(candidate.model_dump(mode="json"))
        if event is not None:
            events.append(event)
    return events


def _merge_runtime(
    payload: dict[str, Any],
    confirmed: list[dict[str, Any]],
) -> dict[str, Any]:
    # Rebuild the operator-confirmed portion from current review state so REJECT
    # and RESET remove rows that were previously published.
    results = [
        dict(item)
        for item in payload.get("results") or []
        if isinstance(item, dict)
        and item.get("operator_review_decision") != "confirmed"
    ]
    by_identity = {
        _event_identity(item): index
        for index, item in enumerate(results)
        if _runtime._canonical_url(item.get("url"))
    }

    for event in confirmed:
        identity = _event_identity(event)
        existing_index = by_identity.get(identity)
        if existing_index is None:
            by_identity[identity] = len(results)
            results.append(event)
            continue

        current = dict(results[existing_index])
        for field, value in event.items():
            if value not in {"", None}:
                current[field] = value
        results[existing_index] = current

    published = dict(payload)
    published["ok"] = True
    published["results"] = results
    published["count"] = len(results)
    published["updated_at"] = _review.utc_now()
    published["review_publish"] = {
        "published_at": published["updated_at"],
        "confirmed_count": len(confirmed),
        "mode": "event_decision",
    }
    return _output.normalize_payload(published)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def publish_review_state(
    store: _review.EventReviewStore,
    state: _review.ReviewState | None = None,
) -> dict[str, Any]:
    """Publish current Event decisions without running any website collector."""

    _listing_runtime.apply()
    _listing_output.apply()
    current = state or store.load()
    runtime_path = store.root.parent / "local_event_search_results.json"
    payload = _merge_runtime(_read_payload(runtime_path), _confirmed_events(current))
    _atomic_write(runtime_path, payload)
    return payload


def set_event_decision(
    store: _review.EventReviewStore,
    candidate_id: str,
    decision: _review.Decision,
) -> _review.ReviewState:
    """Persist one decision and immediately publish the resulting Event set."""

    state = _BASE_SET_EVENT_DECISION(store, candidate_id, decision)
    publish_review_state(store, state)
    return state


def apply() -> None:
    """Install immediate runtime publication for every Event review decision."""

    global _APPLIED, _BASE_SET_EVENT_DECISION
    if _APPLIED:
        return
    _listing_runtime.apply()
    _listing_output.apply()
    _BASE_SET_EVENT_DECISION = _review.EventReviewStore.set_event_decision
    _review.EventReviewStore.set_event_decision = set_event_decision
    _APPLIED = True


__all__ = ["apply", "publish_review_state", "set_event_decision"]
