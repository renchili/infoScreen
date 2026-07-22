from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from . import event_review as _review
from . import extract as _extract

_APPLIED = False
_BASE_SET_EVENT_DECISION = None
_REVIEW_PUBLISH_ORIGIN = "review_state"


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": True, "results": []}
    return payload if isinstance(payload, dict) else {"ok": True, "results": []}


def _canonical_url(value: object) -> str:
    try:
        return _review.canonical_url(value)
    except (TypeError, ValueError):
        return ""


def _published_title(candidate: _review.EventCandidate) -> str:
    title = _extract.clean(candidate.title)
    if title:
        return title
    for line in _extract.lines(candidate.evidence.text):
        if line:
            return line
    source = _extract.clean(candidate.source_name or candidate.source_id)
    return f"{source or 'Local'} activity"


def _confirmed_event(candidate: _review.EventCandidate) -> dict[str, Any]:
    """Convert one operator-confirmed candidate without crawler re-admission.

    The operator has already decided that the listing card is a related activity.
    Missing detail-page fields remain visible as missing data and must not cause a
    second rejection during publication.
    """

    listing_url = _canonical_url(candidate.listing_url)
    detail_url = _canonical_url(candidate.detail_url) or listing_url
    when = _extract.clean(candidate.when)
    dates = _extract.label_dates(when)
    source_name = _extract.clean(candidate.source_name or candidate.source_id)
    listing_only = not detail_url or detail_url == listing_url

    return {
        "title": _published_title(candidate),
        "when": when,
        "where": _extract.clean(candidate.where) or source_name,
        "host": source_name,
        "source_name": source_name,
        "url": detail_url or listing_url,
        "summary": _extract.clean(candidate.summary),
        "start_date": _extract.best_start_date(when) if dates else "",
        "end_date": max(dates).isoformat() if len(dates) >= 2 else "",
        "kind": "event",
        "source_type": (
            "operator_confirmed_official_listing_card_without_detail"
            if listing_only
            else "operator_confirmed_official_listing_card"
        ),
        "candidate_policy": "official-listing-authority-v1",
        "listing_url": listing_url,
        "listing_card_id": candidate.candidate_id,
        "listing_only": listing_only,
        "detail_available": not listing_only,
        "detail_status": candidate.detail_status,
        "detail_error": _extract.clean(candidate.detail_error),
        "operator_review_decision": "confirmed",
        "review_publish_origin": _REVIEW_PUBLISH_ORIGIN,
        "review_candidate_id": candidate.candidate_id,
        "reviewed_at": candidate.reviewed_at or "",
        "collected_at": candidate.collected_at,
    }


def _semantic_identity(event: dict[str, Any]) -> str:
    return _extract.semantic_key(event)


def _confirmed_candidates(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
) -> list[_review.EventCandidate]:
    source_order = {
        str(source.get("id") or ""): index
        for index, source in enumerate(store.inventory())
    }
    rows = [
        (index, candidate)
        for index, candidate in enumerate(state.events)
        if candidate.decision == "confirmed"
    ]
    rows.sort(
        key=lambda item: (
            source_order.get(item[1].source_id, 10_000),
            item[0],
        )
    )
    return [candidate for _, candidate in rows]


def merge_review_state(
    payload: dict[str, Any],
    store: _review.EventReviewStore,
    state: _review.ReviewState | None = None,
) -> dict[str, Any]:
    """Overlay current confirmed review rows without mutating collector rows.

    Every previous row created by this publisher is rebuilt from current review
    state. System-collected rows are copied exactly as supplied. A confirmed
    detail-page Event is considered already present when its canonical URL exists;
    a listing-only Event is matched semantically so multiple distinct cards may
    share the same official list URL.
    """

    current = state or store.load()
    system_results = [
        dict(item)
        for item in payload.get("results") or []
        if isinstance(item, dict)
        and item.get("review_publish_origin") != _REVIEW_PUBLISH_ORIGIN
    ]

    urls = {
        _canonical_url(item.get("url"))
        for item in system_results
        if _canonical_url(item.get("url"))
    }
    semantic_keys = {
        _semantic_identity(item)
        for item in system_results
        if _semantic_identity(item)
    }

    added = 0
    already_present = 0
    review_results: list[dict[str, Any]] = []
    for candidate in _confirmed_candidates(store, current):
        event = _confirmed_event(candidate)
        event_url = _canonical_url(event.get("url"))
        semantic_key = _semantic_identity(event)
        duplicate = (
            semantic_key in semantic_keys
            if event.get("listing_only") is True
            else bool(event_url and event_url in urls) or semantic_key in semantic_keys
        )
        if duplicate:
            already_present += 1
            continue

        if event_url:
            urls.add(event_url)
        if semantic_key:
            semantic_keys.add(semantic_key)
        review_results.append(event)
        added += 1

    results = [*system_results, *review_results]
    merged = dict(payload)
    merged["ok"] = bool(payload.get("ok", True))
    merged["results"] = results
    merged["count"] = len(results)
    merged["updated_at"] = _review.utc_now()
    merged["review_publish"] = {
        "published_at": merged["updated_at"],
        "confirmed_count": len(_confirmed_candidates(store, current)),
        "added": added,
        "already_present": already_present,
        "mode": "overlay_on_collector_results",
        "state_path": str(store.state_path),
    }
    return merged


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
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
    """Immediately apply current Event decisions to the existing display runtime."""

    runtime_path = store.root.parent / "local_event_search_results.json"
    payload = merge_review_state(_read_payload(runtime_path), store, state)
    atomic_write(runtime_path, payload)
    return payload


def set_event_decision(
    store: _review.EventReviewStore,
    candidate_id: str,
    decision: _review.Decision,
) -> _review.ReviewState:
    """Persist one decision and immediately overlay the current confirmed set."""

    state = _BASE_SET_EVENT_DECISION(store, candidate_id, decision)
    publish_review_state(store, state)
    return state


def _publish_existing_state() -> None:
    surface_dir = Path(__file__).resolve().parents[1]
    env_dir = Path(
        os.environ.get("INFOSCREEN_ENV_DIR", str(surface_dir / ".env"))
    ).expanduser().resolve()
    review_root = env_dir / "local_event_review"
    state_path = review_root / "state.json"
    if not state_path.is_file():
        return

    try:
        publish_review_state(
            _review.EventReviewStore(
                root=review_root,
                config_path=surface_dir / "conf" / "event_sources.json",
            )
        )
    except Exception as exc:
        print(
            f"Local Event review state was not published at startup: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def apply() -> None:
    """Install immediate, non-destructive publication of Event review decisions."""

    global _APPLIED, _BASE_SET_EVENT_DECISION
    if _APPLIED:
        return
    _BASE_SET_EVENT_DECISION = _review.EventReviewStore.set_event_decision
    _review.EventReviewStore.set_event_decision = set_event_decision
    _APPLIED = True
    _publish_existing_state()


__all__ = [
    "apply",
    "atomic_write",
    "merge_review_state",
    "publish_review_state",
    "set_event_decision",
]
