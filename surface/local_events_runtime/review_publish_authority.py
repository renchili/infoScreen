from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

from . import event_review as _review
from . import extract as _extract

_APPLIED = False
_BASE_SET_EVENT_DECISION = None
_REVIEW_PUBLISH_ORIGIN = "review_state"
_LEGACY_REVIEW_OVERLAY_BASE = "review_overlay_base"
COLLECTOR_RUNTIME_FILENAME = "local_event_collector_results.json"
DISPLAY_RUNTIME_FILENAME = "local_event_search_results.json"


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": True, "results": [], "count": 0}
    return payload if isinstance(payload, dict) else {"ok": True, "results": [], "count": 0}


def _canonical_url(value: object) -> str:
    try:
        return _review.canonical_url(value)
    except (TypeError, ValueError):
        return ""


def collector_runtime_path(store: _review.EventReviewStore) -> Path:
    """Return the private collector snapshot used to build the kiosk projection."""

    return store.root.parent / COLLECTOR_RUNTIME_FILENAME


def display_runtime_path(store: _review.EventReviewStore) -> Path:
    """Return the public Local Events runtime rendered by the kiosk."""

    return store.root.parent / DISPLAY_RUNTIME_FILENAME


def _published_title(candidate: _review.EventCandidate) -> str:
    title = _extract.clean(candidate.title)
    if title:
        return title
    for line in _extract.lines(candidate.evidence.text):
        if line:
            return line
    source = _extract.clean(candidate.source_name or candidate.source_id)
    return f"{source or 'Local'} activity"


def _review_event(candidate: _review.EventCandidate) -> dict[str, Any]:
    """Convert one reviewed candidate without re-running crawler admission."""

    listing_url = _canonical_url(candidate.listing_url)
    detail_url = _canonical_url(candidate.detail_url) or listing_url
    when = _extract.clean(candidate.when)
    dates = _extract.label_dates(when)
    source_name = _extract.clean(candidate.source_name or candidate.source_id)
    listing_only = not detail_url or detail_url == listing_url

    return {
        "title": _published_title(candidate),
        "when": when,
        "where": _extract.clean(candidate.where),
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
        "operator_review_decision": candidate.decision,
        "review_publish_origin": _REVIEW_PUBLISH_ORIGIN,
        "review_candidate_id": candidate.candidate_id,
        "reviewed_at": candidate.reviewed_at or "",
        "collected_at": candidate.collected_at,
    }


def _semantic_identity(event: dict[str, Any]) -> str:
    return _extract.semantic_key(event)


def _ordered_candidates(
    store: _review.EventReviewStore,
    state: _review.ReviewState,
    decisions: Iterable[str],
) -> list[_review.EventCandidate]:
    accepted = set(decisions)
    source_order = {
        str(source.get("id") or ""): index
        for index, source in enumerate(store.inventory())
    }
    rows = [
        (index, candidate)
        for index, candidate in enumerate(state.events)
        if candidate.decision in accepted
    ]
    rows.sort(
        key=lambda item: (
            source_order.get(item[1].source_id, 10_000),
            item[0],
        )
    )
    return [candidate for _, candidate in rows]


def clean_collector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove Review projection rows and migrate the legacy embedded-base format.

    The collector snapshot must contain only producer-owned rows. Older projected
    runtimes embedded an original row under ``review_overlay_base``. During migration
    that base is restored; Review-only rows are omitted.
    """

    results: list[dict[str, Any]] = []
    for raw in payload.get("results") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("review_publish_origin") != _REVIEW_PUBLISH_ORIGIN:
            results.append(dict(raw))
            continue
        legacy_base = raw.get(_LEGACY_REVIEW_OVERLAY_BASE)
        if isinstance(legacy_base, dict):
            results.append(dict(legacy_base))

    cleaned = dict(payload)
    cleaned["results"] = results
    cleaned["count"] = len(results)
    cleaned.pop("review_publish", None)
    return cleaned


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


def write_collector_snapshot(
    store: _review.EventReviewStore,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist one producer-owned snapshot without Review projection fields."""

    cleaned = clean_collector_payload(payload)
    atomic_write(collector_runtime_path(store), cleaned)
    return cleaned


def load_collector_snapshot(store: _review.EventReviewStore) -> dict[str, Any]:
    """Load the producer snapshot, migrating the current display runtime once.

    Existing installations do not yet have ``local_event_collector_results.json``.
    The first read derives a clean collector base from the current primary runtime,
    including restoration of the legacy embedded-base format, and persists it before
    rebuilding the display projection.
    """

    path = collector_runtime_path(store)
    if path.is_file():
        return clean_collector_payload(_read_payload(path))

    migrated = clean_collector_payload(_read_payload(display_runtime_path(store)))
    write_collector_snapshot(store, migrated)
    return migrated


def _matching_collector_index(
    results: list[dict[str, Any]],
    event: dict[str, Any],
    unavailable: set[int],
) -> int | None:
    event_url = _canonical_url(event.get("url"))
    semantic_key = _semantic_identity(event)

    if event.get("listing_only") is not True and event_url:
        for index, row in enumerate(results):
            if index in unavailable:
                continue
            if _canonical_url(row.get("url")) == event_url:
                return index

    if semantic_key:
        for index, row in enumerate(results):
            if index in unavailable:
                continue
            if _semantic_identity(row) == semantic_key:
                return index
    return None


