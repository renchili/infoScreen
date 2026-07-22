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
        return {}
    return payload if isinstance(payload, dict) else {}


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
    """Convert one operator-confirmed candidate without applying crawler gates.

    Membership was already decided by the operator. Missing detail fields remain
    visible as missing fields; they must not cause a second rejection here.
    """

    listing_url = _review.canonical_url(candidate.listing_url)
    detail_url = _review.canonical_url(candidate.detail_url or listing_url)
    when = _extract.clean(candidate.when)
    dates = _extract.label_dates(when)
    source_name = _extract.clean(candidate.source_name or candidate.source_id)
    listing_only = detail_url == listing_url

    return {
        "title": _published_title(candidate),
        "when": when,
        "where": _extract.clean(candidate.where) or source_name,
        "host": source_name,
        "source_name": source_name,
        "url": detail_url,
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


def _published_payload(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
    previous: dict[str, Any],
) -> dict[str, Any]:
    inventory = store.inventory()
    source_order = {
        str(source.get("id") or ""): index
        for index, source in enumerate(inventory)
    }
    confirmed = [
        (index, candidate)
        for index, candidate in enumerate(state.events)
        if candidate.decision == "confirmed"
    ]
    confirmed.sort(
        key=lambda item: (
            source_order.get(item[1].source_id, 10_000),
            item[0],
        )
    )

    results: list[dict[str, Any]] = []
    for result_order, (_, candidate) in enumerate(confirmed):
        event = _confirmed_event(candidate)
        event["source_order"] = source_order.get(candidate.source_id, 10_000)
        event["result_order"] = result_order
        results.append(event)

    updated_at = _review.utc_now()
    return {
        "ok": True,
        "version": 53,
        "extractor": "operator-confirmed-review-state-v1",
        "text_normalizer": "plain-text-v1",
        "updated_at": updated_at,
        "location": str(previous.get("location") or "Punggol Singapore"),
        "event_source_config": store.config_path.name,
        "source_count": len(inventory),
        "sources": [
            {
                "title": str(source.get("name") or source.get("id") or ""),
                "url": str(source.get("official_home") or ""),
            }
            for source in inventory
        ],
        "count": len(results),
        "results": results,
        "partial": False,
        "write_policy": "review_state_authoritative",
        "review_authority": {
            "confirmed_in_state": len(results),
            "state_path": str(store.state_path),
            "published_at": updated_at,
        },
        "runtime": {
            "writer": "surface.local_events_runtime.review_publish_authority",
            "state_path": str(store.state_path),
        },
    }


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
    """Replace the display runtime with the current confirmed review state."""

    current = state or store.load()
    runtime_path = store.root.parent / "local_event_search_results.json"
    payload = _published_payload(store, current, _read_payload(runtime_path))
    _atomic_write(runtime_path, payload)
    return payload


def set_event_decision(
    store: _review.EventReviewStore,
    candidate_id: str,
    decision: _review.Decision,
) -> _review.ReviewState:
    """Persist one decision and immediately rebuild the display runtime."""

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
    """Make confirmed review state authoritative for the Surface runtime."""

    global _APPLIED, _BASE_SET_EVENT_DECISION
    if _APPLIED:
        return
    _BASE_SET_EVENT_DECISION = _review.EventReviewStore.set_event_decision
    _review.EventReviewStore.set_event_decision = set_event_decision
    _APPLIED = True
    _publish_existing_state()


__all__ = ["apply", "publish_review_state", "set_event_decision"]
