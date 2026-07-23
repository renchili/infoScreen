from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import extract as _extract
from . import official_feeds as _official_feeds
from . import source_overrides as _source_overrides

_APPLIED = False
_MEDIA_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf)$", re.I)
_SYNTHETIC_FRAGMENT_RE = re.compile(r"^(?:nhb|nhb-json|structured)-", re.I)


def listing_detail_url(listing_url: object, value: object) -> str:
    """Return a safe detail URL explicitly referenced by an official Event list.

    The trust boundary is the configured or operator-confirmed listing page. Once an
    activity link is rendered inside an admitted card on that page, its destination
    does not need to share the listing host. This supports official associated sites,
    ticketing sites, and independently hosted Event pages without admitting arbitrary
    URLs from outside the reviewed listing.
    """

    listing_raw = _extract.clean(listing_url)
    raw = _extract.clean(value)
    if not listing_raw or not raw:
        return ""
    try:
        absolute = urljoin(listing_raw, raw)
        parsed = urlsplit(absolute)
        listing = urlsplit(listing_raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    if parsed.fragment and _SYNTHETIC_FRAGMENT_RE.match(parsed.fragment):
        return ""
    path = parsed.path or "/"
    if _MEDIA_RE.search(path):
        return ""

    canonical = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/") or "/", parsed.query, "")
    )
    listing_canonical = urlunsplit(
        (
            listing.scheme.lower(),
            listing.netloc.lower(),
            (listing.path or "/").rstrip("/") or "/",
            listing.query,
            "",
        )
    )
    if canonical == listing_canonical:
        return ""
    return canonical


def canonical_detail_url(source: dict[str, Any], value: object) -> bool:
    """Validate a detail URL against the source's official listing inventory.

    This deliberately does not compare the target host with ``allowed_domains``.
    ``allowed_domains`` remains authoritative for listing-page provenance only.
    """

    return any(
        listing_detail_url(listing_url, value)
        for listing_url in source.get("listing_urls") or []
    )


def _candidate_url(source: dict[str, Any], card: dict[str, Any]) -> str:
    listing_url = _extract.clean(
        card.get("listing_url")
        or card.get("page_url")
        or next(iter(source.get("listing_urls") or []), "")
    )
    for value in [card.get("url"), *(card.get("detail_urls") or [])]:
        candidate = listing_detail_url(listing_url, value)
        if candidate:
            return candidate
    return ""


def _listing_card(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    """Admit an isolated card because it came from the reviewed official list.

    Date, venue, and summary are enrichment fields. They are not membership gates.
    A configured card selector is itself sufficient structural evidence. Generic
    extraction still requires a usable card title to avoid admitting page chrome.
    """

    mode = _extract.clean(card.get("extraction_mode"))
    if mode not in {"detail_link", "nhb_dom_card"}:
        return None
    canonical = ""
    for value in [card.get("url"), *(card.get("detail_urls") or [])]:
        canonical = listing_detail_url(listing_url, value)
        if canonical:
            break
    if not canonical:
        return None
    if not source.get("card_selectors") and not _official_feeds.card_title(card):
        return None

    admitted = dict(card)
    admitted.update(
        url=canonical,
        page_url=canonical,
        detail_urls=[canonical],
        detail_url_count=1,
        listing_evidence=_source_overrides.LISTING_EVIDENCE,
        listing_url=listing_url,
        listing_card_id=_extract.clean(card.get("id")),
        listing_extraction_mode=mode,
    )
    return admitted


def apply() -> None:
    """Install listing-provenance authority in the formal and Review collectors."""

    global _APPLIED
    if _APPLIED:
        return
    _source_overrides.canonical_detail_url = canonical_detail_url
    _source_overrides._candidate_url = _candidate_url
    _source_overrides._listing_card = _listing_card
    _APPLIED = True


__all__ = [
    "apply",
    "canonical_detail_url",
    "listing_detail_url",
    "_candidate_url",
    "_listing_card",
]
