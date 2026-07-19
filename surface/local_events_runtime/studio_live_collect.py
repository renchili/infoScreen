from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from .browser import (
    CLICK_NEXT_PAGE_JS,
    DOM_TIMEOUT_MS,
    LOAD_MORE_ROUNDS,
    LOAD_WAIT_MS,
    MAX_LISTING_PAGES,
    NAV_TIMEOUT_MS,
    NEXT_WAIT_MS,
    PREPARE_PAGE_JS,
    find_browser_executable,
)
from .extract import clean, label_dates
from .studio_actions import execute_browser_actions
from .studio_collect import (
    _debug_belongs_to_source,
    _event_belongs_to_source,
    _event_listing_url,
    _source_inventory,
    published_rules_by_source,
)
from .studio_evaluate import validate_detail_url
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRule,
)

DETAIL_LIMIT = int(os.environ.get("LOCAL_EVENT_STUDIO_DETAIL_LIMIT", "60"))
DETAIL_TIMEOUT_MS = int(os.environ.get("LOCAL_EVENT_STUDIO_DETAIL_TIMEOUT_MS", "20000"))


def _value(locator: Any, attribute: str | None) -> str:
    if locator.count() <= 0:
        return ""
    node = locator.first
    if attribute:
        return clean(node.get_attribute(attribute) or "")
    try:
        return clean(node.inner_text(timeout=3000) or "")
    except Exception:
        return clean(node.text_content(timeout=3000) or "")


def _allowed(url: str, source: dict[str, Any]) -> bool:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def _excluded(card: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        if bool(card.evaluate("(element, value) => element.matches(value)", selector)):
            return True
        if card.locator(selector).count() > 0:
            return True
    return False


def _listing_values(card: Any, rule: LocalEventStudioRule) -> dict[str, str]:
    output: dict[str, str] = {}
    for name in ("title", "when", "where", "url", "summary", "image"):
        mapping = getattr(rule.fields, name)
        output[name] = (
            _value(card.locator(mapping.selector), mapping.attribute)
            if mapping
            else ""
        )
    return output


def _detail_values(page: Any, rule: LocalEventStudioRule) -> dict[str, str]:
    output: dict[str, str] = {}
    for name in ("title", "when", "where", "summary", "image"):
        mapping = getattr(rule.detail_page.fields, name)
        if mapping:
            output[name] = _value(page.locator(mapping.selector), mapping.attribute)
    return output


def _launch(playwright: Any):
    executable = find_browser_executable()
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    return playwright.chromium.launch(
        headless=True,
        executable_path=executable or None,
        args=args,
    )


def _goto(page: Any, url: str, *, timeout: int) -> Any:
    try:
        response = page.goto(url, wait_until="networkidle", timeout=timeout)
    except Exception:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"http_status_{response.status}")
    return response


