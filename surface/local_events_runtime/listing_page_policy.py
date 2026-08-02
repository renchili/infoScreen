from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_ARCHIVE_PATH_RE = re.compile(
    r"(?:^|[/_.-])(?:archive|archives|archived|"
    r"past[-_ ]?(?:event|events|exhibition|exhibitions|programme|programmes)|"
    r"previous[-_ ]?(?:event|events|exhibition|exhibitions|programme|programmes))"
    r"(?:$|[/_.-])",
    re.I,
)
_ARCHIVE_LINK_RE = re.compile(
    r"\b(?:archive|archives|archived|past\s+(?:events?|exhibitions?|programmes?)|"
    r"previous\s+(?:events?|exhibitions?|programmes?))\b",
    re.I,
)


def rejection_reason(url: object, link_text: object = "") -> str:
    """Return why a URL cannot be a current Event list page."""

    raw_url = str(url or "").strip()
    raw_link_text = str(link_text or "").strip()
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "invalid_listing_url"

    searchable_path = unquote(parsed.path or "").casefold()
    searchable_query = unquote(parsed.query or "").casefold()
    if _ARCHIVE_PATH_RE.search(searchable_path):
        return "archive_listing_path"
    if _ARCHIVE_PATH_RE.search(searchable_query):
        return "archive_listing_query"
    if _ARCHIVE_LINK_RE.search(raw_link_text):
        return "archive_listing_link_text"
    return ""


def is_current_listing_page(url: object, link_text: object = "") -> bool:
    """Accept only pages that can represent current or upcoming activities."""

    return not rejection_reason(url, link_text)


__all__ = ["is_current_listing_page", "rejection_reason"]
