from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from . import browser as _browser
from . import extract as _extract

_APPLIED = False
_BASE_COLLECT_SOURCE = None
_BASE_LAUNCH_CHROMIUM = None
_ACTIVE_DEADLINE: ContextVar[float | None] = ContextVar(
    "local_events_collection_deadline",
    default=None,
)

DEFAULT_OPERATION_TIMEOUT_MS = 30_000
CLEANUP_RESERVE_SECONDS = 30.0


class CollectionDeadlineExceeded(TimeoutError):
    """Raised when a browser operation starts after its collection budget."""


def active_deadline() -> float | None:
    return _ACTIVE_DEADLINE.get()


def remaining_seconds() -> float | None:
    deadline = active_deadline()
    if deadline is None:
        return None
    return deadline - time.time() - CLEANUP_RESERVE_SECONDS


def bounded_timeout_ms(requested: object = None) -> int:
    """Clamp one Playwright wait to the active source/global deadline.

    The collector uses wall-clock deadlines. Playwright operations previously kept
    their full per-navigation timeout even after that deadline had elapsed, so the
    ThreadPoolExecutor could not actually stop running source tasks. Reserving a
    small cleanup window lets pages and Chromium close before systemd's outer limit.
    """

    try:
        requested_ms = int(requested) if requested is not None else DEFAULT_OPERATION_TIMEOUT_MS
    except (TypeError, ValueError):
        requested_ms = DEFAULT_OPERATION_TIMEOUT_MS
    requested_ms = max(1, requested_ms)

    remaining = remaining_seconds()
    if remaining is None:
        return requested_ms
    remaining_ms = int(remaining * 1000)
    if remaining_ms <= 0:
        raise CollectionDeadlineExceeded("local_event_collection_deadline_exceeded")
    return max(1, min(requested_ms, remaining_ms))


def ensure_time_remaining() -> None:
    bounded_timeout_ms(1)


class _DeadlinePage:
    def __init__(self, page: Any) -> None:
        self._page = page

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = bounded_timeout_ms(kwargs.get("timeout"))
        return self._page.goto(*args, **kwargs)

    def wait_for_timeout(self, milliseconds: object) -> Any:
        return self._page.wait_for_timeout(bounded_timeout_ms(milliseconds))

    def wait_for_load_state(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = bounded_timeout_ms(kwargs.get("timeout"))
        return self._page.wait_for_load_state(*args, **kwargs)

    def screenshot(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = bounded_timeout_ms(kwargs.get("timeout"))
        return self._page.screenshot(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)


class _DeadlineBrowser:
    def __init__(self, browser: Any) -> None:
        self._browser = browser

    def new_page(self, *args: Any, **kwargs: Any) -> _DeadlinePage:
        ensure_time_remaining()
        return _DeadlinePage(self._browser.new_page(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)


def collect_source(
    source: dict[str, Any],
    debug_dir: Any,
    deadline: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expose the source deadline to every Chromium operation in that worker."""

    token = _ACTIVE_DEADLINE.set(float(deadline))
    try:
        return _BASE_COLLECT_SOURCE(source, debug_dir, deadline)
    finally:
        _ACTIVE_DEADLINE.reset(token)


def launch_chromium(playwright: Any) -> _DeadlineBrowser:
    """Wrap the final HTTP/1 Chromium launcher with deadline-aware pages."""

    ensure_time_remaining()
    return _DeadlineBrowser(_BASE_LAUNCH_CHROMIUM(playwright))


def apply() -> None:
    """Install a real wall-clock boundary around source browser work."""

    global _APPLIED, _BASE_COLLECT_SOURCE, _BASE_LAUNCH_CHROMIUM
    if _APPLIED:
        return

    _BASE_COLLECT_SOURCE = _extract.collect_source
    _BASE_LAUNCH_CHROMIUM = _browser.launch_chromium
    _extract.collect_source = collect_source
    _browser.launch_chromium = launch_chromium
    _APPLIED = True


__all__ = [
    "CLEANUP_RESERVE_SECONDS",
    "CollectionDeadlineExceeded",
    "active_deadline",
    "apply",
    "bounded_timeout_ms",
    "collect_source",
    "ensure_time_remaining",
    "launch_chromium",
    "remaining_seconds",
]
