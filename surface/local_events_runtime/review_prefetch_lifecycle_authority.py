from __future__ import annotations

from typing import Any

from . import review_detail_prefetch_authority as _prefetch

_APPLIED = False

# Prefetch is only a navigation optimisation. It must follow the cards already admitted
# by CARD_JS, not independently broaden membership by scanning every source selector a
# second time. The selector fallback remains for compatibility when no card marker is
# available, but marked Review cards are always authoritative.
ADMITTED_DETAIL_URLS_JS = r"""
(args) => {
  const marked = Array.from(document.querySelectorAll("[data-infoscreen-card-id]"));
  const roots = [];
  const addRoot = element => {
    if (element && !roots.includes(element)) roots.push(element);
  };

  if (marked.length) {
    marked.forEach(addRoot);
  } else {
    for (const selector of args.selectors || []) {
      try {
        for (const element of document.querySelectorAll(selector)) addRoot(element);
      } catch (error) {}
    }
  }

  const urls = [];
  const addUrl = value => {
    try {
      const url = new URL(String(value || ""), location.href);
      url.hash = "";
      if (url.href && !urls.includes(url.href)) urls.push(url.href);
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


def take_prefetched(context: Any, requested_url: str):
    """Consume one prefetched page and release all state owned by that entry."""

    state = _prefetch._state(context)
    key = _prefetch._canonical_url(requested_url)
    entry = state.entries.pop(key, None)
    state.seen.discard(key)
    if entry is not None:
        state.page_ids.discard(id(entry.page))
    return entry


def apply() -> None:
    """Keep Review prefetch bounded to admitted cards and live page entries."""

    global _APPLIED
    if _APPLIED:
        return
    _prefetch.PREFETCH_DETAIL_URLS_JS = ADMITTED_DETAIL_URLS_JS
    _prefetch._take_prefetched = take_prefetched
    _APPLIED = True


__all__ = ["ADMITTED_DETAIL_URLS_JS", "apply", "take_prefetched"]
