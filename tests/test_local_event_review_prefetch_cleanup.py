from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_detail_prefetch_authority as prefetch  # noqa: E402
from local_events_runtime import review_prefetch_cleanup_authority as cleanup  # noqa: E402


class FakePage:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events
        self.closed = False
        self.url = "about:blank"

    def goto(self, url: str, **_: object):
        self.events.append(f"goto:{self.name}:{url}")
        self.url = url
        return None

    def evaluate(self, script: str):
        self.events.append(f"stop:{self.name}")
        return True

    def close(self) -> None:
        self.events.append(f"close:{self.name}")
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed


class FakeContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.created: list[FakePage] = []

    @property
    def pages(self):
        return list(self.created)

    def new_page(self) -> FakePage:
        page = FakePage(f"page-{len(self.created)}", self.events)
        self.created.append(page)
        return page

    def close(self) -> None:
        self.events.append("context-close")


def _unused_entry(context, page: FakePage, url: str = "https://example.test/detail") -> None:
    state = prefetch._state(context)
    state.entries[url] = prefetch._PrefetchedDetail(page=page, requested_url=url)
    state.seen.add(url)
    state.page_ids.add(id(page))


def test_context_close_stops_unused_prefetch_before_browser_context_close() -> None:
    events: list[str] = []
    context = cleanup._ContextProxy(FakeContext(events))
    context.new_page()
    unused = context._context.new_page()
    _unused_entry(context, unused)

    context.close()

    assert events == ["stop:page-1", "close:page-1", "context-close"]
    assert id(context) not in prefetch._STATES


def test_next_listing_navigation_cleans_previous_prefetch_batch() -> None:
    events: list[str] = []
    context = cleanup._ContextProxy(FakeContext(events))
    listing = context.new_page()

    listing.goto("https://example.test/listing-one")
    unused = context._context.new_page()
    _unused_entry(context, unused)
    listing.goto("https://example.test/listing-two")

    assert events == [
        "goto:page-0:https://example.test/listing-one",
        "stop:page-1",
        "close:page-1",
        "goto:page-0:https://example.test/listing-two",
    ]
    assert id(context) not in prefetch._STATES


def test_prefetch_cleanup_is_installed_with_existing_lifecycle_authority() -> None:
    lifecycle = read_text(
        "surface/local_events_runtime/review_prefetch_lifecycle_authority.py"
    )

    assert "apply_prefetch_cleanup()" in lifecycle
    assert "before BrowserContext.close()" in lifecycle
