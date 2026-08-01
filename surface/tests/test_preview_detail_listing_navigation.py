from __future__ import annotations

import inspect
import sys
from types import SimpleNamespace

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import preview_direct_detail_collector_authority as authority  # noqa: E402


LISTING_URL = (
    "https://www.marinabaysands.com/museum/about-us/exhibition-archive.html"
)
DETAIL_URL = (
    "https://www.marinabaysands.com/museum/exhibitions/"
    "another-world-is-possible.html"
)


class Page:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls = []
        self.wait_calls = []
        self.front_calls = 0
        self.close_calls = 0

    def goto(self, url, *, wait_until, timeout):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url
        return SimpleNamespace(status=200)

    def wait_for_timeout(self, timeout):
        self.wait_calls.append(timeout)

    def bring_to_front(self):
        self.front_calls += 1

    def is_closed(self):
        return self.close_calls > 0

    def close(self):
        self.close_calls += 1


class Context:
    def __init__(self) -> None:
        self.pages = []

    def new_page(self):
        page = Page()
        self.pages.append(page)
        return page


def test_listing_and_detail_each_use_a_fresh_page_first_navigation(
    monkeypatch,
) -> None:
    context = Context()
    listing = SimpleNamespace(source_id="artscience", url=LISTING_URL)
    source = {
        "allowed_domains": ["marinabaysands.com"],
        "default_venue": "ArtScience Museum",
    }
    raw = {
        "detail_url": DETAIL_URL,
        "title": "Another World Is Possible",
    }
    parsed = {
        "detail_url": DETAIL_URL,
        "title": "Another World Is Possible",
        "when": "13 Sep 2025 – 22 Feb 2026",
        "where": "ArtScience Museum",
        "summary": "",
        "detail_status": "collected",
        "detail_error": "",
        "detail_page_title": "Another World Is Possible",
    }

    listing_page, _response = authority._open_page_like_listing(
        context,
        LISTING_URL,
        "listing",
    )
    monkeypatch.setattr(
        authority._artscience_detail,
        "read_loaded_detail_candidate",
        lambda actual_page, actual_source, listing_url, requested_url: parsed,
    )

    result = authority._collect_artscience_detail(
        context,
        source,
        listing,
        raw,
    )

    assert len(context.pages) == 2
    detail_page = context.pages[1]
    expected = (
        "domcontentloaded",
        authority._preview.PREVIEW_PAGE_TIMEOUT_MS,
    )
    assert listing_page.goto_calls == [(LISTING_URL, *expected)]
    assert detail_page.goto_calls == [(DETAIL_URL, *expected)]
    assert listing_page.url == LISTING_URL
    assert detail_page.front_calls == 1
    assert detail_page.close_calls == 1
    assert result is parsed


def test_artscience_detail_does_not_reuse_listing_page_or_click() -> None:
    helper_source = inspect.getsource(authority._open_page_like_listing)
    detail_source = inspect.getsource(authority._collect_artscience_detail)

    assert "context.new_page()" in helper_source
    assert ".goto(" in helper_source
    assert 'wait_until="domcontentloaded"' in helper_source
    assert "_open_page_like_listing(" in detail_source
    assert ".click(" not in detail_source
    assert "expect_navigation" not in detail_source
    assert "go_back" not in detail_source
    assert "listing_page" not in detail_source
    assert 'wait_until="commit"' not in helper_source
    assert 'wait_until="commit"' not in detail_source
