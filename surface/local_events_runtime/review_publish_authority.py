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
_REVIEW_OVERLAY_BASE = "review_overlay_base"


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


def _collector_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Restore the collector row underneath any previous Review field overlay.

    A confirmed Review row may replace stale title/date/venue/summary fields on a
    matching collector row. The untouched collector row is stored inside the
    published row so RESET or NOT RELATED can deterministically restore it later.
    Pure Review-only rows have no base and are removed before rebuilding the current
    confirmed set.
    """

    results: list[dict[str, Any]] = []
    for raw in payload.get("results") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("review_publish_origin") != _REVIEW_PUBLISH_ORIGIN:
            results.append(dict(raw))
            continue
        base = raw.get(_REVIEW_OVERLAY_BASE)
        if isinstance(base, dict):
            results.append(dict(base))
    return results


def _matching_system_index(
    results: list[dict[str, Any]],
    event: dict[str, Any],
    consumed: set[int],
) -> int | None:
    event_url = _canonical_url(event.get("url"))
    semantic_key = _semantic_identity(event)

    if event.get("listing_only") is not True and event_url:
        for index, row in enumerate(results):
            if index in consumed:
                continue
            if _canonical_url(row.get("url")) == event_url:
                return index

    if semantic_key:
        for index, row in enumerate(results):
            if index in consumed:
                continue
            if _semantic_identity(row) == semantic_key:
                return index
    return None


def _overlay_review_fields(
    collector_row: dict[str, Any],
    review_event: dict[str, Any],
) -> dict[str, Any]:
    """Use confirmed Review fields while preserving collector metadata and order."""

    merged = dict(collector_row)
    merged.update(review_event)
    merged[_REVIEW_OVERLAY_BASE] = dict(collector_row)
    merged["review_publish_origin"] = _REVIEW_PUBLISH_ORIGIN
    return merged


def merge_review_state(
    payload: dict[str, Any],
    store: _review.EventReviewStore,
    state: _review.ReviewState | None = None,
) -> dict[str, Any]:
    """Publish the current confirmed Review state over collector output.

    System-only rows are preserved exactly. When a confirmed candidate has the same
    canonical detail URL as a collector row, the confirmed title/date/venue/summary
    replace stale collector fields in that row while collector ordering and evidence
    remain intact. Review-only activities are appended. Every publish first restores
    the collector base, making RESET and NOT RELATED reversible.
    """

    current = state or store.load()
    system_results = _collector_results(payload)
    consumed_system_indices: set[int] = set()
    published_urls: set[str] = set()
    published_semantic_keys: set[str] = set()

    added = 0
    replaced = 0
    already_present = 0
    review_results: list[dict[str, Any]] = []

    for candidate in _confirmed_candidates(store, current):
        event = _confirmed_event(candidate)
        event_url = _canonical_url(event.get("url"))
        semantic_key = _semantic_identity(event)
        system_index = _matching_system_index(
            system_results,
            event,
            consumed_system_indices,
        )

        if system_index is not None:
            system_results[system_index] = _overlay_review_fields(
                system_results[system_index],
                event,
            )
            consumed_system_indices.add(system_index)
            if event_url:
                published_urls.add(event_url)
            if semantic_key:
                published_semantic_keys.add(semantic_key)
            replaced += 1
            continue

        duplicate_review = (
            semantic_key in published_semantic_keys
            if event.get("listing_only") is True
            else bool(event_url and event_url in published_urls)
            or semantic_key in published_semantic_keys
        )
        if duplicate_review:
            already_present += 1
            continue

        if event_url:
            published_urls.add(event_url)
        if semantic_key:
            published_semantic_keys.add(semantic_key)
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
        "replaced": replaced,
        "already_present": already_present,
        "mode": "confirmed_review_fields_override_matching_collector_rows",
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
    """Persist one decision and immediately publish the current confirmed set."""

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
    """Install immediate, reversible publication of Event review decisions."""

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
