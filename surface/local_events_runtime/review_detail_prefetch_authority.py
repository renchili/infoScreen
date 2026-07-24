from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import event_review as _review
from . import extract as _extract
from . import listing_provenance_authority as _provenance

_APPLIED = False
_BASE_DETAIL_CANDIDATE = None
_MAX_CONTEXT_STATES = 4
_DEFAULT_PREFETCH_LIMIT = 12
_MAX_PREFETCH_LIMIT = 24

PREFETCH_DETAIL_URLS_JS = r"""
(args) => {
  const roots = [];
  const addRoot = element => {
    if (element && !roots.includes(element)) roots.push(element);
  };
  for (const element of document.querySelectorAll("[data-infoscreen-card-id]")) {
    addRoot(element);
  }
  for (const selector of args.selectors || []) {
    try {
      for (const element of document.querySelectorAll(selector)) addRoot(element);
    } catch (error) {}
  }

  const urls = [];
  const addUrl = value => {
    try {
      const url = new URL(String(value || ""), location.href).href;
      if (url && !urls.includes(url)) urls.push(url);
    } catch (error) {}
  };
  for (const root of roots) {
    if (root.matches && root.matches("a[href]")) addUrl(root.getAttribute("href"));
    for (const anchor of root.querySelectorAll("a[href]")) {
      addUrl(anchor.getAttribute("href"));
    }
  }
  return urls;
}
"""

START_DETAIL_NAVIGATION_JS = r"""
(url) => {
  setTimeout(() => {
    window.location.assign(url);
  }, 0);
  return true;
}
"""

WAIT_FOR_NAVIGATION_JS = r"""
() => location.href !== "about:blank"
"""


@dataclass
class _PrefetchedDetail:
    page: Any
    requested_url: str
    status: dict[str, int | None] = field(default_factory=lambda: {"value": None})


@dataclass
class _PrefetchState:
    entries: dict[str, _PrefetchedDetail] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)
    page_ids: set[int] = field(default_factory=set)


_STATES: "OrderedDict[int, _PrefetchState]" = OrderedDict()


