from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from . import browser as _browser
from . import extract as _extract

DOM_ONLY_SOURCES = {
    "gardensbythebay",
    "nationalgallery",
    "nationalmuseum",
    "sciencecentre",
    "sentosa",
}
NATIONAL_MUSEUM_NON_EVENT_PATHS = {
    "/whats-on/plan-your-itinerary",
}

_applied = False
_base_render_listing_cards = None
_base_event_from_card = None


def _patch_card_anchor_discovery() -> None:
    old = 'for (const a of Array.from(el.querySelectorAll("a[href]"))) {'
    new = (
        'for (const a of ['
        '...(el.matches && el.matches("a[href]") ? [el] : []), '
        '...Array.from(el.querySelectorAll("a[href]"))]) {'
    )
    if old in _browser.CARD_JS:
        _browser.CARD_JS = _browser.CARD_JS.replace(old, new)


def _render_listing_cards(source: dict, url: str, debug_dir, max_cards: int = 60):
    source_id = _extract.clean(source.get("id") or "").lower()
    if source_id in DOM_ONLY_SOURCES:
        return _browser.render_listing_cards(source, url, debug_dir, max_cards=max_cards)
    return _base_render_listing_cards(source, url, debug_dir, max_cards=max_cards)


def _event_end_date(event: dict) -> date | None:
    raw = _extract.clean(event.get("end_date") or event.get("start_date") or "")
    if raw:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    dates = _extract.label_dates(_extract.clean(event.get("when") or ""))
    return max(dates) if dates else None


def _event_from_card(source: dict, card: dict):
    event, reason = _base_event_from_card(source, card)
    if not event:
        return event, reason

    source_id = _extract.clean(source.get("id") or "").lower()
    path = urlparse(_extract.clean(event.get("url") or card.get("url") or "")).path.rstrip("/").lower()

    if source_id == "nationalmuseum" and path in NATIONAL_MUSEUM_NON_EVENT_PATHS:
        return None, "non_event_itinerary_page"

    end_date = _event_end_date(event)
    if end_date and end_date < _extract.TODAY:
        return None, "past_date"

    if source_id == "gardensbythebay":
        url = _extract.clean(event.get("url") or "")
        if "#nhb" in url or not path.startswith("/en/things-to-do/calendar-of-events/"):
            return None, "gardens_noncanonical_event_url"

    return event, reason


def apply() -> None:
    global _applied, _base_render_listing_cards, _base_event_from_card
    if _applied:
        return

    _patch_card_anchor_discovery()
    _base_render_listing_cards = _extract.render_listing_cards
    _base_event_from_card = _extract.event_from_card
    _extract.render_listing_cards = _render_listing_cards
    _extract.event_from_card = _event_from_card
    _applied = True


__all__ = ["apply", "DOM_ONLY_SOURCES", "NATIONAL_MUSEUM_NON_EVENT_PATHS"]
