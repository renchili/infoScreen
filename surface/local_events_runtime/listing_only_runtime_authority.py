from __future__ import annotations

from typing import Any

from . import extract as _extract
from . import review_runtime_authority as _runtime

_APPLIED = False
_BASE_CONFIRMED_EVENT = None


def _listing_only(raw: dict[str, Any]) -> bool:
    detail_url = _runtime._canonical_url(raw.get("detail_url"))
    listing_url = _runtime._canonical_url(raw.get("listing_url"))
    return bool(detail_url and detail_url == listing_url)


def confirmed_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    event = _BASE_CONFIRMED_EVENT(raw)
    if event is None:
        return None
    if not _listing_only(raw):
        return event

    event = dict(event)
    event.update(
        listing_only=True,
        detail_available=False,
        source_type="operator_confirmed_official_listing_card_without_detail",
        listing_card_id=str(raw.get("candidate_id") or ""),
    )
    return event


def _identity(event: dict[str, Any]) -> str:
    url = _runtime._canonical_url(event.get("url"))
    if event.get("listing_only") is True:
        card_id = _extract.clean(event.get("listing_card_id"))
        return f"listing:{url}:{card_id}"
    return f"url:{url}"


def merge_confirmed_events(payload: dict[str, Any]) -> dict[str, Any]:
    state = _runtime._load_state()
    rows = state.get("events")
    confirmed = [
        event
        for raw in (rows if isinstance(rows, list) else [])
        if isinstance(raw, dict)
        if (event := confirmed_event(raw)) is not None
    ]

    results = [
        dict(item)
        for item in payload.get("results") or []
        if isinstance(item, dict)
    ]
    by_identity = {
        _identity(item): index
        for index, item in enumerate(results)
        if _runtime._canonical_url(item.get("url"))
    }
    added = 0
    updated = 0

    for event in confirmed:
        key = _identity(event)
        existing_index = by_identity.get(key)
        if existing_index is None:
            by_identity[key] = len(results)
            results.append(event)
            added += 1
            continue

        current = dict(results[existing_index])
        for field, value in event.items():
            if value not in {"", None}:
                current[field] = value
        results[existing_index] = current
        updated += 1

    source_order = {
        _extract.norm_key((row or {}).get("title")): index
        for index, row in enumerate(payload.get("sources") or [])
        if isinstance(row, dict)
    }
    indexed = list(enumerate(results))
    indexed.sort(
        key=lambda pair: (
            source_order.get(
                _extract.norm_key(
                    pair[1].get("source_name") or pair[1].get("host")
                ),
                10_000,
            ),
            pair[0],
        )
    )

    merged = dict(payload)
    merged["results"] = [item for _, item in indexed]
    merged["count"] = len(results)
    merged["review_authority"] = {
        "confirmed_in_state": len(confirmed),
        "added": added,
        "updated": updated,
        "feedback_state_path": str(_runtime._review_state_path()),
    }
    return merged


def apply() -> None:
    global _APPLIED, _BASE_CONFIRMED_EVENT
    if _APPLIED:
        return
    _BASE_CONFIRMED_EVENT = _runtime._confirmed_event
    _runtime._confirmed_event = confirmed_event
    _runtime._merge_confirmed_events = merge_confirmed_events
    _APPLIED = True


__all__ = ["apply", "confirmed_event", "merge_confirmed_events"]
