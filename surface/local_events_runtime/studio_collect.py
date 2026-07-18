from __future__ import annotations

import json
import os
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .browser import DOM_TIMEOUT_MS, NAV_TIMEOUT_MS, PREPARE_PAGE_JS, launch_chromium
from .studio_capture import DOM_EVIDENCE_JS
from .studio_dom import SnapshotDom, StudioSelectorError, select_nodes
from .studio_evaluate import evaluate_rule, validate_detail_url
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRule,
    LocalEventStudioRuleStore,
    canonical_listing_url,
)

DETAIL_LIMIT = int(os.environ.get("LOCAL_EVENT_STUDIO_DETAIL_LIMIT", "24"))
DETAIL_TIMEOUT_MS = int(os.environ.get("LOCAL_EVENT_STUDIO_DETAIL_TIMEOUT_MS", "16000"))
LOAD_MORE_ROUNDS = int(os.environ.get("LOCAL_EVENT_STUDIO_LOAD_MORE_ROUNDS", "12"))
MAX_DOM_ELEMENTS = int(os.environ.get("LOCAL_EVENT_STUDIO_MAX_DOM_ELEMENTS", "6000"))


class StudioCollectionError(RuntimeError):
    """Raised when one published Studio source cannot be collected safely."""


class StudioBrowser(AbstractContextManager["StudioBrowser"]):
    """One Playwright browser reused for a source's list and detail pages."""

    def __init__(self) -> None:
        self._playwright_context = None
        self._browser = None

    def __enter__(self) -> "StudioBrowser":
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - deployment dependency
            raise StudioCollectionError("missing_playwright_python_package") from exc
        self._playwright_context = sync_playwright()
        playwright = self._playwright_context.__enter__()
        self._browser = launch_chromium(playwright)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright_context is not None:
            self._playwright_context.__exit__(exc_type, exc, traceback)

    def _page(self):
        if self._browser is None:
            raise StudioCollectionError("Studio browser is not started")
        return self._browser.new_page(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
        )

    def render_listing(self, source: dict[str, Any], listing_url: str) -> dict[str, Any]:
        """Render one configured list and return current DOM evidence without persistence."""

        page = self._page()
        try:
            try:
                page.goto(listing_url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            except Exception:
                page.goto(listing_url, wait_until="domcontentloaded", timeout=DOM_TIMEOUT_MS)
            page.wait_for_timeout(700)
            prepare = page.evaluate(
                PREPARE_PAGE_JS,
                {"maxRounds": int(source.get("load_more_rounds", LOAD_MORE_ROUNDS))},
            )
            final_url = str(page.url)
            if not _host_allowed(
                final_url,
                [str(item) for item in source.get("allowed_domains") or []],
            ):
                raise StudioCollectionError("listing_redirected_outside_allowed_domains")
            dom = page.evaluate(DOM_EVIDENCE_JS, {"maxElements": MAX_DOM_ELEMENTS})
            return {
                "final_url": final_url,
                "page_title": str(page.title() or ""),
                "prepare": prepare,
                "dom": dom,
            }
        finally:
            page.close()

    def render_detail(self, source: dict[str, Any], detail_url: str) -> dict[str, Any]:
        """Render one admitted public detail URL for explicitly mapped field overrides."""

        page = self._page()
        try:
            try:
                page.goto(detail_url, wait_until="networkidle", timeout=DETAIL_TIMEOUT_MS)
            except Exception:
                page.goto(detail_url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
            page.wait_for_timeout(300)
            final_url = str(page.url)
            if not _host_allowed(
                final_url,
                [str(item) for item in source.get("allowed_domains") or []],
            ):
                raise StudioCollectionError("detail_redirected_outside_allowed_domains")
            return {
                "final_url": final_url,
                "page_title": str(page.title() or ""),
                "dom": page.evaluate(DOM_EVIDENCE_JS, {"maxElements": MAX_DOM_ELEMENTS}),
            }
        finally:
            page.close()


def _host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in allowed_domains
        )
    )


