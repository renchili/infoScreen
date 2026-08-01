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
        self.url = LISTING_URL
        self.goto_calls = []
        self.wait_calls = []
        self.front_calls = 0

    def goto(self, url, *, wait_until, timeout):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url
        return SimpleNamespace(status=200)

    def wait_for_timeout(self, timeout):
        self.wait_calls.append(timeout)

    def bring_to_front(self):
        self.front_calls += 1

    def is_closed(self):
        return False

    def evaluate(self, script, args):
        return {"rows": [], "observed": {}}


def test_artscience_detail_uses_the_exact_listing_navigation_operation(
    monkeypatch,
) -> None:
    page = Page()
    listing = SimpleNamespace(
        source_id="artscience",
        url=LISTING_URL,
    )
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

    monkeypatch.setattr(
        authority._artscience_detail,
        "read_loaded_detail_candidate",
        lambda actual_page, actual_source, listing_url, requested_url: parsed,
    )
    monkeypatch.setattr(authority, "_mark_listing_page", lambda *args: None)

    result = authority._read_artscience_detail_like_listing(
        page,
        source,
        listing,
        raw,
    )

    expected = (
        "domcontentloaded",
        authority._preview.PREVIEW_PAGE_TIMEOUT_MS,
    )
    assert page.goto_calls == [
        (DETAIL_URL, *expected),
        (LISTING_URL, *expected),
    ]
    assert page.wait_calls == [
        authority._preview.PREVIEW_SETTLE_MS,
        authority._preview.PREVIEW_SETTLE_MS,
    ]
    assert page.front_calls == 1
    assert result is parsed


def test_listing_style_navigation_does_not_use_click_or_commit_wait() -> None:
    helper_source = inspect.getsource(authority._goto_like_listing)
    detail_source = inspect.getsource(authority._read_artscience_detail_like_listing)

    assert ".goto(" in helper_source
    assert 'wait_until="domcontentloaded"' in helper_source
    assert "_goto_like_listing(" in detail_source
    assert ".click(" not in detail_source
    assert "expect_navigation" not in detail_source
    assert 'wait_until="commit"' not in helper_source
    assert 'wait_until="commit"' not in detail_source