def _overlay_confirmed_fields(
    collector_row: dict[str, Any],
    review_event: dict[str, Any],
) -> dict[str, Any]:
    """Use non-empty confirmed fields while retaining collector evidence metadata."""

    merged = dict(collector_row)
    protected_if_empty = {"title", "where", "summary"}
    date_fields = {"when", "start_date", "end_date"}

    for key, value in review_event.items():
        if key in protected_if_empty:
            if _extract.clean(value):
                merged[key] = value
            continue
        if key in date_fields:
            continue
        merged[key] = value

    if _extract.clean(review_event.get("when")):
        merged["when"] = review_event["when"]
        merged["start_date"] = review_event.get("start_date") or ""
        merged["end_date"] = review_event.get("end_date") or ""

    merged["review_publish_origin"] = _REVIEW_PUBLISH_ORIGIN
    return merged


def _complete_review_only_event(event: dict[str, Any]) -> dict[str, Any]:
    """Fill only the minimum display fallback for a Review-only activity."""

    completed = dict(event)
    if not _extract.clean(completed.get("where")):
        completed["where"] = _extract.clean(
            completed.get("source_name") or completed.get("host")
        )
    return completed


def merge_review_state(
    payload: dict[str, Any],
    store: _review.EventReviewStore,
    state: _review.ReviewState | None = None,
) -> dict[str, Any]:
    """Project Review decisions over a clean collector snapshot.

    ``confirmed`` replaces matching collector fields or appends a Review-only row.
    ``rejected`` suppresses a matching collector row. ``pending`` leaves the collector
    row unchanged. The projection is rebuilt from the producer snapshot every time,
    so RESET restores collector output without embedding a second row inside the
    public kiosk payload.
    """

    current = state or store.load()
    collector = clean_collector_payload(payload)
    system_results = [dict(item) for item in collector.get("results") or []]
    consumed: set[int] = set()
    suppressed: set[int] = set()
    published_urls: set[str] = set()
    published_semantic_keys: set[str] = set()

    added = 0
    replaced = 0
    rejected = 0
    already_present = 0
    review_only_results: list[dict[str, Any]] = []

    for candidate in _ordered_candidates(store, current, {"confirmed"}):
        event = _review_event(candidate)
        event_url = _canonical_url(event.get("url"))
        semantic_key = _semantic_identity(event)
        system_index = _matching_collector_index(system_results, event, consumed)

        if system_index is not None:
            system_results[system_index] = _overlay_confirmed_fields(
                system_results[system_index],
                event,
            )
            consumed.add(system_index)
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
        review_only_results.append(_complete_review_only_event(event))
        added += 1

    for candidate in _ordered_candidates(store, current, {"rejected"}):
        event = _review_event(candidate)
        system_index = _matching_collector_index(
            system_results,
            event,
            consumed | suppressed,
        )
        if system_index is None:
            continue
        suppressed.add(system_index)
        rejected += 1

    results = [
        row
        for index, row in enumerate(system_results)
        if index not in suppressed
    ]
    results.extend(review_only_results)

    merged = dict(collector)
    merged["ok"] = bool(collector.get("ok", True))
    merged["results"] = results
    merged["count"] = len(results)
    merged["updated_at"] = _review.utc_now()
    merged["review_publish"] = {
        "published_at": merged["updated_at"],
        "confirmed_count": len(_ordered_candidates(store, current, {"confirmed"})),
        "rejected_count": len(_ordered_candidates(store, current, {"rejected"})),
        "added": added,
        "replaced": replaced,
        "suppressed": rejected,
        "already_present": already_present,
        "mode": "review_projection_over_collector_snapshot",
        "collector_snapshot": str(collector_runtime_path(store)),
        "state_path": str(store.state_path),
    }
    return merged


def publish_review_state(
    store: _review.EventReviewStore,
    state: _review.ReviewState | None = None,
) -> dict[str, Any]:
    """Rebuild and atomically publish the kiosk runtime from current authorities."""

    collector = load_collector_snapshot(store)
    payload = merge_review_state(collector, store, state)
    atomic_write(display_runtime_path(store), payload)
    return payload


def set_event_decision(
    store: _review.EventReviewStore,
    candidate_id: str,
    decision: _review.Decision,
) -> _review.ReviewState:
    """Persist one decision and immediately rebuild the kiosk projection."""

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
    """Install immediate deterministic publication of Event review decisions."""

    global _APPLIED, _BASE_SET_EVENT_DECISION
    if _APPLIED:
        return
    _BASE_SET_EVENT_DECISION = _review.EventReviewStore.set_event_decision
    _review.EventReviewStore.set_event_decision = set_event_decision
    _APPLIED = True
    _publish_existing_state()


__all__ = [
    "COLLECTOR_RUNTIME_FILENAME",
    "DISPLAY_RUNTIME_FILENAME",
    "apply",
    "atomic_write",
    "clean_collector_payload",
    "collector_runtime_path",
    "display_runtime_path",
    "load_collector_snapshot",
    "merge_review_state",
    "publish_review_state",
    "set_event_decision",
    "write_collector_snapshot",
]
