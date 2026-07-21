from __future__ import annotations

from typing import Any

from . import browser as _browser
from . import extract as _extract
from . import official_feeds as _official_feeds
from . import source_overrides

_applied = False


def _listing_card_without_listing_date(
    source: dict[str, Any],
    card: dict[str, Any],
    listing_url: str,
) -> dict[str, Any] | None:
    """Admit an isolated official list card before reading its detail-page date.

    A listing page proves activity membership through one official detail link and
    a usable title. The listing itself is not required to repeat date or venue
    fields; those fields remain mandatory only after detail-page enrichment.
    """

    mode = _extract.clean(card.get("extraction_mode"))
    if mode not in {"detail_link", "nhb_dom_card"}:
        return None
    if int(card.get("detail_url_count") or 0) != 1:
        return None
    if not _official_feeds.card_title(card):
        return None

    canonical = source_overrides._candidate_url(source, card)
    if not canonical:
        return None

    admitted = dict(card)
    admitted.update(
        url=canonical,
        page_url=canonical,
        listing_evidence=source_overrides.LISTING_EVIDENCE,
        listing_url=listing_url,
        listing_card_id=_extract.clean(card.get("id")),
        listing_extraction_mode=mode,
    )
    return admitted


def apply() -> None:
    """Apply detail-page date authority after the listing-authority patch."""

    global _applied
    if _applied:
        return

    source_overrides.apply()

    # source_overrides previously discarded a rendered list card before opening
    # its official detail page when the list card did not repeat a date.
    _browser.CARD_JS = _browser.CARD_JS.replace(
        '    if (!hasDateText(textLines(card).join(" "))) continue;\n',
        "",
    )
    source_overrides._listing_card = _listing_card_without_listing_date
    _applied = True


__all__ = ["apply"]
