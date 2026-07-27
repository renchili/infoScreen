from __future__ import annotations

import sys

from .conftest import SURFACE, read_text

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_detail_navigation_authority as authority  # noqa: E402


LISTING_URL = "https://www.acm.nhb.gov.sg/whats-on/overview"
OVERLAP_LISTING_URL = (
    "https://www.acm.nhb.gov.sg/whats-on/overview"
    "?category=Programmes&time=Today%2CUpcoming"
)
DETAIL_URLS = [
    "https://www.acm.nhb.gov.sg/whats-on/programmes/2026-ltn",
    "https://www.acm.nhb.gov.sg/whats-on/programmes/daily-guided-tours",
    "https://www.acm.nhb.gov.sg/whats-on/exhibitions/crosscurrents",
]
SOURCE = {
    "id": "acm",
    "name": "Asian Civilisations Museum",
    "default_venue": "Asian Civilisations Museum",
    "allowed_domains": ["acm.nhb.gov.sg"],
    "card_selectors": ["a.a-listing-content__anchor-card[href]"],
    "review_detail_policy": "always",
}


class FakeListingPage:
    def __init__(self, urls: list[str]):
        self.url = LISTING_URL
        self._urls = urls
        self.closed = False

    def evaluate(self, script, args=None):
        assert script == authority.PREFETCH_DETAIL_URLS_JS
        assert args == {"selectors": SOURCE["card_selectors"]}
        return list(self._urls)

    def is_closed(self):
        return self.closed


class FakePrefetchPage:
    def __init__(self, events: list[tuple[str, str]]):
        self.url = "about:blank"
        self.main_frame = object()
        self.closed = False
        self.events = events
        self.handlers = {}

    def on(self, event, callback):
        self.handlers[event] = callback

    def evaluate(self, script, arg=None):
        assert script == authority.START_DETAIL_NAVIGATION_JS
        self.url = arg
        self.events.append(("start", arg))
        return True

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class FakePrefetchContext:
    def __init__(self, urls: list[str]):
        self.events: list[tuple[str, str]] = []
        self.pages = [FakeListingPage(urls)]

    def new_page(self):
        page = FakePrefetchPage(self.events)
        self.pages.append(page)
        return page


class CountingPage:
    def __init__(self):
        self.url = "about:blank"
        self.closed = False
        self.goto_count = 0

    def goto(self, url, *, wait_until, timeout):
        self.url = url
        self.goto_count += 1
        assert wait_until == "commit"
        assert timeout == authority.DETAIL_COMMIT_TIMEOUT_MS
        return None

    def wait_for_function(self, script, timeout):
        assert script == authority.DETAIL_READY_JS
        assert timeout == authority.DETAIL_CONTENT_WAIT_MS

    def wait_for_timeout(self, milliseconds):
        assert milliseconds == 150

    def evaluate(self, script, arg=None):
        if script == authority.FALLBACK_DETAIL_FIELDS_JS:
            return {}
        return {
            "title": "LIGHT TO NIGHT AT ACM: POWER OF PLAY",
            "dates": [],
            "venues": [],
            "summary": "Experience ACM after dark through the Power of Play.",
            "summary_candidates": [
                "Experience ACM after dark through the Power of Play."
            ],
            "lines": [
                "LIGHT TO NIGHT AT ACM: POWER OF PLAY",
                "Programmes on 23, 24, 30, 31 Jan 2026, 6–10pm",
                "Asian Civilisations Museum",
            ],
        }

    def title(self):
        return "LIGHT TO NIGHT AT ACM: POWER OF PLAY"

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class CountingContext:
    def __init__(self):
        self.pages = []
        self.created = 0

    def new_page(self):
        self.created += 1
        page = CountingPage()
        self.pages.append(page)
        return page


def reset_states() -> None:
    for state in list(authority._STATES.values()):
        authority._close_entries(state)
    authority._STATES.clear()


def test_detail_concurrency_is_bounded_and_configurable(monkeypatch) -> None:
    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_CONCURRENCY", "6")
    assert authority._detail_concurrency() == 6

    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_CONCURRENCY", "99")
    assert authority._detail_concurrency() == 12

    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_CONCURRENCY", "0")
    assert authority._detail_concurrency() == 1


def test_all_visible_acm_details_start_before_first_detail_wait(monkeypatch) -> None:
    reset_states()
    monkeypatch.setenv("INFOSCREEN_REVIEW_DETAIL_CONCURRENCY", "6")
    context = FakePrefetchContext(DETAIL_URLS)
    state = authority._state(context)

    authority._prepare_prefetch(
        context,
        state,
        SOURCE,
        LISTING_URL,
        DETAIL_URLS[0],
    )

    assert context.events == [("start", url) for url in DETAIL_URLS]
    assert list(state.entries) == DETAIL_URLS
    assert len(context.pages) == 1 + len(DETAIL_URLS)


def test_overlapping_acm_listing_reuses_the_same_detail_result() -> None:
    reset_states()
    context = CountingContext()
    card = {
        "id": "acm-2026-ltn",
        "url": DETAIL_URLS[0],
        "headings": ["LIGHT TO NIGHT AT ACM: POWER OF PLAY"],
        "link_text": "LIGHT TO NIGHT AT ACM: POWER OF PLAY",
        "text": "LIGHT TO NIGHT AT ACM: POWER OF PLAY",
        "text_lines": ["LIGHT TO NIGHT AT ACM: POWER OF PLAY"],
    }

    first = authority._detail_candidate(
        context,
        SOURCE,
        LISTING_URL,
        DETAIL_URLS[0],
        card,
    )
    second = authority._detail_candidate(
        context,
        SOURCE,
        OVERLAP_LISTING_URL,
        DETAIL_URLS[0],
        card,
    )

    assert context.created == 1
    assert first == second
    assert first["when"] == "Programmes on 23, 24, 30, 31 Jan 2026, 6–10pm"
    assert first["where"] == "Asian Civilisations Museum"


def test_dynamic_listing_keeps_scope_but_stops_on_listing_stability() -> None:
    code = read_text(
        "surface/local_events_runtime/dynamic_listing_authority.py"
    )

    assert "const maxRounds = Math.max(0, Number(args.maxRounds || 0));" in code
    assert "Math.max(Number(args.maxRounds || 0), 80)" not in code
    assert "stableRounds >= 2" in code
    assert "body.innerText" not in code
    assert "listingState" in code
