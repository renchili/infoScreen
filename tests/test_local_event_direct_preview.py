from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_collector_authority as preview  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
)


LISTING_URL = "https://www.marinabaysands.com/museum/whats-on.html"
DETAIL_URL = "https://www.marinabaysands.com/museum/exhibitions/future-world.html"


def preview_store(tmp_path) -> EventReviewStore:
    config = tmp_path / "event_sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "artscience",
                        "name": "ArtScience Museum",
                        "allowed_domains": ["marinabaysands.com"],
                        "default_venue": "ArtScience Museum",
                        "listing_urls": [LISTING_URL],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = EventReviewStore(tmp_path / "infoscreen-event-preview-test", config)
    store.save(
        ReviewState(
            listing_pages=[
                ListingPageCandidate(
                    candidate_id="artscience-preview",
                    source_id="artscience",
                    source_name="ArtScience Museum",
                    url=LISTING_URL,
                    origin="configured",
                    decision="confirmed",
                    discovered_at="2026-07-28T00:00:00+00:00",
                )
            ]
        )
    )
    return store


def install_fake_playwright(monkeypatch, rows):
    class Page:
        url = LISTING_URL

        def goto(self, url, *, wait_until, timeout):
            assert url == LISTING_URL
            assert wait_until == "domcontentloaded"
            assert timeout == preview.PREVIEW_PAGE_TIMEOUT_MS
            return SimpleNamespace(status=200)

        def wait_for_timeout(self, milliseconds):
            assert milliseconds == preview.PREVIEW_SETTLE_MS

        def evaluate(self, script, args):
            assert script == preview.PREVIEW_LISTING_JS
            assert args["listingUrl"] == LISTING_URL
            assert args["allowedDomains"] == ["marinabaysands.com"]
            return rows

    class Browser:
        def new_page(self, **kwargs):
            assert kwargs["viewport"] == {"width": 1440, "height": 1200}
            return Page()

        def close(self):
            return None

    monkeypatch.setattr(preview._browser, "launch_chromium", lambda playwright: Browser())

    sync_api = ModuleType("playwright.sync_api")

    class PlaywrightContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    sync_api.sync_playwright = lambda: PlaywrightContext()
    package = ModuleType("playwright")
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_preview_bypasses_formal_collector_and_audit_pipeline(monkeypatch, tmp_path) -> None:
    store = preview_store(tmp_path)
    formal_calls = []
    monkeypatch.setattr(
        preview,
        "_BASE_COLLECT",
        lambda store: formal_calls.append(store) or (_ for _ in ()).throw(
            AssertionError("formal collector must not run for preview")
        ),
    )
    install_fake_playwright(
        monkeypatch,
        [
            {
                "title": "teamLab Future World",
                "when": "Daily",
                "where": "",
                "summary": "Interactive permanent exhibition.",
                "detail_url": DETAIL_URL,
                "text": "teamLab Future World\nDaily",
                "selector": '[data-infoscreen-preview-index="0"]',
                "document_position": {"x": 10, "y": 20, "width": 300, "height": 200},
                "viewport_position": {"x": 10, "y": 20, "width": 300, "height": 200},
            }
        ],
    )

    state = preview.collect_event_candidates(store)

    assert formal_calls == []
    assert [event.title for event in state.events] == ["teamLab Future World"]
    assert state.events[0].detail_url == DETAIL_URL
    assert state.events[0].where == "ArtScience Museum"
    assert state.event_collection["preview_mode"] == "direct_single_page_main_content"
    assert state.event_collection["formal_collector_bypassed"] is True
    assert state.event_collection["selector_audit_skipped"] is True
    assert state.event_collection["listing_diagnostics_skipped"] is True


def test_non_preview_store_still_uses_formal_collector(monkeypatch, tmp_path) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)
    expected = ReviewState(event_collection={"formal": True})
    monkeypatch.setattr(preview, "_BASE_COLLECT", lambda actual: expected)

    assert preview.collect_event_candidates(store) is expected


def test_direct_preview_script_does_not_run_formal_audits() -> None:
    script = preview.PREVIEW_LISTING_JS

    assert 'root.querySelectorAll("a[href]")' in script
    assert 'document.querySelectorAll("a[href]")' not in script
    assert "CARD_EVIDENCE_JS" not in script
    assert "LISTING_DIAGNOSTIC_JS" not in script
    assert "networkidle" not in script
