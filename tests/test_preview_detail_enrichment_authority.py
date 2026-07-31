from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import (  # noqa: E402
    preview_direct_detail_collector_authority as authority,
)
from local_events_runtime.event_review import (  # noqa: E402
    EventReviewStore,
    ListingPageCandidate,
    ReviewState,
    stable_id,
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
                        "official_home": "https://www.marinabaysands.com/museum.html",
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
                    candidate_id=stable_id("artscience", LISTING_URL),
                    source_id="artscience",
                    source_name="ArtScience Museum",
                    url=LISTING_URL,
                    origin="configured",
                    decision="confirmed",
                    discovered_at="2026-07-30T00:00:00+00:00",
                )
            ]
        )
    )
    return store


def _listing_payload() -> dict:
    return {
        "rows": [
            {
                "detail_url": DETAIL_URL,
                "title": "Another World Is Possible",
                "when": "",
                "where": "ArtScience Museum",
                "summary": "View details",
                "selector": "article.event-card:nth-of-type(1)",
                "document_position": {
                    "x": 152,
                    "y": 1633,
                    "width": 243,
                    "height": 76,
                },
                "viewport_position": {
                    "x": 152,
                    "y": 100,
                    "width": 243,
                    "height": 76,
                },
                "text": "Another World Is Possible\nView details",
            }
        ],
        "observed": {
            "final_url": LISTING_URL,
            "page_title": "Exhibition Archive | ArtScience Museum",
            "body_text_length": 1200,
            "visible_link_count": 20,
            "same_domain_link_count": 10,
            "detail_link_count": 1,
            "extracted_card_count": 1,
            "admitted_card_count": 1,
            "marked_card_count": 1,
            "cards_with_evidence": 1,
            "cards_with_selector": 1,
            "detail_link_examples": [
                {"text": "Another World Is Possible", "url": DETAIL_URL}
            ],
        },
    }


def _install_fake_playwright(monkeypatch, payload: dict):
    order: list[str] = []
    launches: list[object] = []
    contexts: list[object] = []
    pages: list[object] = []

    class Response:
        status = 200

    class Page:
        def __init__(self, context, index: int):
            self.context = context
            self.index = index
            self.closed = False
            self.url = LISTING_URL if index == 0 else DETAIL_URL
            pages.append(self)

        def goto(self, url, *, wait_until, timeout):
            assert self.index == 0
            assert url == LISTING_URL
            assert wait_until == "domcontentloaded"
            assert timeout == authority._preview.PREVIEW_PAGE_TIMEOUT_MS
            order.append("listing_goto")
            return Response()

        def wait_for_timeout(self, value):
            assert value == authority._preview.PREVIEW_SETTLE_MS
            order.append("listing_settle")

        def evaluate(self, script, args):
            assert self.index == 0
            assert script == authority._preview.PREVIEW_LISTING_JS
            assert args["listingUrl"] == LISTING_URL
            assert args["sourceId"] == "artscience"
            order.append("listing_evaluate")
            return payload

        def is_closed(self):
            return self.closed

        def close(self):
            if not self.closed:
                self.closed = True
                order.append(
                    "listing_close" if self.index == 0 else "detail_close"
                )

    class Context:
        def __init__(self, marker):
            self.marker = marker
            self.closed = False
            self.page_count = 0
            contexts.append(self)

        def new_page(self):
            page = Page(self, self.page_count)
            self.page_count += 1
            order.append(
                "listing_page" if page.index == 0 else "detail_page"
            )
            return page

        def close(self):
            self.closed = True
            order.append("context_close")

    class Browser:
        version = "150.0"

        def __init__(self, marker):
            self.marker = marker
            self.close_count = 0

        def new_context(self, **kwargs):
            assert kwargs == {
                "viewport": {"width": 1440, "height": 1200},
                "device_scale_factor": 1,
            }
            order.append("context_open")
            return Context(self.marker)

        def close(self):
            self.close_count += 1
            order.append("browser_close")

    def launch(_playwright):
        marker = object()
        browser = Browser(marker)
        launches.append(browser)
        order.append("browser_launch")
        return browser

    monkeypatch.setattr(authority._browser, "launch_chromium", launch)

    sync_api = ModuleType("playwright.sync_api")

    class PlaywrightContext:
        def __enter__(self):
            order.append("playwright_enter")
            return object()

        def __exit__(self, exc_type, exc, traceback):
            order.append("playwright_exit")
            return False

    sync_api.sync_playwright = lambda: PlaywrightContext()
    package = ModuleType("playwright")
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return SimpleNamespace(
        order=order,
        launches=launches,
        contexts=contexts,
        pages=pages,
    )


