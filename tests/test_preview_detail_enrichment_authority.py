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
FINAL_DETAIL_URL = (
    "https://www.marinabaysands.com/museum/exhibitions/"
    "another-world-is-possible-canonical.html"
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


def _candidate(index: int, detail_url: str) -> EventCandidate:
    return EventCandidate(
        candidate_id=f"old-preview-id-{index}",
        source_id="artscience",
        source_name="ArtScience Museum",
        listing_url=LISTING_URL,
        detail_url=detail_url,
        title=f"ArtScience candidate {index}",
        when="",
        where="ArtScience Museum",
        summary="View details",
        detail_status="incomplete",
        detail_error="preview_listing_evidence_only_missing_when",
        detail_page_title="",
        evidence=EventEvidence(
            selector=f'[data-infoscreen-preview-index="{index}"]',
            selector_index=index,
            selector_match_count=1,
            document_position={
                "x": 152 + index * 296,
                "y": 1633,
                "width": 243,
                "height": 76,
            },
            viewport_position={
                "x": 152 + index * 296,
                "y": 100,
                "width": 243,
                "height": 76,
            },
            page_index=0,
            page_url=LISTING_URL,
            text=f"ArtScience candidate {index}\nView details",
        ),
        collected_at="2026-07-30T00:00:00+00:00",
    )


def _listing_only_state(count: int = 1) -> ReviewState:
    urls = [
        DETAIL_URL,
        "https://www.marinabaysands.com/museum/exhibitions/insects.html",
    ]
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
        events=[_candidate(index, urls[index]) for index in range(count)],
        event_collection={
            "preview_mode": "direct_single_page_main_content",
            "detail_page_requests_skipped": count,
            "listing_diagnostics": [],
        },
    )


def _install_fake_playwright(monkeypatch):
    launches = []

    class Page:
        def __init__(self, marker):
            self.marker = marker
            self.closed = False

        def is_closed(self):
            return self.closed

        def close(self):
            self.closed = True

    class Context:
        def __init__(self, marker):
            self.marker = marker

        def new_page(self):
            return Page(self.marker)

        def close(self):
            return None

    class Browser:
        def __init__(self, marker):
            self.marker = marker

        def new_context(self, **kwargs):
            assert kwargs == {
                "viewport": {"width": 1440, "height": 1000},
                "device_scale_factor": 1,
            }
            return Context(self.marker)

        def close(self):
            return None

    def launch(_playwright):
        marker = object()
        launches.append(marker)
        return Browser(marker)

    monkeypatch.setattr(authority._browser, "launch_chromium", launch)

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
    return launches


def test_real_preview_entrypoint_reads_artscience_detail_page(monkeypatch, tmp_path) -> None:
    store = _store(tmp_path)
    state = _listing_only_state()
    base_calls = []
    monkeypatch.setattr(
        authority,
        "_BASE_PREVIEW_COLLECT",
        lambda actual: base_calls.append(actual) or state,
    )
    launches = _install_fake_playwright(monkeypatch)
    calls = []

    monkeypatch.setattr(authority._effective, "apply", lambda: None)
    monkeypatch.setattr(
        authority._effective,
        "detail_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("ArtScience Preview must use its source detail owner")
        ),
    )

    def collect_detail(page, source, listing_url, detail_url):
        calls.append((page.marker, source, listing_url, detail_url))
        return {
            "detail_url": FINAL_DETAIL_URL,
            "title": "Another World Is Possible",
            "when": "13 Sep 2025 – 22 Feb 2026",
            "where": "ArtScience Museum",
            "summary": "An exhibition exploring how new worlds can be imagined.",
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": "Another World Is Possible",
        }

    monkeypatch.setattr(
        authority._artscience_detail,
        "collect_detail_candidate",
        collect_detail,
    )

    result = authority.collect_preview_with_details(store)

    assert base_calls == [store]
    assert len(launches) == 1
    assert calls == [(launches[0], store.inventory()[0], LISTING_URL, DETAIL_URL)]
    assert result.events[0].candidate_id == "old-preview-id-0"
    assert result.events[0].detail_url == FINAL_DETAIL_URL
    assert result.events[0].detail_status == "collected"
    assert result.events[0].detail_error == ""
    assert result.events[0].when == "13 Sep 2025 – 22 Feb 2026"
    assert result.events[0].summary.startswith("An exhibition exploring")
    assert result.events[0].detail_page_title == "Another World Is Possible"
    assert result.event_collection["preview_detail_mode"] == "official_detail_pages"
    assert result.event_collection["preview_candidate_listing_detail_urls"] == {
        "old-preview-id-0": DETAIL_URL,
    }
    assert result.event_collection["preview_detail_transport"] == "shared_browser_context"
    assert result.event_collection["preview_detail_context_count"] == 1
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_requests_skipped"] == 0


def test_all_artscience_details_share_one_browser_context(monkeypatch, tmp_path) -> None:
    store = _store(tmp_path)
    state = _listing_only_state(count=2)
    monkeypatch.setattr(authority, "_BASE_PREVIEW_COLLECT", lambda actual: state)
    launches = _install_fake_playwright(monkeypatch)
    page_markers = []

    monkeypatch.setattr(authority._effective, "apply", lambda: None)

    def collect_detail(page, source, listing_url, detail_url):
        page_markers.append(page.marker)
        return {
            "detail_url": detail_url,
            "title": detail_url.rsplit("/", 1)[-1],
            "when": "1 Jan 2026 – 31 Dec 2026",
            "where": "ArtScience Museum",
            "summary": "Collected detail summary.",
            "detail_status": "collected",
            "detail_error": "",
            "detail_page_title": detail_url.rsplit("/", 1)[-1],
        }

    monkeypatch.setattr(
        authority._artscience_detail,
        "collect_detail_candidate",
        collect_detail,
    )

    result = authority.collect_preview_with_details(store)

    assert len(launches) == 1
    assert page_markers == [launches[0], launches[0]]
    assert result.event_collection["preview_detail_transport"] == "shared_browser_context"
    assert result.event_collection["preview_detail_context_count"] == 1
    assert result.event_collection["detail_page_error_count"] == 0
    assert all(event.detail_status == "collected" for event in result.events)


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
