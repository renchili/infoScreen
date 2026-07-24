from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_detail_prefetch_authority as prefetch  # noqa: E402


LISTING_URL = "https://www.acm.nhb.gov.sg/whats-on/overview"
DETAIL_URLS = [
    "https://www.acm.nhb.gov.sg/whats-on/exhibitions/elegant-sounds",
    "https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents",
    "https://www.acm.nhb.gov.sg/whats-on/programmes/crossing-cultures",
]


class FakeListingPage:
    def __init__(self, urls: list[str]):
        self.url = LISTING_URL
        self._urls = urls

    def evaluate(self, script, args=None):
        assert script == prefetch.PREFETCH_DETAIL_URLS_JS
        return list(self._urls)

    def is_closed(self):
        return False


class FakeDetailPage:
    def __init__(self, events: list[tuple[str, str]]):
        self.url = "about:blank"
        self.main_frame = object()
        self._events = events
        self._closed = False
        self._handlers = {}

    def on(self, event, callback):
        self._handlers[event] = callback

    def evaluate(self, script, arg=None):
        assert script == prefetch.START_DETAIL_NAVIGATION_JS
        self.url = arg
        self._events.append(("start", arg))
        return True

    def wait_for_function(self, script, timeout):
        self._events.append(("wait", self.url))
        assert script == prefetch.WAIT_FOR_NAVIGATION_JS
        assert timeout > 0
        return True

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True


class FakeContext:
    def __init__(self, urls: list[str]):
        self.events: list[tuple[str, str]] = []
        self.pages = [FakeListingPage(urls)]

    def new_page(self):
        page = FakeDetailPage(self.events)
        self.pages.append(page)
        return page


def reset_state() -> None:
    prefetch._STATES.clear()


def test_prefetch_starts_every_visible_detail_before_any_wait(monkeypatch) -> None:
    reset_state()
    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_PREFETCH", "12")
    context = FakeContext(DETAIL_URLS)

    prefetch._prefetch_listing_details(
        context,
        {"card_selectors": [".a-listing-content"]},
        LISTING_URL,
        DETAIL_URLS[0],
    )

    assert context.events == [("start", url) for url in DETAIL_URLS]
    assert len(prefetch._state(context).entries) == len(DETAIL_URLS)
    assert all(kind != "wait" for kind, _ in context.events)


def test_prefetch_limit_bounds_open_tabs(monkeypatch) -> None:
    reset_state()
    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_PREFETCH", "2")
    context = FakeContext(DETAIL_URLS)

    prefetch._prefetch_listing_details(
        context,
        {"card_selectors": [".a-listing-content"]},
        LISTING_URL,
        DETAIL_URLS[0],
    )

    assert context.events == [("start", url) for url in DETAIL_URLS[:2]]
    assert len(prefetch._state(context).entries) == 2


def test_prefetched_proxy_waits_without_starting_a_second_navigation() -> None:
    page = FakeDetailPage([])
    page.url = DETAIL_URLS[0]
    entry = prefetch._PrefetchedDetail(page=page, requested_url=DETAIL_URLS[0])
    entry.status["value"] = 200

    response = prefetch._PrefetchedPageProxy(entry).goto(
        DETAIL_URLS[0],
        wait_until="commit",
        timeout=60_000,
    )

    assert response.status == 200
    assert page._events == [("wait", DETAIL_URLS[0])]


def test_detail_candidate_reuses_prefetched_page(monkeypatch) -> None:
    reset_state()
    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_PREFETCH", "12")
    context = FakeContext(DETAIL_URLS)

    def base(context_proxy, source, listing_url, raw_url, card):
        page = context_proxy.new_page()
        response = page.goto(raw_url, wait_until="commit", timeout=60_000)
        return {
            "detail_url": page.url,
            "status": response.status if response is not None else None,
        }

    monkeypatch.setattr(prefetch, "_BASE_DETAIL_CANDIDATE", base)
    result = prefetch._detail_candidate(
        context,
        {"card_selectors": [".a-listing-content"]},
        LISTING_URL,
        DETAIL_URLS[0],
        {},
    )

    assert result["detail_url"] == DETAIL_URLS[0]
    assert context.events[: len(DETAIL_URLS)] == [
        ("start", url) for url in DETAIL_URLS
    ]
    assert context.events[-1] == ("wait", DETAIL_URLS[0])


def test_http_bootstrap_installs_prefetch_after_detail_reader() -> None:
    bootstrap = read_text("surface/local_events_runtime/http1_browser.py")

    navigation = bootstrap.index("apply_review_detail_navigation_authority()")
    prefetch_apply = bootstrap.index("apply_review_detail_prefetch_authority()")
    binding = bootstrap.index("_bind_final_browser_runtime_to_review()")

    assert navigation < prefetch_apply < binding
