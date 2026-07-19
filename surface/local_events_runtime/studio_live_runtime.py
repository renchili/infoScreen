from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlsplit

from .extract import clean, label_dates
from .studio_actions import execute_browser_actions
from .studio_evaluate import validate_detail_url
from .studio_rules import LocalEventStudioRule

DETAIL_TIMEOUT_MS = 20000


def host_allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def read_value(locator: Any, attribute: str | None) -> str:
    if locator.count() <= 0:
        return ""
    node = locator.first
    if attribute:
        return clean(node.get_attribute(attribute) or "")
    try:
        return clean(node.inner_text(timeout=3000) or "")
    except Exception:
        return clean(node.text_content(timeout=3000) or "")


def goto_official_page(page: Any, url: str, *, timeout_ms: int = DETAIL_TIMEOUT_MS) -> Any:
    try:
        response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    except Exception:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"http_status_{response.status}")
    return response


def required_mapping_errors(rule: LocalEventStudioRule) -> list[str]:
    errors: list[str] = []
    if rule.card is None:
        errors.append("card_selector_missing")
    if rule.fields.url is None:
        errors.append("url_selector_missing")
    for name in ("title", "when", "where"):
        listing_mapping = getattr(rule.fields, name)
        detail_mapping = (
            getattr(rule.detail_page.fields, name)
            if rule.detail_page.enabled
            else None
        )
        if listing_mapping is None and detail_mapping is None:
            errors.append(f"{name}_selector_missing")
    return errors


def card_is_excluded(card: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        if bool(card.evaluate("(element, value) => element.matches(value)", selector)):
            return True
        if card.locator(selector).count() > 0:
            return True
    return False


def listing_values(card: Any, rule: LocalEventStudioRule) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in ("title", "when", "where", "url", "summary", "image"):
        mapping = getattr(rule.fields, name)
        values[name] = (
            read_value(card.locator(mapping.selector), mapping.attribute)
            if mapping is not None
            else ""
        )
    return values


def _detail_values(page: Any, rule: LocalEventStudioRule) -> dict[str, str]:
    values: dict[str, str] = {}
    if not rule.detail_page.enabled:
        return values
    for name in ("title", "when", "where", "summary", "image"):
        mapping = getattr(rule.detail_page.fields, name)
        if mapping is not None:
            values[name] = read_value(
                page.locator(mapping.selector),
                mapping.attribute,
            )
    return values


def verify_detail_page(
    page_factory: Any,
    source: dict[str, Any],
    rule: LocalEventStudioRule,
    public_url: str,
    values: dict[str, str],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Open one admitted URL and return its verified final URL and mapped values."""

    detail = page_factory.new_page(
        viewport={"width": 1440, "height": 1000},
        device_scale_factor=1,
    )
    try:
        goto_official_page(detail, public_url)
        if not host_allowed(str(detail.url), source):
            raise RuntimeError("detail_redirected_outside_allowed_domains")
        final_url, reason = validate_detail_url(
            str(detail.url),
            rule.listing_url,
            source,
        )
        if reason:
            raise RuntimeError(reason)

        action_diagnostics = execute_browser_actions(detail, rule.detail_actions)
        readable = read_value(detail.locator("main, article, body"), None)
        if not readable and not clean(detail.title() or ""):
            raise RuntimeError("detail_page_has_no_readable_content")

        merged = dict(values)
        for name, value in _detail_values(detail, rule).items():
            if value:
                merged[name] = value
        merged["url"] = final_url
        return final_url, merged, {
            "ok": True,
            "url": final_url,
            "page_title": detail.title(),
            "actions": action_diagnostics,
        }
    finally:
        detail.close()


def finalize_values(
    values: dict[str, str],
    rule: LocalEventStudioRule,
    source: dict[str, Any],
    *,
    today: date | None = None,
) -> tuple[dict[str, str], list[date]]:
    """Apply explicit venue fallback and mandatory final value/date checks."""

    output = dict(values)
    if not output.get("where"):
        listing_where = rule.fields.where
        detail_where = (
            rule.detail_page.fields.where
            if rule.detail_page.enabled
            else None
        )
        allow_default = bool(
            (listing_where and listing_where.allow_source_default)
            or (detail_where and detail_where.allow_source_default)
        )
        if allow_default:
            output["where"] = clean(
                source.get("default_venue")
                or source.get("name")
                or ""
            )

    missing = [
        f"{name}_missing_after_detail"
        for name in ("title", "when", "where")
        if not output.get(name)
    ]
    dates = label_dates(output.get("when", ""))
    if not dates:
        missing.append("when_not_parseable")
    elif (
        rule.validation.require_current_or_future_date
        and max(dates) < (today or date.today())
    ):
        missing.append("event_expired")
    if missing:
        raise RuntimeError(missing[0])
    return output, dates


__all__ = [
    "card_is_excluded",
    "finalize_values",
    "goto_official_page",
    "host_allowed",
    "listing_values",
    "read_value",
    "required_mapping_errors",
    "verify_detail_page",
]