def _collect_detail(
    browser: Any,
    source: dict[str, Any],
    rule: LocalEventStudioRule,
    public_url: str,
    values: dict[str, str],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    detail = browser.new_page(
        viewport={"width": 1440, "height": 1000},
        device_scale_factor=1,
    )
    try:
        _goto(detail, public_url, timeout=DETAIL_TIMEOUT_MS)
        if not _allowed(str(detail.url), source):
            raise RuntimeError("detail_redirected_outside_allowed_domains")
        final_url, reason = validate_detail_url(
            str(detail.url),
            rule.listing_url,
            source,
        )
        if reason:
            raise RuntimeError(reason)
        action_diagnostics = execute_browser_actions(detail, rule.detail_actions)
        root_text = _value(detail.locator("main, article, body"), None)
        if not root_text and not clean(detail.title() or ""):
            raise RuntimeError("detail_page_has_no_readable_content")
        if rule.detail_page.enabled:
            for name, value in _detail_values(detail, rule).items():
                if value:
                    values[name] = value
        return final_url, values, {
            "ok": True,
            "url": final_url,
            "page_title": detail.title(),
            "actions": action_diagnostics,
        }
    finally:
        detail.close()


def collect_published_live_source(
    source: dict[str, Any],
    rules: list[LocalEventStudioRule],
    *,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Replay published actions, admit listing cards, then verify every output on its detail page."""

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return [], [
            {
                "source": source.get("name") or rule.source_id,
                "source_id": rule.source_id,
                "adapter": "studio_live_rule",
                "listing_urls": [rule.listing_url],
                "studio_rule_version": rule.version,
                "status": "failed",
                "complete": False,
                "accepted": 0,
                "reason_counts": {"missing_playwright_python_package": 1},
                "detail": str(exc)[:400],
            }
            for rule in rules
        ]

    current_date = today or date.today()
    output: list[dict[str, Any]] = []
    debug_rows: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        try:
            browser = _launch(playwright)
        except Exception as exc:
            return [], [
                {
                    "source": source.get("name") or rule.source_id,
                    "source_id": rule.source_id,
                    "adapter": "studio_live_rule",
                    "listing_urls": [rule.listing_url],
                    "studio_rule_version": rule.version,
                    "status": "failed",
                    "complete": False,
                    "accepted": 0,
                    "reason_counts": {"studio_browser_start_failed": 1},
                    "detail": f"{type(exc).__name__}:{exc}"[:400],
                }
                for rule in rules
            ]

        try:
            for rule in rules:
                debug: dict[str, Any] = {
                    "source": source.get("name") or rule.source_id,
                    "source_id": rule.source_id,
                    "adapter": "studio_live_rule",
                    "listing_urls": [rule.listing_url],
                    "studio_rule_version": rule.version,
                    "status": "complete",
                    "complete": True,
                    "listing_fetched": 0,
                    "cards_found": 0,
                    "accepted": 0,
                    "reason_counts": {},
                    "not_output_preview": [],
                    "listing_actions": [],
                }
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                )
                rule_results: list[dict[str, Any]] = []
                seen_urls: set[str] = set()
                detail_reads = 0
                try:
                    _goto(page, rule.listing_url, timeout=NAV_TIMEOUT_MS)
                    if not _allowed(str(page.url), source):
                        raise RuntimeError("listing_redirected_outside_allowed_domains")
                    page.wait_for_timeout(LOAD_WAIT_MS)
                    debug["listing_actions"] = execute_browser_actions(
                        page,
                        rule.listing_actions,
                    )

                    for page_index in range(MAX_LISTING_PAGES):
                        prepare = page.evaluate(
                            PREPARE_PAGE_JS,
                            {
                                "maxRounds": int(
                                    source.get("load_more_rounds", LOAD_MORE_ROUNDS)
                                )
                            },
                        )
                        debug.setdefault("prepare", []).append(prepare)
                        if not _allowed(str(page.url), source):
                            raise RuntimeError("listing_redirected_outside_allowed_domains")

                        cards = page.locator(rule.card.selector).all() if rule.card else []
                        debug["listing_fetched"] += 1
                        debug["cards_found"] += len(cards)

                        for card_index, card in enumerate(cards):
                            if detail_reads >= DETAIL_LIMIT:
                                debug["reason_counts"]["detail_limit_reached"] = (
                                    debug["reason_counts"].get("detail_limit_reached", 0)
                                    + 1
                                )
                                break
                            card_id = f"{page_index}:{card_index}"
                            try:
                                if _excluded(
                                    card,
                                    rule.card.exclude_selectors if rule.card else [],
                                ):
                                    debug["reason_counts"]["excluded_by_rule"] = (
                                        debug["reason_counts"].get(
                                            "excluded_by_rule",
                                            0,
                                        )
                                        + 1
                                    )
                                    continue

                                values = _listing_values(card, rule)
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

                                detail_reads += 1
                                public_url, values, detail_info = _collect_detail(
                                    browser,
                                    source,
                                    rule,
                                    public_url,
                                    values,
                                )

                                if (
                                    not values.get("where")
                                    and rule.fields.where
                                    and rule.fields.where.allow_source_default
                                ):
                                    values["where"] = clean(
                                        source.get("default_venue")
                                        or source.get("name")
                                        or ""
                                    )

                                missing = [
                                    f"{name}_missing_after_detail"
                                    for name in ("title", "when", "where")
                                    if not values.get(name)
                                ]
                                dates = label_dates(values.get("when", ""))
                                if not dates:
                                    missing.append("when_not_parseable")
                                elif (
                                    rule.validation.require_current_or_future_date
                                    and max(dates) < current_date
                                ):
                                    missing.append("event_expired")
                                if missing:
                                    raise RuntimeError(missing[0])

                                rule_results.append(
                                    {
                                        "title": values["title"],
                                        "when": values["when"],
                                        "where": values["where"],
                                        "url": public_url,
                                        "summary": values.get("summary", ""),
                                        "image": values.get("image", ""),
                                        "start_date": min(dates).isoformat(),
                                        "end_date": max(dates).isoformat(),
                                        "source_id": rule.source_id,
                                        "source_name": source.get("name")
                                        or rule.source_id,
                                        "host": source.get("name") or rule.source_id,
                                        "listing_url": rule.listing_url,
                                        "studio_listing_url": rule.listing_url,
                                        "candidate_policy": "official-listing-authority-v1",
                                        "source_type": "studio_live_rule",
                                        "studio_rule_version": rule.version,
                                        "studio_detail_page": detail_info,
                                    }
                                )
                            except Exception as exc:
                                reason = str(exc) or type(exc).__name__
                                debug["reason_counts"][reason] = (
                                    debug["reason_counts"].get(reason, 0) + 1
                                )
                                if len(debug["not_output_preview"]) < 20:
                                    try:
                                        card_text = clean(
                                            card.inner_text(timeout=2000) or ""
                                        )[:400]
                                    except Exception:
                                        card_text = ""
                                    debug["not_output_preview"].append(
                                        {
                                            "card_id": card_id,
                                            "reason": reason,
                                            "card_text": card_text,
                                        }
                                    )

                        if detail_reads >= DETAIL_LIMIT:
                            break
                        if page_index >= MAX_LISTING_PAGES - 1:
                            break
                        next_result = page.evaluate(
                            CLICK_NEXT_PAGE_JS,
                            {
                                "allowedDomains": source.get("allowed_domains")
                                or [],
                                "pageIndex": page_index,
                            },
                        )
                        if not next_result.get("clicked"):
                            break
                        try:
                            page.wait_for_load_state(
                                "networkidle",
                                timeout=NEXT_WAIT_MS,
                            )
                        except Exception:
                            page.wait_for_timeout(NEXT_WAIT_MS)

                    debug["accepted"] = len(rule_results)
                    debug["accepted_preview"] = [
                        {
                            "title": item["title"],
                            "when": item["when"],
                            "where": item["where"],
                            "url": item["url"],
                        }
                        for item in rule_results[:12]
                    ]
                    if not rule_results:
                        debug["status"] = "failed"
                        debug["complete"] = False
                        debug["error"] = "studio_live_rule_no_accepted_events"
                    output.extend(rule_results)
                except Exception as exc:
                    debug["status"] = "failed"
                    debug["complete"] = False
                    debug["error"] = type(exc).__name__
                    debug["detail"] = str(exc)[:500]
                finally:
                    page.close()
                    debug_rows.append(debug)
        finally:
            browser.close()

    return output, debug_rows


def apply_published_live_rules(
    payload: dict[str, Any],
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
    today: date | None = None,
) -> dict[str, Any]:
    """Replace activated source/listing rows with replayed listing/detail-rule output."""

    result_payload = dict(payload)
    results = [
        dict(item)
        for item in result_payload.get("results") or []
        if isinstance(item, dict)
    ]
    debug_rows = [
        dict(item)
        for item in result_payload.get("debug_by_source") or []
        if isinstance(item, dict)
    ]
    config_path = Path(source_config_path).expanduser().resolve()
    sources = _source_inventory(config_path)
    source_by_id = {
        str(source.get("id") or ""): source
        for source in sources
    }
    rules_by_source = published_rules_by_source(
        root=root,
        source_config_path=config_path,
    )
    if not rules_by_source:
        return result_payload

    live_results: list[dict[str, Any]] = []
    live_debug: list[dict[str, Any]] = []
    activations: list[dict[str, Any]] = []

    for source_id, rules in rules_by_source.items():
        source = source_by_id.get(source_id)
        if source is None:
            continue
        configured = {
            str(value).rstrip("/")
            for value in source.get("listing_urls") or []
        }
        published = {rule.listing_url.rstrip("/") for rule in rules}
        full_source = bool(configured) and configured == published

        if full_source:
            results = [
                item
                for item in results
                if not _event_belongs_to_source(item, source)
            ]
            debug_rows = [
                item
                for item in debug_rows
                if not _debug_belongs_to_source(item, source)
            ]
        else:
            results = [
                item
                for item in results
                if not (
                    _event_belongs_to_source(item, source)
                    and _event_listing_url(item).rstrip("/") in published
                )
            ]

        source_results, source_debug = collect_published_live_source(
            source,
            rules,
            today=today,
        )
        live_results.extend(source_results)
        live_debug.extend(source_debug)
        activations.append(
            {
                "source_id": source_id,
                "listing_urls": sorted(published),
                "full_source_activation": full_source,
                "rule_versions": [rule.version for rule in rules],
                "mode": "recorded_actions_listing_and_detail",
            }
        )

    existing = {str(item.get("url") or "") for item in results}
    for item in live_results:
        if str(item.get("url") or "") not in existing:
            results.append(item)
            existing.add(str(item.get("url") or ""))

    result_payload["results"] = results
    result_payload["count"] = len(results)
    result_payload["debug_by_source"] = debug_rows + live_debug
    result_payload["studio_activations"] = activations
    result_payload["studio_source_count"] = len(activations)
    if any(row.get("complete") is False for row in live_debug):
        result_payload["partial"] = True
    return result_payload


__all__ = ["apply_published_live_rules", "collect_published_live_source"]
