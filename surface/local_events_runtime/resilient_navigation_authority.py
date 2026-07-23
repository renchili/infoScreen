from __future__ import annotations

import time
from typing import Any, Callable

_APPLIED = False
_ORIGINAL_GOTO: Callable[..., Any] | None = None

DEFAULT_NAVIGATION_TIMEOUT_MS = 180_000
SOFT_DOMCONTENTLOADED_TIMEOUT_MS = 15_000
SOFT_NETWORK_IDLE_TIMEOUT_MS = 5_000

READABLE_DOCUMENT_JS = r"""
() => {
  const body = document.body;
  if (!body) return false;
  const root = document.querySelector("main") || document.querySelector("article") || body;
  const text = String(root.innerText || root.textContent || "").replace(/\s+/g, " ").trim();
  const usefulNodes = root.querySelectorAll(
    "a[href], article, section, [class*='card' i], [class*='event' i], [class*='listing' i]"
  ).length;
  return text.length >= 20 || usefulNodes > 0;
}
"""


def _timeout_ms(raw: object) -> int:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_NAVIGATION_TIMEOUT_MS
    return value if value > 0 else DEFAULT_NAVIGATION_TIMEOUT_MS


def _remaining_ms(started: float, total_ms: int) -> int:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return max(1, total_ms - elapsed_ms)


def _document_readable(page: Any) -> bool:
    try:
        return bool(page.evaluate(READABLE_DOCUMENT_JS))
    except Exception:
        return False


def _goto_with_readable_document(
    page: Any,
    url: str,
    *args: Any,
    **kwargs: Any,
):
    """Navigate once and accept a readable DOM even if lifecycle events never settle.

    Several official Event sites keep analytics, consent, personalisation, or API
    requests active for a long time. Playwright can therefore time out waiting for
    ``networkidle`` or even ``domcontentloaded`` after the page's actual content is
    already available. Repeating ``goto`` starts the same slow navigation again and
    loses the usable document.

    This wrapper changes only callers that requested ``networkidle`` or
    ``domcontentloaded``. It waits for the response to commit, gives the normal DOM
    event a bounded opportunity, then treats a usable rendered document as success.
    A page with no readable DOM still raises the original navigation error.
    """

    if _ORIGINAL_GOTO is None:
        raise RuntimeError("resilient_navigation_not_applied")

    requested_state = str(kwargs.get("wait_until") or "").lower()
    if requested_state not in {"networkidle", "domcontentloaded"}:
        return _ORIGINAL_GOTO(page, url, *args, **kwargs)

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    total_timeout_ms = _timeout_ms(kwargs.get("timeout"))
    started = time.monotonic()
    commit_kwargs = dict(kwargs)
    commit_kwargs["wait_until"] = "commit"

    try:
        response = _ORIGINAL_GOTO(page, url, *args, **commit_kwargs)
    except PlaywrightError:
        # Redirect races and lifecycle timeouts can arrive immediately after the
        # browser has already committed and rendered the intended document.
        if _document_readable(page):
            return None
        raise

    dom_wait_ms = min(
        SOFT_DOMCONTENTLOADED_TIMEOUT_MS,
        _remaining_ms(started, total_timeout_ms),
    )
    try:
        page.wait_for_load_state("domcontentloaded", timeout=dom_wait_ms)
    except PlaywrightError:
        # DOMContentLoaded is advisory here. Readability remains the hard condition.
        pass

    readable_wait_ms = _remaining_ms(started, total_timeout_ms)
    try:
        page.wait_for_function(READABLE_DOCUMENT_JS, timeout=readable_wait_ms)
    except PlaywrightError:
        if not _document_readable(page):
            raise

    # Keep a small best-effort settling window for client-rendered cards, but never
    # require networkidle. Callers still perform their configured render wait and
    # dynamic-listing expansion after this function returns.
    if requested_state == "networkidle":
        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=min(
                    SOFT_NETWORK_IDLE_TIMEOUT_MS,
                    _remaining_ms(started, total_timeout_ms),
                ),
            )
        except (PlaywrightTimeoutError, PlaywrightError):
            pass

    return response


def apply() -> None:
    """Patch Playwright Page.goto for every Local Events collection path."""

    global _APPLIED, _ORIGINAL_GOTO
    if _APPLIED:
        return

    from playwright.sync_api import Page

    _ORIGINAL_GOTO = Page.goto
    Page.goto = _goto_with_readable_document
    _APPLIED = True


__all__ = [
    "DEFAULT_NAVIGATION_TIMEOUT_MS",
    "READABLE_DOCUMENT_JS",
    "apply",
]