def _canonical_url(value: object) -> str:
    text = _extract.clean(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            (parsed.path or "/").rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def _prefetch_limit() -> int:
    try:
        configured = int(
            os.environ.get(
                "INFOSCREEN_REVIEW_DETAIL_PREFETCH",
                str(_DEFAULT_PREFETCH_LIMIT),
            )
        )
    except ValueError:
        configured = _DEFAULT_PREFETCH_LIMIT
    return max(1, min(_MAX_PREFETCH_LIMIT, configured))


def _state(context: Any) -> _PrefetchState:
    key = id(context)
    state = _STATES.get(key)
    if state is not None:
        _STATES.move_to_end(key)
        return state

    state = _PrefetchState()
    _STATES[key] = state
    while len(_STATES) > _MAX_CONTEXT_STATES:
        _, stale = _STATES.popitem(last=False)
        for entry in stale.entries.values():
            try:
                if not entry.page.is_closed():
                    entry.page.close()
            except Exception:
                pass
    return state


def _listing_page(context: Any, state: _PrefetchState, listing_url: str) -> Any | None:
    expected = _canonical_url(listing_url)
    candidates = [
        page
        for page in context.pages
        if id(page) not in state.page_ids
        and not page.is_closed()
        and str(page.url or "") != "about:blank"
    ]
    for page in candidates:
        if _canonical_url(page.url) == expected:
            return page
    return candidates[0] if candidates else None


def _capture_main_status(entry: _PrefetchedDetail) -> None:
    page = entry.page

    def on_response(response: Any) -> None:
        try:
            if (
                response.request.resource_type == "document"
                and response.frame == page.main_frame
            ):
                entry.status["value"] = int(response.status)
        except Exception:
            return

    page.on("response", on_response)


def _start_prefetch(context: Any, state: _PrefetchState, requested_url: str) -> None:
    key = _canonical_url(requested_url)
    if not key or key in state.seen or len(state.entries) >= _prefetch_limit():
        return

    page = context.new_page()
    entry = _PrefetchedDetail(page=page, requested_url=requested_url)
    state.entries[key] = entry
    state.seen.add(key)
    state.page_ids.add(id(page))
    _capture_main_status(entry)
    try:
        page.evaluate(START_DETAIL_NAVIGATION_JS, requested_url)
    except Exception:
        state.entries.pop(key, None)
        state.seen.discard(key)
        state.page_ids.discard(id(page))
        try:
            page.close()
        except Exception:
            pass


def _prefetch_listing_details(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    requested_url: str,
) -> None:
    """Start all visible detail navigations before waiting for the first one."""

    state = _state(context)
    raw_urls = [requested_url]
    listing_page = _listing_page(context, state, listing_url)
    if listing_page is not None:
        try:
            observed = listing_page.evaluate(
                PREFETCH_DETAIL_URLS_JS,
                {"selectors": source.get("card_selectors") or []},
            )
        except Exception:
            observed = []
        if isinstance(observed, list):
            raw_urls.extend(str(value or "") for value in observed)

    for raw_url in raw_urls:
        canonical = _provenance.listing_detail_url(listing_url, raw_url)
        if canonical:
            _start_prefetch(context, state, canonical)


def _take_prefetched(context: Any, requested_url: str) -> _PrefetchedDetail | None:
    return _state(context).entries.pop(_canonical_url(requested_url), None)


class _PrefetchedPageProxy:
    def __init__(self, entry: _PrefetchedDetail):
        self._entry = entry
        self._page = entry.page

    def goto(self, url: str, *, wait_until: str, timeout: int):
        expected = _canonical_url(self._entry.requested_url)
        if _canonical_url(url) != expected:
            raise ValueError("prefetched_detail_url_mismatch")
        self._page.wait_for_function(WAIT_FOR_NAVIGATION_JS, timeout=timeout)
        status = self._entry.status.get("value")
        return SimpleNamespace(status=status) if status is not None else None

    def __getattr__(self, name: str):
        return getattr(self._page, name)


class _PrefetchedContextProxy:
    def __init__(self, context: Any, entry: _PrefetchedDetail):
        self._context = context
        self._entry = entry
        self._used = False

    def new_page(self):
        if self._used:
            return self._context.new_page()
        self._used = True
        return _PrefetchedPageProxy(self._entry)

    def __getattr__(self, name: str):
        return getattr(self._context, name)


def _detail_candidate(
    context: Any,
    source: dict[str, Any],
    listing_url: str,
    raw_url: str,
    card: dict[str, Any],
) -> dict[str, str]:
    requested_url = _provenance.listing_detail_url(listing_url, raw_url)
    if not requested_url or "#nhb-" in raw_url or "#nhb-json-" in raw_url:
        return _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )

    _prefetch_listing_details(
        context,
        source,
        listing_url,
        requested_url,
    )
    entry = _take_prefetched(context, requested_url)
    if entry is None:
        return _BASE_DETAIL_CANDIDATE(
            context,
            source,
            listing_url,
            raw_url,
            card,
        )

    return _BASE_DETAIL_CANDIDATE(
        _PrefetchedContextProxy(context, entry),
        source,
        listing_url,
        raw_url,
        card,
    )


def apply() -> None:
    """Prefetch Review detail tabs while preserving the blocking Preview contract."""

    global _APPLIED, _BASE_DETAIL_CANDIDATE
    if _APPLIED:
        return
    _BASE_DETAIL_CANDIDATE = _review._detail_candidate
    _review._detail_candidate = _detail_candidate
    _APPLIED = True


__all__ = [
    "PREFETCH_DETAIL_URLS_JS",
    "START_DETAIL_NAVIGATION_JS",
    "WAIT_FOR_NAVIGATION_JS",
    "apply",
    "_detail_candidate",
    "_prefetch_listing_details",
    "_prefetch_limit",
    "_take_prefetched",
]
