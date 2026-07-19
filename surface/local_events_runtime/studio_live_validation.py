from __future__ import annotations

from datetime import date
from typing import Any

from .studio_evaluate import rule_fingerprint, validate_detail_url
from .studio_live_runtime import (
    card_is_excluded,
    finalize_values,
    listing_values,
    required_mapping_errors,
    verify_detail_page,
)
from .studio_rules import LocalEventStudioRule


def validate_current_listing(
    page: Any,
    page_factory: Any,
    rule: LocalEventStudioRule,
    source: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate the operator-prepared listing against several real detail pages."""

    fatal = required_mapping_errors(rule)
    cards = []
    if rule.card is not None:
        cards = [
            card
            for card in page.locator(rule.card.selector).all()
            if card.is_visible()
        ]
        if not cards:
            fatal.append("card_selector_matched_zero_visible_elements")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    if not fatal and rule.card is not None and rule.fields.url is not None:
        for index, card in enumerate(cards[:12]):
            if len(accepted) >= 3:
                break
            card_id = f"live-{index}"
            try:
                if card_is_excluded(card, rule.card.exclude_selectors):
                    continue
                values = listing_values(card, rule)
                public_url, reason = validate_detail_url(
                    values.get("url", ""),
                    rule.listing_url,
                    source,
                )
                if reason:
                    raise RuntimeError(reason)
                if public_url in seen_urls:
                    raise RuntimeError("duplicate_detail_url")
                seen_urls.add(public_url)

                public_url, values, detail_info = verify_detail_page(
                    page_factory,
                    source,
                    rule,
                    public_url,
                    values,
                )
                values, dates = finalize_values(
                    values,
                    rule,
                    source,
                    today=today,
                )
                accepted.append(
                    {
                        "card_id": card_id,
                        "event": {
                            "title": values["title"],
                            "when": values["when"],
                            "where": values["where"],
                            "url": public_url,
                            "summary": values.get("summary", ""),
                            "image": values.get("image", ""),
                            "start_date": min(dates).isoformat(),
                            "end_date": max(dates).isoformat(),
                            "source_id": rule.source_id,
                            "source_name": source.get("name") or rule.source_id,
                            "listing_url": rule.listing_url,
                        },
                        "detail_page_pending": False,
                        "detail_page": detail_info,
                    }
                )
            except Exception as exc:
                rejected.append(
                    {
                        "card_id": card_id,
                        "reason": str(exc) or type(exc).__name__,
                    }
                )

    if len(accepted) < 2:
        fatal.append("live_validation_requires_two_confirmed_detail_pages")
    fatal = list(dict.fromkeys(fatal))
    return {
        "schema_version": 1,
        "rule_fingerprint": rule_fingerprint(rule),
        "source_id": rule.source_id,
        "listing_url": rule.listing_url,
        "card_selector": rule.card.selector if rule.card else None,
        "matched_card_count": len(cards),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "publishable": not fatal and len(accepted) >= 2,
        "fatal_errors": fatal,
        "warnings": [],
        "accepted": accepted,
        "rejected": rejected,
        "validation_mode": "operator_live_browser_with_detail_pages",
    }


__all__ = ["validate_current_listing"]
