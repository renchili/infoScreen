from __future__ import annotations

from typing import Any

from . import event_review as _review

_APPLIED = False
_BASE_COLLECT = None
FALLBACK_DISCOVERY_TIMEOUT_MS = 15_000


def _configured(source: dict[str, Any]) -> bool:
    return any(str(value or "").strip() for value in source.get("listing_urls") or [])


def _discover_missing_sources(
    playwright: Any,
    sources: list[dict[str, Any]],
    candidates: dict[str, _review.ListingPageCandidate],
    started: str,
    errors: list[dict[str, str]],
) -> None:
    if not sources:
        return

    browser = _review.launch_chromium(playwright)
    try:
        for source in sources:
            source_id = str(source.get("id") or "")
            source_name = str(source.get("name") or source_id)
            home = str(source.get("official_home") or "").strip()
            if not home:
                errors.append(
                    {
                        "source_id": source_id,
                        "error": "missing_official_home_and_listing_urls",
                    }
                )
                continue

            page = browser.new_page(
                viewport={"width": 1440, "height": 1000},
                device_scale_factor=1,
            )
            try:
                # Listing discovery only needs the rendered navigation document. Waiting
                # for network-idle lets analytics, media and long polling consume the full
                # timeout, then the old collector repeated navigation with a second wait.
                page.goto(
                    home,
                    wait_until="domcontentloaded",
                    timeout=min(
                        FALLBACK_DISCOVERY_TIMEOUT_MS,
                        max(1, int(_review.DOM_TIMEOUT_MS)),
                    ),
                )
                rows = page.evaluate(
                    _review.LISTING_DISCOVERY_JS,
                    {"allowedDomains": source.get("allowed_domains") or []},
                ) or []
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
                        discovered_at=started,
                    )
            except Exception as exc:
                errors.append(
                    {
                        "source_id": source_id,
                        "error": f"{type(exc).__name__}: {exc}"[:500],
                    }
                )
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    finally:
        browser.close()


def collect_listing_pages(store: _review.EventReviewStore) -> _review.ReviewState:
    """Collect verified configured listing entrypoints without redundant home scans.

    The source inventory already defines verified official listing entrypoints. Those
    URLs are authoritative inputs and are added synchronously. Chromium discovery is a
    bounded fallback only for sources that have no configured listing URL at all.
    """

    started = _review.utc_now()
    inventory = store.inventory()
    candidates = _review._configured_listing_candidates(inventory, started)
    missing_sources = [source for source in inventory if not _configured(source)]
    errors: list[dict[str, str]] = []

    if missing_sources:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                _discover_missing_sources(
                    playwright,
                    missing_sources,
                    candidates,
                    started,
                    errors,
                )
        except Exception as exc:
            errors.append(
                {
                    "source_id": "*",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )

    configured_source_ids = [
        str(source.get("id") or "") for source in inventory if _configured(source)
    ]
    missing_source_ids = [
        str(source.get("id") or "") for source in missing_sources
    ]
    return store.replace_listing_pages(
        list(candidates.values()),
        {
            "started_at": started,
            "completed_at": _review.utc_now(),
            "candidate_count": len(candidates),
            "configured_source_count": len(configured_source_ids),
            "configured_source_ids": configured_source_ids,
            "browser_discovery_source_count": len(missing_source_ids),
            "browser_discovery_source_ids": missing_source_ids,
            "homepage_discovery_skipped_source_count": len(configured_source_ids),
            "homepage_discovery_policy": "skip_when_verified_listing_urls_exist",
            "errors": errors,
        },
    )


def apply() -> None:
    global _APPLIED, _BASE_COLLECT
    if _APPLIED:
        _review.collect_listing_pages = collect_listing_pages
        return

    _BASE_COLLECT = _review.collect_listing_pages
    _review.collect_listing_pages = collect_listing_pages
    _APPLIED = True


__all__ = [
    "FALLBACK_DISCOVERY_TIMEOUT_MS",
    "apply",
    "collect_listing_pages",
]
