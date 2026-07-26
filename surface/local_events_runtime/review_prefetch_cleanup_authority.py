from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import review_detail_prefetch_authority as _prefetch

_APPLIED = False
_BASE_LAUNCH_CHROMIUM = None

_STOP_PAGE_JS = "() => { try { window.stop(); } catch (error) {} return true; }"


def close_prefetched(context: Any) -> int:
    """Stop and close every unconsumed detail page owned by one Review context."""

    state = _prefetch._STATES.pop(id(context), None)
    if state is None:
        return 0

    entries = list(state.entries.values())
    state.entries.clear()
    state.seen.clear()
    state.page_ids.clear()

    closed = 0
    for entry in entries:
        page = entry.page
        try:
            if page.is_closed():
                continue
        except Exception:
            pass
        try:
            page.evaluate(_STOP_PAGE_JS)
        except Exception:
            pass
        try:
            page.close()
            closed += 1
        except Exception:
            # The outer process boundary remains the final guard for a broken
            # Playwright transport, but ordinary unused tabs must not reach
            # BrowserContext.close() while still navigating.
            pass
    return closed


class _PrimaryPageProxy:
    """Clean the previous listing's unused detail batch before a new navigation."""

    def __init__(self, owner: "_ContextProxy", page: Any) -> None:
        self._owner = owner
        self._page = page
        self._navigated = False

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        if self._navigated:
            close_prefetched(self._owner)
        self._navigated = True
        return self._page.goto(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)


class _ContextProxy:
    def __init__(self, context: Any) -> None:
        self._context = context
        self._primary_created = False

    @property
    def pages(self):
        return self._context.pages

    def new_page(self, *args: Any, **kwargs: Any) -> Any:
        page = self._context.new_page(*args, **kwargs)
        if self._primary_created:
            return page
        self._primary_created = True
        return _PrimaryPageProxy(self, page)

    def close(self, *args: Any, **kwargs: Any) -> Any:
        close_prefetched(self)
        return self._context.close(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


class _BrowserProxy:
    def __init__(self, browser: Any) -> None:
        self._browser = browser

    def new_context(self, *args: Any, **kwargs: Any) -> _ContextProxy:
        return _ContextProxy(self._browser.new_context(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)


def launch_chromium(playwright: Any) -> _BrowserProxy:
    """Return contexts that clean unconsumed prefetch batches deterministically."""

    return _BrowserProxy(_BASE_LAUNCH_CHROMIUM(playwright))


def apply() -> None:
    """Install prefetch cleanup before Review creates its BrowserContext."""

    global _APPLIED, _BASE_LAUNCH_CHROMIUM
    if _APPLIED:
        return

    _BASE_LAUNCH_CHROMIUM = _browser.launch_chromium
    _browser.launch_chromium = launch_chromium
    _APPLIED = True


__all__ = [
    "apply",
    "close_prefetched",
    "launch_chromium",
    "_BrowserProxy",
    "_ContextProxy",
    "_PrimaryPageProxy",
]
