from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import event_review as _review
from . import event_review_diagnostics as _diagnostics
from . import source_overrides as _source_overrides
from .listing_page_policy import rejection_reason as listing_page_rejection_reason

_APPLIED = False
_BASE_SET_LISTING_DECISION = None
_BASE_COLLECT = None
_PROTOCOL_PREFIX = "preview-review-v1:"
_SELECTION_FILE = "preview_event_selections.json"
_PREVIEW_MANIFEST_TTL_ENV = "INFOSCREEN_PREVIEW_MANIFEST_TTL_SECONDS"
_DEFAULT_PREVIEW_MANIFEST_TTL_SECONDS = 21_600
_MIN_PREVIEW_MANIFEST_TTL_SECONDS = 60


def _preview_manifest_ttl_seconds(value: object) -> int:
    """Parse the optional manifest TTL without making service import fragile."""

    raw = str(value or "").strip()
    if not raw:
        return _DEFAULT_PREVIEW_MANIFEST_TTL_SECONDS
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_PREVIEW_MANIFEST_TTL_SECONDS
    return max(_MIN_PREVIEW_MANIFEST_TTL_SECONDS, parsed)


_PREVIEW_MANIFEST_TTL_SECONDS = _preview_manifest_ttl_seconds(
    os.environ.get(
        _PREVIEW_MANIFEST_TTL_ENV,
        str(_DEFAULT_PREVIEW_MANIFEST_TTL_SECONDS),
    )
)
_PREVIEW_MANIFESTS: dict[str, dict[str, Any]] = {}


def _selection_path(store: _review.EventReviewStore) -> Path:
    return store.root / _SELECTION_FILE


def _load(store: _review.EventReviewStore) -> dict[str, Any]:
    path = _selection_path(store)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "listings": {}}
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"invalid preview Event selection state: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("listings"), dict):
        raise RuntimeError("invalid preview Event selection state")
    return payload


