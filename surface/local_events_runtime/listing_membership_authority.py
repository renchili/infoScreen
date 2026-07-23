from __future__ import annotations

import sys
from typing import Any

from . import extract as _extract
from . import source_overrides as _source_overrides

_APPLIED = False


def _explicit_venue(card: dict[str, Any]) -> str:
    """Return a venue read from detail evidence rather than the source fallback."""

    evidence = card.get("detail_evidence")
    if not isinstance(evidence, dict):
        return ""
    for value in evidence.get("venue_candidates") or []:
        venue = _extract.clean(value)
        if venue:
            return venue
    return ""


def _detail_state(
    card: dict[str, Any],
    when: str,
    explicit_venue: str,
) -> tuple[str, str]:
    """Describe missing enrichment fields without revoking list membership."""

    missing: list[str] = []
    if not _extract.clean(when):
        missing.append("date")
    if not _extract.clean(explicit_venue):
        missing.append("venue")

    enrich_error = _extract.clean(card.get("detail_enrich_error"))
    if enrich_error:
        return "incomplete", f"detail_enrichment_failed:{enrich_error}"[:500]
    if not missing:
        return "collected", ""
    return "incomplete", f"detail_{'_and_'.join(missing)}_not_found"


def dom_event(
    source: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any] | None:
    """Build one official-list activity even when detail fields are incomplete.

    The configured or operator-confirmed Event List proves membership. Date, venue,
    and summary are enrichment fields. Their absence must remain visible as an
    incomplete activity rather than reducing source coverage.
    """

    title = _extract.pick_title(card)
    if not title:
        return None

    when, when_line = _extract.pick_when(card)
    where = _extract.pick_venue(source, card, when, when_line)
    summary = _extract.pick_summary(card, title, when, where)
    dates = _extract.label_dates(when)
    explicit_venue = _explicit_venue(card)
    detail_status, detail_error = _detail_state(card, when, explicit_venue)

    return {
        "title": title,
        "when": _extract.clean(when),
        "where": _extract.clean(where)
        or _extract.clean(source.get("default_venue") or source.get("name")),
        "host": source.get("name") or "Official source",
        "source_name": source.get("name") or "Official source",
        "url": _extract.clean(card.get("url")),
        "summary": _extract.clean(summary),
        "start_date": _extract.best_start_date(when) if dates else "",
        "end_date": max(dates).isoformat() if len(dates) >= 2 else "",
        "kind": "event",
        "source_type": (
            "official_listing_card"
            if detail_status == "collected"
            else "official_listing_card_detail_incomplete"
        ),
        "detail_available": bool(card.get("detail_enriched")),
        "detail_status": detail_status,
        "detail_error": detail_error,
        "debug_screenshot": card.get("screenshot") or "",
        "debug_detail_url_count": card.get("detail_url_count", 0),
    }


def event_from_card(
    source: dict[str, Any],
    card: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Apply membership first and expiration only when a real date was parsed."""

    if card.get("listing_evidence") != _source_overrides.LISTING_EVIDENCE:
        return None, "missing_official_listing_evidence"
    url = _source_overrides._candidate_url(source, card)
    if not url:
        return None, "official_detail_url_not_found"

    event = _source_overrides._structured_event(source, card) or dom_event(source, card)
    if not event:
        return None, "listing_card_title_not_found"
    event["url"] = url

    # Unknown dates are incomplete, not expired. Only concrete parsed dates can
    # prove that an official listed activity has already ended.
    dates = _extract.label_dates(_extract.clean(event.get("when")))
    end = _source_overrides._event_end(event)
    if (end or (max(dates) if dates else None)) and (
        end or max(dates)
    ) < _extract.TODAY:
        return None, "past_date"

    evidence = (
        card.get("detail_evidence")
        if isinstance(card.get("detail_evidence"), dict)
        else {}
    )
    detail_title = _source_overrides._valid_title(evidence.get("title"))
    if detail_title:
        event["title"] = detail_title
    event["where"] = _source_overrides._venue(source, event, evidence)
    event["candidate_policy"] = "official-listing-authority-v1"
    event["listing_url"] = card.get("listing_url") or ""
    event["listing_card_id"] = card.get("listing_card_id") or ""

    package = sys.modules.get(__package__)
    repair = getattr(package, "_apply_gardens_card_fields", None)
    if callable(repair):
        event = repair(source, card, event)
    return event, "accepted"


def apply() -> None:
    """Install official-list membership authority in the formal collector."""

    global _APPLIED
    if _APPLIED:
        return

    _source_overrides.apply()
    _source_overrides._dom_event = dom_event
    _source_overrides._event = event_from_card
    _extract.event_from_card = event_from_card

    package = sys.modules.get(__package__)
    if package is not None:
        package.event_from_card = event_from_card
    _APPLIED = True


__all__ = ["apply", "dom_event", "event_from_card"]
