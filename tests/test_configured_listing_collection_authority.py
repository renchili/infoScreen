from __future__ import annotations

import inspect
import json
import sys
from types import ModuleType, SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import configured_listing_collection_authority as authority  # noqa: E402
from local_events_runtime.event_review import EventReviewStore  # noqa: E402


def _store(tmp_path, sources) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return EventReviewStore(tmp_path / "review", config)


def test_verified_configured_listing_urls_do_not_launch_chromium(monkeypatch, tmp_path) -> None:
    store = _store(
        tmp_path,
        [
            {
                "id": "artscience",
                "name": "ArtScience Museum",
                "official_home": "https://www.marinabaysands.com/museum.html",
                "allowed_domains": ["marinabaysands.com"],
                "listing_urls": [
                    "https://www.marinabaysands.com/museum/whats-on.html",
                    "https://www.marinabaysands.com/museum/whats-on.html?tab=event",
                ],
            }
        ],
    )
    monkeypatch.setattr(
        authority._review,
        "launch_chromium",
        lambda playwright: (_ for _ in ()).throw(
            AssertionError("configured listing collection must not launch Chromium")
        ),
    )

    state = authority.collect_listing_pages(store)

    assert len(state.listing_pages) == 2
    assert {item.origin for item in state.listing_pages} == {"configured"}
    assert state.listing_collection["configured_source_count"] == 1
    assert state.listing_collection["browser_discovery_source_count"] == 0
    assert state.listing_collection["homepage_discovery_skipped_source_count"] == 1
    assert state.listing_collection["errors"] == []


def test_unconfigured_source_uses_one_domcontentloaded_navigation(monkeypatch, tmp_path) -> None:
    store = _store(
        tmp_path,
        [
            {
                "id": "example",
                "name": "Example Institution",
                "official_home": "https://example.com/",
                "allowed_domains": ["example.com"],
                "listing_urls": [],
            }
        ],
    )
    navigations = []

    class Page:
        def goto(self, url, *, wait_until, timeout):
            navigations.append((url, wait_until, timeout))
            return SimpleNamespace(status=200)

        def evaluate(self, script, args):
            assert script == authority._review.LISTING_DISCOVERY_JS
            assert args == {"allowedDomains": ["example.com"]}
            return [
                {
                    "url": "https://example.com/events",
                    "link_text": "Events",
                }
            ]

        def close(self):
            return None

    class Browser:
        def new_page(self, **kwargs):
            assert kwargs["viewport"] == {"width": 1440, "height": 1000}
            return Page()

        def close(self):
            return None

    monkeypatch.setattr(authority._review, "launch_chromium", lambda playwright: Browser())

    sync_api = ModuleType("playwright.sync_api")

    class Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    sync_api.sync_playwright = lambda: Context()
    package = ModuleType("playwright")
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    state = authority.collect_listing_pages(store)

    assert navigations == [
        (
            "https://example.com/",
            "domcontentloaded",
            min(authority.FALLBACK_DISCOVERY_TIMEOUT_MS, authority._review.DOM_TIMEOUT_MS),
        )
    ]
    assert [item.url for item in state.listing_pages] == ["https://example.com/events"]
    assert state.listing_collection["browser_discovery_source_count"] == 1


def test_listing_collection_authority_never_waits_for_network_idle() -> None:
    source = inspect.getsource(authority._discover_missing_sources)

    assert 'wait_until="domcontentloaded"' in source
    assert 'wait_until="networkidle"' not in source