def _atomic_replace(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _save(store: _review.EventReviewStore, payload: dict[str, Any]) -> None:
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_replace(_selection_path(store), content)


def _selection_snapshot(store: _review.EventReviewStore) -> bytes | None:
    try:
        return _selection_path(store).read_bytes()
    except FileNotFoundError:
        return None


def _restore_selection_snapshot(
    store: _review.EventReviewStore,
    snapshot: bytes | None,
) -> None:
    path = _selection_path(store)
    if snapshot is not None:
        _atomic_replace(path, snapshot)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _discard_listing_selection(
    store: _review.EventReviewStore,
    listing_url: str,
) -> tuple[bytes | None, bool]:
    """Remove one stale selection record and return rollback material."""

    selections = _load(store)
    listings = selections.setdefault("listings", {})
    if listing_url not in listings:
        return _selection_snapshot(store), False
    snapshot = _selection_snapshot(store)
    del listings[listing_url]
    _save(store, selections)
    return snapshot, True


def _rollback_selection_after_failure(
    store: _review.EventReviewStore,
    snapshot: bytes | None,
    exc: Exception,
) -> None:
    try:
        _restore_selection_snapshot(store, snapshot)
    except Exception as rollback_exc:
        raise RuntimeError(
            "List Page decision failed and Preview selection rollback also failed: "
            f"{rollback_exc}"
        ) from exc


def _decode_protocol(value: str) -> dict[str, Any] | None:
    raw = str(value or "")
    if not raw.startswith(_PROTOCOL_PREFIX):
        return None
    token = raw.removeprefix(_PROTOCOL_PREFIX)
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        raise ValueError(f"invalid preview Event review payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid preview Event review payload")
    return payload


def _host_allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    allowed = [
        str(value or "").lower().removeprefix("www.")
        for value in source.get("allowed_domains") or []
        if str(value or "").strip()
    ]
    return bool(
        host
        and any(host == domain or host.endswith("." + domain) for domain in allowed)
    )


def _listing_revision(listing: _review.ListingPageCandidate) -> str:
    """Revision shared by the real page and its temporary confirmed Preview copy."""

    payload = json.dumps(
        {
            "candidate_id": listing.candidate_id,
            "url": listing.url,
            "discovered_at": listing.discovered_at,
            "reviewed_at": listing.reviewed_at,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _manifest_candidate_rows(
    listing_url: str,
    state: _review.ReviewState,
) -> list[dict[str, str]]:
    raw_listing_urls = state.event_collection.get(
        "preview_candidate_listing_detail_urls"
    )
    listing_urls = raw_listing_urls if isinstance(raw_listing_urls, dict) else {}
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in state.events:
        if _review.canonical_url(candidate.listing_url) != listing_url:
            raise ValueError("Preview returned a candidate from another List Page")
        candidate_id = str(candidate.candidate_id or "").strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError("Preview returned duplicate or missing candidate identity")
        final_url = _review.canonical_url(candidate.detail_url)
        listing_detail_url = _review.canonical_url(
            listing_urls.get(candidate_id) or final_url
        )
        seen.add(candidate_id)
        rows.append(
            {
                "candidate_id": candidate_id,
                "listing_detail_url": listing_detail_url,
                "detail_url": final_url,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["candidate_id"],
            row["listing_detail_url"],
            row["detail_url"],
        ),
    )


def invalidate_preview_manifest(listing_url: str) -> None:
    """Invalidate the process-local candidate manifest for one List Page."""

    try:
        canonical = _review.canonical_url(listing_url)
    except ValueError:
        return
    _PREVIEW_MANIFESTS.pop(canonical, None)


def issue_preview_manifest(
    listing: _review.ListingPageCandidate,
    state: _review.ReviewState,
) -> _review.ReviewState:
    """Record the exact candidate set returned by the latest successful Preview.

    The manifest is process-local and never writes Review state. A server restart,
    expiry, List Page state change, reset, or newer Preview requires the operator to
    Preview again before committing candidate decisions.
    """

    listing_url = _review.canonical_url(listing.url)
    invalidate_preview_manifest(listing_url)
    rows = _manifest_candidate_rows(listing_url, state)
    if not rows:
        return state

    now = time.time()
    expires_at = now + _PREVIEW_MANIFEST_TTL_SECONDS
    _PREVIEW_MANIFESTS[listing_url] = {
        "listing_candidate_id": listing.candidate_id,
        "listing_url": listing_url,
        "listing_revision": _listing_revision(listing),
        "issued_at": now,
        "expires_at": expires_at,
        "candidates": rows,
    }
    state.event_collection = {
        **state.event_collection,
        "preview_selection_manifest_policy": "latest_server_preview_exact_set",
        "preview_selection_manifest_candidate_count": len(rows),
        "preview_selection_manifest_expires_at_epoch": int(expires_at),
    }
    return state


def _preview_manifest(
    listing: _review.ListingPageCandidate,
) -> dict[str, Any]:
    listing_url = _review.canonical_url(listing.url)
    manifest = _PREVIEW_MANIFESTS.get(listing_url)
    if not isinstance(manifest, dict):
        raise ValueError(
            "Preview candidate manifest is missing; run Preview again before saving"
        )
    if float(manifest.get("expires_at") or 0) <= time.time():
        invalidate_preview_manifest(listing_url)
        raise ValueError(
            "Preview candidate manifest expired; run Preview again before saving"
        )
    if manifest.get("listing_candidate_id") != listing.candidate_id:
        invalidate_preview_manifest(listing_url)
        raise ValueError("Preview candidate manifest does not match the List Page")
    if manifest.get("listing_revision") != _listing_revision(listing):
        invalidate_preview_manifest(listing_url)
        raise ValueError(
            "List Page state changed after Preview; run Preview again before saving"
        )
    return manifest


def _validated_review(
    store: _review.EventReviewStore,
    payload: dict[str, Any],
    listing_decision: str,
) -> tuple[str, str, list[dict[str, str]]]:
    if listing_decision not in {"confirmed", "rejected"}:
        raise ValueError(
            "a Preview Event review must confirm or reject the List Page"
        )

    listing_candidate_id = str(payload.get("listing_candidate_id") or "").strip()
    listing_url = _review.canonical_url(payload.get("listing_url"))
    state = store.load()
    listing = next(
        (item for item in state.listing_pages if item.candidate_id == listing_candidate_id),
        None,
    )
    if listing is None:
        raise ValueError("listing candidate not found")
    if listing.url != listing_url:
        raise ValueError("preview Event review does not match the List Page")

    source = store.source(listing.source_id)
    raw_rows = payload.get("decisions")
    if not isinstance(raw_rows, list) or not raw_rows or len(raw_rows) > 200:
        raise ValueError("preview Event review must contain 1 to 200 decisions")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("invalid preview Event decision")
        candidate_id = str(raw.get("candidate_id") or "").strip()
        detail_url = _review.canonical_url(raw.get("detail_url"))
        listing_detail_url = _review.canonical_url(
            raw.get("listing_detail_url") or detail_url
        )
        decision = str(raw.get("decision") or "").strip()
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("every Preview candidate must be REAL EVENT or NOT EVENT")
        if not candidate_id or candidate_id in seen:
            raise ValueError("duplicate or missing Preview candidate identity")
        if not _host_allowed(listing_detail_url, source):
            raise ValueError(
                "Preview candidate listing URL is outside the institution allow-list"
            )
        if not _host_allowed(detail_url, source):
            raise ValueError(
                "Preview candidate detail URL is outside the institution allow-list"
            )
        expected = _review.stable_id(
            listing.source_id,
            listing.url,
            listing_detail_url,
        )
        if candidate_id != expected:
            raise ValueError(
                "Preview candidate identity does not match its official listing link"
            )
        seen.add(candidate_id)
        rows.append(
            {
                "candidate_id": candidate_id,
                "listing_detail_url": listing_detail_url,
                "detail_url": detail_url,
                "decision": decision,
            }
        )

    manifest = _preview_manifest(listing)
    submitted = sorted(
        [
            {
                "candidate_id": row["candidate_id"],
                "listing_detail_url": row["listing_detail_url"],
                "detail_url": row["detail_url"],
            }
            for row in rows
        ],
        key=lambda row: (
            row["candidate_id"],
            row["listing_detail_url"],
            row["detail_url"],
        ),
    )
    if submitted != manifest.get("candidates"):
        raise ValueError(
            "Preview candidate set is incomplete or no longer current; run Preview again"
        )

    real_count = sum(row["decision"] == "confirmed" for row in rows)
    if listing_decision == "confirmed" and real_count == 0:
        raise ValueError("a List Page cannot be confirmed without a REAL EVENT selection")
    if listing_decision == "rejected" and real_count:
        raise ValueError("a rejected List Page cannot contain REAL EVENT selections")
    return listing_candidate_id, listing.url, rows


def _set_listing_decision(
    store: _review.EventReviewStore,
    candidate_id: str,
    decision: _review.Decision,
) -> _review.ReviewState:
    payload = _decode_protocol(candidate_id)
    if payload is not None:
        actual_id, listing_url, rows = _validated_review(store, payload, decision)
        selections = _load(store)
        listings = selections.setdefault("listings", {})
        listings[listing_url] = {
            "listing_candidate_id": actual_id,
            "listing_url": listing_url,
            "reviewed_at": _review.utc_now(),
            "decisions": rows,
        }
        snapshot = _selection_snapshot(store)
        _save(store, selections)
        try:
            state = _BASE_SET_LISTING_DECISION(store, actual_id, decision)
        except Exception as exc:
            _rollback_selection_after_failure(store, snapshot, exc)
            raise
        invalidate_preview_manifest(listing_url)
        return state

    state = store.load()
    listing = next(
        (item for item in state.listing_pages if item.candidate_id == candidate_id),
        None,
    )
    if listing is None:
        raise ValueError("listing candidate not found")

    if decision == "confirmed":
        record = _load(store).get("listings", {}).get(listing.url)
        decisions = record.get("decisions") if isinstance(record, dict) else None
        if not isinstance(decisions, list) or not any(
            isinstance(row, dict) and row.get("decision") == "confirmed"
            for row in decisions
        ):
            raise ValueError(
                "Preview every candidate and select REAL EVENT / NOT EVENT before confirming this List Page"
            )
        state = _BASE_SET_LISTING_DECISION(store, candidate_id, decision)
        invalidate_preview_manifest(listing.url)
        return state

    snapshot, changed = _discard_listing_selection(store, listing.url)
    try:
        state = _BASE_SET_LISTING_DECISION(store, candidate_id, decision)
    except Exception as exc:
        if changed:
            _rollback_selection_after_failure(store, snapshot, exc)
        raise
    invalidate_preview_manifest(listing.url)
    return state


def _confirmed_selections(
    store: _review.EventReviewStore,
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str]]:
    state = store.load()
    records = _load(store).get("listings", {})
    ids: dict[str, set[str]] = {}
    urls: dict[str, set[str]] = {}
    skipped: list[str] = []
    for listing in (item for item in state.listing_pages if item.decision == "confirmed"):
        if listing_page_rejection_reason(listing.url, listing.link_text):
            skipped.append(listing.url)
            continue
        record = records.get(listing.url)
        decisions = record.get("decisions") if isinstance(record, dict) else None
        selected = [
            row
            for row in decisions or []
            if isinstance(row, dict) and row.get("decision") == "confirmed"
        ]
        if not selected:
            skipped.append(listing.url)
            continue
        ids[listing.url] = {str(row.get("candidate_id") or "") for row in selected}
        selected_urls: set[str] = set()
        for row in selected:
            final_url = _review.canonical_url(row.get("detail_url"))
            listing_detail_url = _review.canonical_url(
                row.get("listing_detail_url") or final_url
            )
            selected_urls.update((listing_detail_url, final_url))
        urls[listing.url] = selected_urls
    if not ids:
        raise ValueError("no confirmed List Page has a committed REAL EVENT selection")
    return ids, urls, skipped


def collect_event_candidates(store: _review.EventReviewStore) -> _review.ReviewState:
    if store.root.name.startswith("infoscreen-event-preview-"):
        return _BASE_COLLECT(store)

    selected_ids, selected_urls, skipped_listings = _confirmed_selections(store)
    original_listing_card = _source_overrides._listing_card

    def selected_listing_card(
        source: dict[str, Any],
        raw_card: dict[str, Any],
        listing_url: str,
    ):
        card = original_listing_card(source, raw_card, listing_url)
        if card is None:
            return None
        canonical_listing = _review.canonical_url(listing_url)
        raw_url = str(card.get("url") or "").strip()
        try:
            canonical_detail = _review.canonical_url(raw_url)
        except ValueError:
            return None
        identity = _diagnostics._candidate_identity(card, canonical_detail)
        candidate_id = _review.stable_id(
            str(source.get("id") or ""),
            canonical_listing,
            identity,
        )
        if candidate_id in selected_ids.get(canonical_listing, set()):
            return card
        if canonical_detail in selected_urls.get(canonical_listing, set()):
            return card
        return None

    _source_overrides._listing_card = selected_listing_card
    try:
        state = _BASE_COLLECT(store)
    finally:
        _source_overrides._listing_card = original_listing_card

    allowed_ids = set().union(*selected_ids.values()) if selected_ids else set()
    allowed_urls = set().union(*selected_urls.values()) if selected_urls else set()
    selected_events = []
    for item in state.events:
        try:
            canonical_detail = _review.canonical_url(item.detail_url)
        except ValueError:
            canonical_detail = ""
        if item.candidate_id not in allowed_ids and canonical_detail not in allowed_urls:
            continue
        item.decision = "confirmed"
        item.reviewed_at = _review.utc_now()
        selected_events.append(item)
    state.events = selected_events
    state.event_collection = {
        **state.event_collection,
        "preview_selection_policy": "confirmed_preview_events_only",
        "selected_real_event_count": len(state.events),
        "confirmed_listings_without_real_event_selection": skipped_listings,
    }
    return store.save(state)


def apply() -> None:
    global _APPLIED, _BASE_SET_LISTING_DECISION, _BASE_COLLECT
    if _APPLIED:
        _review.EventReviewStore.set_listing_decision = _set_listing_decision
        _diagnostics.collect_event_candidates = collect_event_candidates
        return

    _BASE_SET_LISTING_DECISION = _review.EventReviewStore.set_listing_decision
    _BASE_COLLECT = _diagnostics.collect_event_candidates
    _review.EventReviewStore.set_listing_decision = _set_listing_decision
    _diagnostics.collect_event_candidates = collect_event_candidates
    _APPLIED = True


__all__ = [
    "apply",
    "collect_event_candidates",
    "invalidate_preview_manifest",
    "issue_preview_manifest",
    "_decode_protocol",
    "_discard_listing_selection",
    "_load",
    "_preview_manifest_ttl_seconds",
    "_restore_selection_snapshot",
    "_set_listing_decision",
]
