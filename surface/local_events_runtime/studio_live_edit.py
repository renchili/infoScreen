from __future__ import annotations

from typing import Any

from .studio_rules import LocalEventStudioRule, LocalEventStudioRuleStore


def _selector(
    selector: str,
    attribute: str | None = None,
    optional: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {"selector": selector, "optional": optional}
    if attribute:
        value["attribute"] = attribute
    return value


def _empty_rule(source_id: str, listing_url: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_id": source_id,
        "listing_url": listing_url,
        "version": 0,
        "status": "draft",
        "fields": {},
        "detail_page": {"enabled": False, "fields": {}},
        "listing_actions": [],
        "detail_actions": [],
        "validation": {
            "require_public_detail_url": True,
            "require_current_or_future_date": True,
        },
    }


def _editable_rule(
    store: LocalEventStudioRuleStore,
    source_id: str,
    listing_url: str,
) -> dict[str, Any]:
    current = store.load_draft(source_id, listing_url)
    if current is None:
        current = store.load_published(source_id, listing_url)
    return (
        current.model_dump(mode="json", exclude_none=True)
        if current is not None
        else _empty_rule(source_id, listing_url)
    )


def _action_payload(mode: str, data: dict[str, Any]) -> dict[str, Any]:
    selector = str(data.get("selector") or "").strip() or None
    wait_ms = int(data.get("wait_ms") or 500)
    optional = bool(data.get("optional"))
    if mode == "action_click":
        return {
            "action": "click",
            "selector": selector,
            "optional": optional,
            "wait_ms": wait_ms,
        }
    if mode == "action_repeat":
        return {
            "action": "click_repeat",
            "selector": selector,
            "optional": optional,
            "max_rounds": int(data.get("max_rounds") or 20),
            "wait_ms": wait_ms,
        }
    if mode == "action_select":
        return {
            "action": "select_option",
            "selector": selector,
            "value": str(data.get("value") or ""),
            "optional": optional,
            "wait_ms": wait_ms,
        }
    if mode == "action_scroll":
        return {
            "action": "scroll_to_bottom",
            "optional": optional,
            "wait_ms": wait_ms,
        }
    if mode == "action_wait":
        return {
            "action": "wait",
            "optional": optional,
            "wait_ms": int(data.get("wait_ms") or 1000),
        }
    raise ValueError(f"unsupported action mode: {mode}")


def save_live_selection(
    store: LocalEventStudioRuleStore,
    source_id: str,
    listing_url: str,
    data: dict[str, Any],
) -> LocalEventStudioRule:
    """Apply one real-page selection to an inert draft rule."""

    raw = _editable_rule(store, source_id, listing_url)
    mode = str(data.get("mode") or "")
    role = str(data.get("page_role") or "")
    selector = str(data.get("selector") or "").strip()
    attribute = str(data.get("attribute") or "").strip() or None

    if mode.startswith("action_"):
        bucket = "listing_actions" if role == "listing" else "detail_actions"
        if mode == "action_clear":
            raw[bucket] = []
        else:
            raw.setdefault(bucket, []).append(_action_payload(mode, data))
        return store.save_draft(raw)

    if not selector:
        raise ValueError("empty selector")
    if mode == "card":
        raw["card"] = {
            "selector": selector,
            "exclude_selectors": list(
                (raw.get("card") or {}).get("exclude_selectors") or []
            ),
        }
    elif mode == "exclude":
        card = dict(raw.get("card") or {})
        if not card.get("selector"):
            raise ValueError("select LIST CARD first")
        card["exclude_selectors"] = list(
            dict.fromkeys([*(card.get("exclude_selectors") or []), selector])
        )
        raw["card"] = card
    elif mode == "url":
        if role != "listing":
            raise ValueError("DETAIL LINK belongs on the listing page")
        raw.setdefault("fields", {})["url"] = _selector(selector, "href")
    elif mode in {"title", "when", "where", "summary", "image"}:
        if role == "detail":
            detail = raw.setdefault(
                "detail_page",
                {"enabled": True, "fields": {}},
            )
            detail["enabled"] = True
            target = detail.setdefault("fields", {})
        else:
            target = raw.setdefault("fields", {})
        mapping = _selector(
            selector,
            attribute,
            optional=mode in {"summary", "image"},
        )
        if mode == "where":
            mapping["allow_source_default"] = False
        target[mode] = mapping
    else:
        raise ValueError(f"unsupported mode: {mode}")
    return store.save_draft(raw)


__all__ = ["save_live_selection"]
