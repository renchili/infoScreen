from __future__ import annotations

import json
import sys
from types import ModuleType

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_detail_enrichment_authority as authority  # noqa: E402
from local_events_runtime.event_review import (  # noqa: E402
    EventCandidate,
    EventEvidence,
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
)

LISTING_URL = (
    "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html"
)
DETAIL_URL = (
    "https://www.marinabaysands.com/museum/exhibitions/"
    "another-world-is-possible.html"
)


def _store(tmp_path) -> EventReviewStore:
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
    return EventReviewStore(tmp_path / "infoscreen-event-preview-test", config)


def _listing_only_state() -> ReviewState:
    return ReviewState(
        listing_pages=[
            ListingPageCandidate(
                candidate_id="listing",
                source_id="artscience",
                source_name="ArtScience Museum",
                url=LISTING_URL,
                origin="configured",
                decision="confirmed",
                discovered_at="2026-07-30T00:00:00+00:00",
            )
        ],
        events=[
            EventCandidate(
                candidate_id="old-preview-id",
                source_id="artscience",
                source_name="ArtScience Museum",
                listing_url=LISTING_URL,
                detail_url=DETAIL_URL,
                title="Another World Is Possible",
                when="",
                where="ArtScience Museum",
                summary="Another World Is Possible\nView details",
                detail_status="incomplete",
                detail_error="preview_listing_evidence_only_missing_when",
                detail_page_title="",
                evidence=EventEvidence(
                    selector='[data-infoscreen-preview-index="0"]',
                    selector_index=0,
                    selector_match_count=1,
                    document_position={
                        "x": 152,
                        "y": 1633,
                        "width": 243,
                        "height": 76,
                    },
                    viewport_position={
                        "x": 152,
                        "y": 100,
                        "width": 243,
                        "height": 76,
                    },
                    page_index=0,
                    page_url=LISTING_URL,
                    text="Another World Is Possible\nView details",
                ),
                collected_at="2026-07-30T00:00:00+00:00",
            )
        ],
        event_collection={
            "preview_mode": "direct_single_page_main_content",
            "detail_page_requests_skipped": 1,
            "listing_diagnostics": [],
        },
    )


def _install_fake_playwright(monkeypatch):
    context = object()

    class Browser:
        def new_context(self, **kwargs):
            assert kwargs == {
                "viewport": {"width": 1440, "height": 1000},
                "device_scale_factor": 1,
            }

            class Context:
                marker = context

                def close(self):
                    return None

            return Context()

        def close(self):
            return None

    monkeypatch.setattr(
        authority._browser,
        "launch_chromium",
        lambda playwright: Browser(),
    )

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
    return context


def test_real_preview_entrypoint_reads_official_detail_page(monkeypatch, tmp_path) -> None:
    store = _store(tmp_path)
    state = _listing_only_state()
    base_calls = []
    monkeypatch.setattr(
        authority,
        "_BASE_PREVIEW_COLLECT",
        lambda actual: base_calls.append(actual) or state,
    )
    expected_context = _install_fake_playwright(monkeypatch)
    calls = []

    monkeypatch.setattr(authority._effective, "apply", lambda: None)

    def detail_candidate(context, source, listing_url, detail_url, card):
        calls.append((context.marker, source, listing_url, detail_url, card))
        return {
            "detail_url": DETAIL_URL,
            "title": "Another World Is Possible",
            "when": "13 Sep 2025 – 22 Feb 2026",
            "where": "ArtScience Museum",
            "summary": "An exhibition exploring how new worlds can be imagined.",
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": "Another World Is Possible | ArtScience Museum",
        }

    monkeypatch.setattr(authority._effective, "detail_candidate", detail_candidate)

    result = authority.collect_preview_with_details(store)

    assert base_calls == [store]
    assert len(calls) == 1
    assert calls[0][0] is expected_context
    assert calls[0][1]["id"] == "artscience"
    assert calls[0][2:4] == (LISTING_URL, DETAIL_URL)
    assert calls[0][4] == {
        "url": DETAIL_URL,
        "headings": ["Another World Is Possible"],
        "link_text": "Another World Is Possible",
        "text_lines": ["Another World Is Possible"],
        "text": "Another World Is Possible",
    }
    assert result.events[0].detail_status == "collected"
    assert result.events[0].detail_error == ""
    assert result.events[0].when == "13 Sep 2025 – 22 Feb 2026"
    assert result.events[0].summary.startswith("An exhibition exploring")
    assert result.events[0].detail_page_title.startswith("Another World Is Possible")
    assert result.event_collection["preview_detail_mode"] == "official_detail_pages"
    assert result.event_collection["preview_detail_enrichment_entrypoint"] == (
        "preview_collector._collect_preview"
    )
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_requests_skipped"] == 0


def test_apply_replaces_the_actual_preview_function(monkeypatch) -> None:
    original = object()
    monkeypatch.setattr(authority, "_APPLIED", False)
    monkeypatch.setattr(authority, "_BASE_PREVIEW_COLLECT", None)
    monkeypatch.setattr(authority._preview, "_collect_preview", original)

    authority.apply()

    assert authority._BASE_PREVIEW_COLLECT is original
    assert authority._preview._collect_preview is authority.collect_preview_with_details


def test_non_preview_state_is_not_enriched(monkeypatch, tmp_path) -> None:
    config = tmp_path / "event_sources.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    store = EventReviewStore(tmp_path / "review", config)
    expected = ReviewState(event_collection={"formal": True})
    monkeypatch.setattr(
        authority._browser,
        "launch_chromium",
        lambda playwright: (_ for _ in ()).throw(
            AssertionError("formal collection must not be enriched")
        ),
    )

    assert authority.enrich_preview_state(store, expected) is expected