def _source_inventory(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioCollectionError(f"invalid source configuration: {exc}") from exc
    return [dict(item) for item in payload.get("sources") or [] if isinstance(item, dict)]


def published_rules_by_source(
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> dict[str, list[LocalEventStudioRule]]:
    """Return active rules grouped by source, without treating drafts as active."""

    store = LocalEventStudioRuleStore(root=root, source_config_path=source_config_path)
    output: dict[str, list[LocalEventStudioRule]] = {}
    for source in store.configured_sources():
        rules = [
            rule
            for listing_url in source.listing_urls
            if (rule := store.load_published(source.id, listing_url)) is not None
        ]
        if rules:
            output[source.id] = rules
    return output


def _detail_value(dom: SnapshotDom, selector_rule: Any) -> tuple[str, dict[str, Any] | None]:
    if selector_rule is None:
        return "", None
    nodes = select_nodes(dom, selector_rule.selector)
    if not nodes:
        return "", None
    node = nodes[0]
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    if selector_rule.attribute == "src":
        raw = str(node.get("src") or attributes.get("src") or "").strip()
    elif selector_rule.attribute:
        raw = str(attributes.get(selector_rule.attribute) or "").strip()
    else:
        raw = " ".join(str(node.get("text") or "").split())
    if not raw:
        return "", None
    return raw, {
        "page_role": "detail",
        "selector": selector_rule.selector,
        "element_id": node.get("id"),
        "raw_value": raw,
        "normalized_value": raw,
        "attribute": selector_rule.attribute,
        "precedence": "detail_mapped_field",
    }


def _apply_detail_rule(
    accepted: dict[str, Any],
    rule: LocalEventStudioRule,
    source: dict[str, Any],
    browser: StudioBrowser,
) -> dict[str, Any]:
    if not rule.detail_page.enabled:
        return accepted

    event = dict(accepted.get("event") or {})
    evidence = dict(accepted.get("evidence") or {})
    try:
        detail = browser.render_detail(source, str(event.get("url") or ""))
        detail_dom = SnapshotDom(detail.get("dom") or {})
        for name in ("title", "when", "where", "summary", "image"):
            value, field_evidence = _detail_value(
                detail_dom,
                getattr(rule.detail_page.fields, name),
            )
            if value:
                event[name] = value
                evidence[name] = field_evidence
        public_url, url_reason = validate_detail_url(
            str(detail.get("final_url") or event.get("url") or ""),
            rule.listing_url,
            source,
        )
        if public_url and not url_reason:
            event["url"] = public_url
            if "url" in evidence:
                evidence["url"] = {
                    **evidence["url"],
                    "normalized_value": public_url,
                    "detail_redirect_observed": True,
                }
        return {
            **accepted,
            "event": event,
            "evidence": evidence,
            "detail_page_pending": False,
            "detail_page": {
                "ok": True,
                "final_url": detail.get("final_url"),
                "page_title": detail.get("page_title"),
            },
        }
    except Exception as exc:
        return {
            **accepted,
            "event": event,
            "evidence": evidence,
            "detail_page_pending": False,
            "detail_page": {
                "ok": False,
                "error": type(exc).__name__,
                "detail": str(exc)[:300],
            },
        }


def collect_published_source(
    source: dict[str, Any],
    rules: list[LocalEventStudioRule],
    *,
    browser_factory: Callable[[], StudioBrowser] = StudioBrowser,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect one source only from its published Studio listing rules."""

    results: list[dict[str, Any]] = []
    debug_rows: list[dict[str, Any]] = []
    with browser_factory() as browser:
        for rule in rules:
            debug: dict[str, Any] = {
                "source": source.get("name") or rule.source_id,
                "source_id": rule.source_id,
                "adapter": "studio_published_rule",
                "listing_urls": [rule.listing_url],
                "studio_rule_version": rule.version,
                "status": "complete",
                "complete": True,
                "listing_fetched": 0,
                "cards_found": 0,
                "accepted": 0,
                "reason_counts": {},
            }
            try:
                rendered = browser.render_listing(source, rule.listing_url)
                debug["listing_fetched"] = 1
                debug["final_url"] = rendered.get("final_url")
                debug["prepare"] = rendered.get("prepare") or {}
                evaluation = evaluate_rule(
                    rule,
                    rendered.get("dom") or {},
                    source,
                    today=today,
                )
                debug["cards_found"] = evaluation.get("matched_card_count", 0)
                debug["accepted"] = evaluation.get("accepted_count", 0)
                debug["publishable"] = evaluation.get("publishable", False)
                debug["fatal_errors"] = evaluation.get("fatal_errors") or []
                debug["warnings"] = evaluation.get("warnings") or []
                debug["not_output_preview"] = (evaluation.get("rejected") or [])[:12]
                reason_counts: dict[str, int] = {}
                for rejected in evaluation.get("rejected") or []:
                    reason = str(rejected.get("reason") or "unknown")
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                debug["reason_counts"] = reason_counts

                accepted_rows = list(evaluation.get("accepted") or [])
                if rule.detail_page.enabled:
                    accepted_rows = [
                        _apply_detail_rule(item, rule, source, browser)
                        if index < DETAIL_LIMIT
                        else {
                            **item,
                            "detail_page_pending": False,
                            "detail_page": {"ok": False, "error": "detail_limit_reached"},
                        }
                        for index, item in enumerate(accepted_rows)
                    ]

                for item in accepted_rows:
                    event = dict(item.get("event") or {})
                    event.update(
                        {
                            "candidate_policy": "official-listing-authority-v1",
                            "source_type": "studio_published_rule",
                            "studio_rule_version": rule.version,
                            "studio_listing_url": rule.listing_url,
                            "studio_evidence": item.get("evidence") or {},
                            "studio_detail_page": item.get("detail_page"),
                        }
                    )
                    results.append(event)
                debug["accepted_preview"] = [
                    {
                        "title": item.get("title"),
                        "when": item.get("when"),
                        "where": item.get("where"),
                        "url": item.get("url"),
                    }
                    for item in results[-len(accepted_rows):]
                ] if accepted_rows else []
            except Exception as exc:
                debug.update(
                    {
                        "status": "failed",
                        "complete": False,
                        "error": type(exc).__name__,
                        "detail": str(exc)[:500],
                    }
                )
            debug_rows.append(debug)
    return results, debug_rows


def _event_belongs_to_source(event: dict[str, Any], source: dict[str, Any]) -> bool:
    source_id = str(source.get("id") or "")
    source_name = str(source.get("name") or "")
    return bool(
        event.get("source_id") == source_id
        or event.get("source_name") == source_name
        or event.get("host") == source_name
        or event.get("source") == source_name
    )


def _event_listing_url(event: dict[str, Any]) -> str:
    for key in ("listing_url", "studio_listing_url", "listing_source_url"):
        value = event.get(key)
        if value:
            try:
                return canonical_listing_url(value)
            except ValueError:
                return ""
    return ""


def _debug_belongs_to_source(row: dict[str, Any], source: dict[str, Any]) -> bool:
    return bool(
        row.get("source_id") == source.get("id")
        or row.get("source") == source.get("name")
    )


def apply_published_studio_rules(
    payload: dict[str, Any],
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
    browser_factory: Callable[[], StudioBrowser] = StudioBrowser,
    today: date | None = None,
) -> dict[str, Any]:
    """Replace only activated source/listing results while preserving legacy sources."""

    output = dict(payload)
    results = [dict(item) for item in output.get("results") or [] if isinstance(item, dict)]
    debug_rows = [dict(item) for item in output.get("debug_by_source") or [] if isinstance(item, dict)]
    config_path = Path(source_config_path).expanduser().resolve()
    sources = _source_inventory(config_path)
    source_by_id = {str(source.get("id") or ""): source for source in sources}
    rules_by_source = published_rules_by_source(root=root, source_config_path=config_path)
    if not rules_by_source:
        return output

    studio_results: list[dict[str, Any]] = []
    studio_debug: list[dict[str, Any]] = []
    activated: list[dict[str, Any]] = []

    for source_id, rules in rules_by_source.items():
        source = source_by_id.get(source_id)
        if source is None:
            continue
        configured_urls = {
            canonical_listing_url(value)
            for value in source.get("listing_urls") or []
        }
        published_urls = {rule.listing_url for rule in rules}
        full_source_activation = bool(configured_urls) and published_urls == configured_urls

        if full_source_activation:
            results = [item for item in results if not _event_belongs_to_source(item, source)]
            debug_rows = [item for item in debug_rows if not _debug_belongs_to_source(item, source)]
        else:
            results = [
                item
                for item in results
                if not (
                    _event_belongs_to_source(item, source)
                    and _event_listing_url(item) in published_urls
                )
            ]

        source_results, source_debug = collect_published_source(
            source,
            rules,
            browser_factory=browser_factory,
            today=today,
        )
        studio_results.extend(source_results)
        studio_debug.extend(source_debug)
        activated.append(
            {
                "source_id": source_id,
                "listing_urls": sorted(published_urls),
                "full_source_activation": full_source_activation,
                "rule_versions": [rule.version for rule in rules],
            }
        )

    existing_urls = {str(item.get("url") or "") for item in results}
    for item in studio_results:
        if str(item.get("url") or "") not in existing_urls:
            results.append(item)
            existing_urls.add(str(item.get("url") or ""))

    output["results"] = results
    output["count"] = len(results)
    output["debug_by_source"] = debug_rows + studio_debug
    output["studio_activations"] = activated
    output["studio_source_count"] = len(activated)
    if any(row.get("complete") is False for row in studio_debug):
        output["partial"] = True
    return output


__all__ = [
    "StudioBrowser",
    "StudioCollectionError",
    "apply_published_studio_rules",
    "collect_published_source",
    "published_rules_by_source",
]
