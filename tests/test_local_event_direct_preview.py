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
DETAIL_URL = "https://www.marinabaysands.com/museum/exhibitions/into-the-ocean.html"


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


def install_fake_playwright(monkeypatch, payload):
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
            assert args["sourceId"] == "artscience"
            return payload

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


def observed(**overrides):
    value = {
        "final_url": LISTING_URL,
        "page_title": "What's On | ArtScience Museum",
        "body_text_length": 1200,
        "visible_link_count": 18,
        "same_domain_link_count": 12,
        "detail_link_count": 3,
        "extracted_card_count": 3,
        "admitted_card_count": 1,
        "marked_card_count": 1,
        "cards_with_evidence": 1,
        "cards_with_selector": 1,
        "detail_link_examples": [
            {"text": "Into the Ocean: Journey Beneath", "url": DETAIL_URL},
        ],
    }
    value.update(overrides)
    return value


def test_preview_bypasses_formal_collector_and_admits_date_less_list_card(monkeypatch, tmp_path) -> None:
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
        {
            "rows": [
                {
                    "title": "Into the Ocean: Journey Beneath",
                    "when": "",
                    "where": "",
                    "summary": "",
                    "detail_url": DETAIL_URL,
                    "text": "Into the Ocean: Journey Beneath",
                    "selector": '[data-infoscreen-preview-index="0"]',
                    "document_position": {"x": 10, "y": 20, "width": 300, "height": 200},
                    "viewport_position": {"x": 10, "y": 20, "width": 300, "height": 200},
                }
            ],
            "observed": observed(),
        },
    )

    state = preview.collect_event_candidates(store)

    assert formal_calls == []
    assert [event.title for event in state.events] == ["Into the Ocean: Journey Beneath"]
    assert state.events[0].when == ""
    assert state.events[0].detail_url == DETAIL_URL
    assert state.events[0].where == "ArtScience Museum"
    assert state.event_collection["preview_mode"] == "direct_single_page_main_content"
    assert state.event_collection["preview_card_policy"] == "rendered_title_and_official_detail_link"
    assert state.event_collection["formal_collector_bypassed"] is True
    assert state.event_collection["selector_audit_skipped"] is True
    assert state.event_collection["listing_diagnostics_skipped"] is False
    diagnostic = state.event_collection["listing_diagnostics"][0]
    assert diagnostic["listing_url"] == LISTING_URL
    assert diagnostic["candidates_created"] == 1
    assert diagnostic["reason_code"] == "candidates_created_fields_incomplete"


def test_zero_preview_returns_exact_page_scoped_recognition_stage(monkeypatch, tmp_path) -> None:
    store = preview_store(tmp_path)
    install_fake_playwright(
        monkeypatch,
        {
            "rows": [],
            "observed": observed(
                extracted_card_count=0,
                admitted_card_count=0,
                marked_card_count=0,
                cards_with_evidence=0,
                cards_with_selector=0,
            ),
        },
    )

    state = preview.collect_event_candidates(store)

    assert state.events == []
    diagnostic = state.event_collection["listing_diagnostics"][0]
    assert diagnostic["listing_url"] == LISTING_URL
    assert diagnostic["detail_link_count"] == 3
    assert diagnostic["extracted_card_count"] == 0
    assert diagnostic["reason_code"] == "activity_links_not_isolated_into_cards"
    assert "3 possible Event detail link" in diagnostic["reason"]


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
    assert "if (!when) continue" not in script
    assert "strong_boundary" in script
    assert 'sourceId !== "artscience"' in script
    assert "/museum\\/(?:exhibitions|events|programmes|programs|experiences)" in script
    assert "descriptiveAnchorTitle" in script
    assert "genericLinkText" in script
    assert "listing_diagnostics" not in script
