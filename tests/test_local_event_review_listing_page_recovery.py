from __future__ import annotations

import sys
from pathlib import Path

from .conftest import SURFACE

sys.path.insert(0, str(SURFACE))

from local_events_runtime import review_listing_page_recovery_authority as authority  # noqa: E402


class _FakePage:
    def __init__(self, *, crash: bool = False, value: object = None) -> None:
        self.crash = crash
        self.value = value
        self.closed = False
        self.goto_calls = 0

    def goto(self, *args, **kwargs):
        self.goto_calls += 1
        if self.crash:
            raise RuntimeError("Page.goto: Page crashed")
        return self.value

    def close(self) -> None:
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed


class _FakeContext:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages_to_create = list(pages)
        self.created: list[_FakePage] = []

    def new_page(self) -> _FakePage:
        page = self.pages_to_create.pop(0)
        self.created.append(page)
        return page


def test_crashed_listing_page_is_replaced_and_navigation_retried_once() -> None:
    crashed = _FakePage(crash=True)
    replacement = _FakePage(value="response")
    context = _FakeContext([crashed, replacement])
    page = authority._RecoveringListingPage(context, context.new_page())

    result = page.goto("https://example.test/events", wait_until="networkidle")

    assert result == "response"
    assert crashed.goto_calls == 1
    assert crashed.closed is True
    assert replacement.goto_calls == 1
    assert context.created == [crashed, replacement]


def test_non_crash_navigation_error_is_not_retried() -> None:
    class FailingPage(_FakePage):
        def goto(self, *args, **kwargs):
            self.goto_calls += 1
            raise RuntimeError("Page.goto: net::ERR_NAME_NOT_RESOLVED")

    failed = FailingPage()
    spare = _FakePage(value="unexpected")
    context = _FakeContext([failed, spare])
    page = authority._RecoveringListingPage(context, context.new_page())

    try:
        page.goto("https://example.test/events")
    except RuntimeError as exc:
        assert "ERR_NAME_NOT_RESOLVED" in str(exc)
    else:
        raise AssertionError("non-crash navigation error should propagate")

    assert failed.goto_calls == 1
    assert failed.closed is False
    assert context.created == [failed]


def test_only_first_context_page_gets_listing_recovery_wrapper() -> None:
    first = _FakePage(value="listing")
    second = _FakePage(value="detail")
    raw = _FakeContext([first, second])
    context = authority._ReviewContext(raw)

    listing = context.new_page()
    detail = context.new_page()

    assert isinstance(listing, authority._RecoveringListingPage)
    assert detail is second
