from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from . import event_review as _review
from .manual_listing import MANUAL_LINK_TEXT

DISCOVERY_TIMEOUT_MS = 20_000
_MBS_DOMAIN = "marinabaysands.com"


def _source(store: _review.EventReviewStore, source_id: str) -> dict[str, Any]:
    requested = str(source_id or "").strip()
    if not requested:
        raise ValueError("source_id is required")
    return store.source(requested)


def _configured_candidates(
    source: dict[str, Any],
    discovered_at: str,
) -> dict[str, _review.ListingPageCandidate]:
    source_id = str(source.get("id") or "")
    source_name = str(source.get("name") or source_id)
    candidates: dict[str, _review.ListingPageCandidate] = {}
    for value in source.get("listing_urls") or []:
        url = _review.canonical_url(value)
        candidate_id = _review.stable_id(source_id, url)
        candidates[candidate_id] = _review.ListingPageCandidate(
            candidate_id=candidate_id,
            source_id=source_id,
            source_name=source_name,
            url=url,
            origin="configured",
            discovered_at=discovered_at,
        )
    return candidates


def _requires_headed_browser(source: dict[str, Any]) -> bool:
    host = (urlsplit(str(source.get("official_home") or "")).hostname or "")
    host = host.lower().removeprefix("www.")
    return host == _MBS_DOMAIN or host.endswith("." + _MBS_DOMAIN)


def _launch_browser(playwright: Any, source: dict[str, Any]):
    if not _requires_headed_browser(source):
        return _review.launch_chromium(playwright)

    # MBS resets stream 1 for the deployed Snap Chromium in headless HTTP/2 mode.
    # The existing Preview transport already owns the verified headed launch policy.
    from . import preview_transport_authority as transport

    if not transport._graphical_session_available():
        raise RuntimeError(
            "ArtScience list-page discovery requires the existing Surface graphical "
            "session; DISPLAY and WAYLAND_DISPLAY are both missing"
        )
    original_headless = transport._PREVIEW_HEADLESS
    transport._PREVIEW_HEADLESS = False
    try:
        return transport._launch_preview_chromium(playwright)
    finally:
        transport._PREVIEW_HEADLESS = original_headless


def _discover_home_links(
    source: dict[str, Any],
    candidates: dict[str, _review.ListingPageCandidate],
    discovered_at: str,
    errors: list[dict[str, str]],
) -> None:
    home = str(source.get("official_home") or "").strip()
    if not home:
        errors.append(
            {
                "source_id": str(source.get("id") or ""),
                "error": "missing_official_home",
            }
        )
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, source)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
            )
            try:
                page.goto(
                    home,
                    wait_until="domcontentloaded",
                    timeout=DISCOVERY_TIMEOUT_MS,
                )
                rows = page.evaluate(
                    _review.LISTING_DISCOVERY_JS,
                    {"allowedDomains": source.get("allowed_domains") or []},
                ) or []
                source_id = str(source.get("id") or "")
                source_name = str(source.get("name") or source_id)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    url = _review.canonical_url(row.get("url"))
                    if not _review._host_allowed(url, source):
                        continue
                    candidate_id = _review.stable_id(source_id, url)
                    if candidate_id in candidates:
                        continue
                    candidates[candidate_id] = _review.ListingPageCandidate(
                        candidate_id=candidate_id,
                        source_id=source_id,
                        source_name=source_name,
                        url=url,
                        origin="discovered",
                        link_text=str(row.get("link_text") or "")[:240],
                        discovered_at=discovered_at,
                    )
            finally:
                page.close()
        finally:
            browser.close()


def _merge_selected_source(
    store: _review.EventReviewStore,
    source_id: str,
    candidates: dict[str, _review.ListingPageCandidate],
    collection: dict[str, Any],
) -> _review.ReviewState:
    state = store.load()
    previous_selected = {
        item.candidate_id: item
        for item in state.listing_pages
        if item.source_id == source_id
    }

    selected_rows: list[_review.ListingPageCandidate] = []
    for candidate in candidates.values():
        previous = previous_selected.get(candidate.candidate_id)
        if previous is not None:
            candidate.decision = previous.decision
            candidate.reviewed_at = previous.reviewed_at
        selected_rows.append(candidate)

    present = {item.candidate_id for item in selected_rows}
    selected_rows.extend(
        item
        for item in previous_selected.values()
        if item.candidate_id not in present and item.link_text == MANUAL_LINK_TEXT
    )
    removed_urls = sorted(
        item.url
        for item in previous_selected.values()
        if item.candidate_id not in present and item.link_text != MANUAL_LINK_TEXT
    )

    from . import preview_event_selection_authority as selection

    selection_snapshot = selection._selection_snapshot(store)
    selection_changed = False
    if removed_urls:
        selections = selection._load(store)
        listings = selections.setdefault("listings", {})
        for url in removed_urls:
            if url in listings:
                del listings[url]
                selection_changed = True
        if selection_changed:
            selection._save(store, selections)

    state.listing_pages = sorted(
        [item for item in state.listing_pages if item.source_id != source_id]
        + selected_rows,
        key=lambda item: (item.source_name.casefold(), item.url),
    )
    state.listing_collection = collection
    try:
        saved = store.save(state)
    except Exception as exc:
        if selection_changed:
            try:
                selection._restore_selection_snapshot(store, selection_snapshot)
            except Exception as rollback_exc:
                raise RuntimeError(
                    "List Page discovery state write failed and retired Preview "
                    "selection rollback also failed: "
                    f"{rollback_exc}"
                ) from exc
        raise

    for url in removed_urls:
        selection.invalidate_preview_manifest(url)
    return saved


def collect_listing_pages_for_source(
    store: _review.EventReviewStore,
    source_id: str,
) -> _review.ReviewState:
    """Discover candidate list pages for exactly one institution before confirmation."""

    source = _source(store, source_id)
    selected_source_id = str(source.get("id") or "")
    started = _review.utc_now()
    candidates = _configured_candidates(source, started)
    errors: list[dict[str, str]] = []

    try:
        _discover_home_links(source, candidates, started, errors)
    except Exception as exc:
        errors.append(
            {
                "source_id": selected_source_id,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
        )

    return _merge_selected_source(
        store,
        selected_source_id,
        candidates,
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "scope": "single_institution_before_confirmation",
            "source_id": selected_source_id,
            "source_name": str(source.get("name") or selected_source_id),
            "candidate_count": len(candidates),
            "configured_candidate_count": len(source.get("listing_urls") or []),
            "homepage_discovery_attempted": True,
            "homepage_discovery_timeout_ms": DISCOVERY_TIMEOUT_MS,
            "errors": errors,
        },
    )


__all__ = ["DISCOVERY_TIMEOUT_MS", "collect_listing_pages_for_source"]