def test_direct_preview_collects_listing_and_detail_in_one_context(
    monkeypatch,
    tmp_path,
) -> None:
    store = _store(tmp_path)
    runtime = _install_fake_playwright(monkeypatch, _listing_payload())
    detail_calls = []

    monkeypatch.setattr(authority._effective, "apply", lambda: None)

    def collect_detail(page, source, listing_url, detail_url):
        detail_calls.append((page, source, listing_url, detail_url))
        runtime.order.append("detail_collect")
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

    result = authority.collect_preview(store)

    assert len(runtime.launches) == 1
    assert runtime.launches[0].close_count == 1
    assert len(runtime.contexts) == 1
    assert runtime.contexts[0].closed is True
    assert len(runtime.pages) == 2
    assert all(page.closed for page in runtime.pages)
    assert detail_calls == [
        (
            runtime.pages[1],
            store.inventory()[0],
            LISTING_URL,
            DETAIL_URL,
        )
    ]
    assert runtime.pages[0].context is runtime.pages[1].context
    assert runtime.order.index("listing_goto") < runtime.order.index(
        "detail_collect"
    ) < runtime.order.index("context_close") < runtime.order.index("browser_close")

    candidate = result.events[0]
    expected_id = stable_id("artscience", LISTING_URL, DETAIL_URL)
    assert candidate.candidate_id == expected_id
    assert candidate.detail_url == FINAL_DETAIL_URL
    assert candidate.detail_status == "collected"
    assert candidate.detail_error == ""
    assert candidate.when == "13 Sep 2025 – 22 Feb 2026"
    assert candidate.summary.startswith("An exhibition exploring")
    assert candidate.detail_page_title == "Another World Is Possible"

    assert result.event_collection["preview_browser_process_count"] == 1
    assert result.event_collection["preview_browser_reuse"] == "listing_and_details"
    assert result.event_collection["preview_detail_context_count"] == 1
    assert result.event_collection["preview_detail_transport"] == (
        "same_browser_context"
    )
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_requests_skipped"] == 0
    assert result.event_collection["detail_page_error_count"] == 0
    assert result.event_collection["preview_candidate_listing_detail_urls"] == {
        expected_id: DETAIL_URL,
    }
    assert store.load().events[0].detail_url == FINAL_DETAIL_URL


def test_direct_preview_detail_failure_does_not_open_a_second_browser(
    monkeypatch,
    tmp_path,
) -> None:
    store = _store(tmp_path)
    runtime = _install_fake_playwright(monkeypatch, _listing_payload())

    monkeypatch.setattr(authority._effective, "apply", lambda: None)

    def fail_detail(page, source, listing_url, detail_url):
        runtime.order.append("detail_collect")
        raise RuntimeError("detail exploded")

    monkeypatch.setattr(
        authority._artscience_detail,
        "collect_detail_candidate",
        fail_detail,
    )

    result = authority.collect_preview(store)

    assert len(runtime.launches) == 1
    assert runtime.launches[0].close_count == 1
    assert len(runtime.contexts) == 1
    assert len(runtime.pages) == 2
    assert all(page.closed for page in runtime.pages)
    assert runtime.order.count("browser_launch") == 1
    assert runtime.order.count("browser_close") == 1

    candidate = result.events[0]
    assert candidate.candidate_id == stable_id(
        "artscience",
        LISTING_URL,
        DETAIL_URL,
    )
    assert candidate.detail_url == DETAIL_URL
    assert candidate.detail_status == "failed"
    assert "RuntimeError: detail exploded" in candidate.detail_error
    assert result.event_collection["detail_page_request_count"] == 1
    assert result.event_collection["detail_page_error_count"] == 1
    assert result.event_collection["detail_page_errors"][0]["detail_url"] == (
        DETAIL_URL
    )


def test_direct_preview_apply_replaces_the_exact_preview_entrypoint(
    monkeypatch,
) -> None:
    original = object()
    monkeypatch.setattr(authority, "_APPLIED", False)
    monkeypatch.setattr(authority._preview, "_collect_preview", original)

    authority.apply()

    assert authority._APPLIED is True
    assert authority._preview._collect_preview is authority.collect_preview
