from __future__ import annotations

from typing import Any

from . import browser as _browser

_APPLIED = False
_BASE_LAUNCH_CHROMIUM = None


def _is_page_crash(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    return "page crashed" in text or "target page, context or browser has been closed" in text


class _RecoveringListingPage:
    """Replace a crashed listing Page once and keep the caller's Page handle valid."""

    def __init__(self, context: Any, page: Any) -> None:
        self._context = context
        self._page = page

    def _replace(self) -> None:
        stale = self._page
        try:
            if not stale.is_closed():
                stale.close()
        except Exception:
            pass
        self._page = self._context.new_page()

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._page.goto(*args, **kwargs)
        except Exception as exc:
            if not _is_page_crash(exc):
                raise
            self._replace()
            return self._page.goto(*args, **kwargs)

    def close(self, *args: Any, **kwargs: Any) -> Any:
        return self._page.close(*args, **kwargs)

    def is_closed(self) -> bool:
        return bool(self._page.is_closed())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)


class _ReviewContext:
    """Wrap only the collector's first Page, which is the shared listing Page."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self._listing_page_created = False

    def new_page(self, *args: Any, **kwargs: Any) -> Any:
        page = self._context.new_page(*args, **kwargs)
        if self._listing_page_created:
            return page
        self._listing_page_created = True
        return _RecoveringListingPage(self._context, page)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


class _ReviewBrowser:
    def __init__(self, browser: Any) -> None:
        self._browser = browser

    def new_context(self, *args: Any, **kwargs: Any) -> _ReviewContext:
        return _ReviewContext(self._browser.new_context(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)


def launch_chromium(playwright: Any) -> _ReviewBrowser:
    return _ReviewBrowser(_BASE_LAUNCH_CHROMIUM(playwright))


def apply() -> None:
    """Install one-shot Page-crash recovery for Review listing navigation."""

    global _APPLIED, _BASE_LAUNCH_CHROMIUM
    if _APPLIED:
        return
    _BASE_LAUNCH_CHROMIUM = _browser.launch_chromium
    _browser.launch_chromium = launch_chromium
    _APPLIED = True


__all__ = [
    "apply",
    "launch_chromium",
    "_RecoveringListingPage",
    "_ReviewBrowser",
    "_ReviewContext",
    "_is_page_crash",
]
