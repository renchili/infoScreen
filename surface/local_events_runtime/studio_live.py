from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .browser import find_browser_executable
from .extract import clean, label_dates
from .studio_actions import execute_browser_actions
from .studio_capture import DOM_EVIDENCE_JS, write_snapshot
from .studio_evaluate import _write_test_run, rule_fingerprint, validate_detail_url
from .studio_live_overlay import OVERLAY_JS
from .studio_rules import (
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_STUDIO_ROOT,
    LocalEventStudioRule,
    LocalEventStudioRuleStore,
    canonical_listing_url,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(source_id: str, listing_url: str) -> str:
    digest = hashlib.sha256(canonical_listing_url(listing_url).encode("utf-8")).hexdigest()[:12]
    return f"{source_id}-{digest}"


def _live_dir(root: Path) -> Path:
    path = root / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(root: Path, source_id: str, listing_url: str) -> Path:
    return _live_dir(root) / f"{_key(source_id, listing_url)}.json"


def _read_state(root: Path, source_id: str, listing_url: str) -> dict[str, Any]:
    try:
        value = json.loads(
            _state_path(root, source_id, listing_url).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(
    root: Path,
    source_id: str,
    listing_url: str,
    **changes: Any,
) -> dict[str, Any]:
    path = _state_path(root, source_id, listing_url)
    payload = {
        "source_id": source_id,
        "listing_url": canonical_listing_url(listing_url),
        **_read_state(root, source_id, listing_url),
        **changes,
        "updated_at": _now().isoformat(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return payload


def _alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> dict[str, Any]:
    """Start one detached headed Chromium worker for a configured listing."""

    studio_root = Path(root).expanduser().resolve()
    store = LocalEventStudioRuleStore(
        root=studio_root,
        source_config_path=source_config_path,
    )
    safe_source, canonical_url = store._binding(source_id, listing_url)
    current = _read_state(studio_root, safe_source, canonical_url)
    if _alive(int(current.get("pid") or 0)):
        return {**current, "ok": True, "already_running": True}

    worker = Path(__file__).resolve().parents[1] / "jobs" / "local_event_studio_live.py"
    log = _live_dir(studio_root) / f"{_key(safe_source, canonical_url)}.log"
    environment = os.environ.copy()
    environment["INFOSCREEN_ENV_DIR"] = str(studio_root.parent)
    with log.open("ab") as handle:
        process = subprocess.Popen(
            [sys.executable, str(worker), safe_source, canonical_url],
            cwd=str(worker.parents[1]),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=environment,
        )
    state = _write_state(
        studio_root,
        safe_source,
        canonical_url,
        pid=process.pid,
        status="starting",
        current_url=canonical_url,
        started_at=_now().isoformat(),
        log_path=str(log),
    )
    return {**state, "ok": True, "already_running": False}


def _source(path: Path, source_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload.get("sources") or []:
        if isinstance(item, dict) and item.get("id") == source_id:
            return dict(item)
    raise ValueError(f"source not found: {source_id}")


def _allowed(url: str, source: dict[str, Any]) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(
        host
        and any(
            host == str(domain).lower().removeprefix("www.")
            or host.endswith("." + str(domain).lower().removeprefix("www."))
            for domain in source.get("allowed_domains") or []
        )
    )


def _role(url: str, listing_url: str) -> str:
    current = urlsplit(url)
    listing = urlsplit(canonical_listing_url(listing_url))
    return (
        "listing"
        if (
            current.netloc.lower(),
            current.path.rstrip("/"),
        )
        == (
            listing.netloc.lower(),
            listing.path.rstrip("/"),
        )
        else "detail"
    )


def _selector(
    selector: str,
    attribute: str | None = None,
    optional: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {"selector": selector, "optional": optional}
    if attribute:
        value["attribute"] = attribute
    return value


def _empty(source_id: str, listing_url: str) -> dict[str, Any]:
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
        else _empty(source_id, listing_url)
    )


def _action_from_selection(mode: str, data: dict[str, Any]) -> dict[str, Any]:
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


def _save_selection(
    store: LocalEventStudioRuleStore,
    source_id: str,
    listing_url: str,
    data: dict[str, Any],
) -> LocalEventStudioRule:
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
            raw.setdefault(bucket, []).append(_action_from_selection(mode, data))
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
        raw.setdefault("fields", {})["url"] = _selector(selector, "href")
    elif mode in {"title", "when", "where", "summary", "image"}:
        target = raw.setdefault("fields", {})
        if role == "detail":
            detail = raw.setdefault(
                "detail_page",
                {"enabled": True, "fields": {}},
            )
            detail["enabled"] = True
            target = detail.setdefault("fields", {})
            if mode in {"title", "when", "where"} and mode not in raw["fields"]:
                placeholder = _selector(
                    f"#__infoscreen_detail_only_{mode}",
                    optional=True,
                )
                if mode == "where":
                    placeholder["allow_source_default"] = False
                raw["fields"][mode] = placeholder
        target[mode] = _selector(
            selector,
            attribute,
            optional=mode in {"summary", "image"},
        )
    else:
        raise ValueError(f"unsupported mode: {mode}")
    return store.save_draft(raw)


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


def _goto_detail(page: Any, url: str) -> Any:
    try:
        response = page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception:
        response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
    if response is not None and response.status >= 400:
        raise ValueError(f"detail_http_status_{response.status}")
    return response


def _validate(
    page: Any,
    context: Any,
    rule: LocalEventStudioRule,
    source: dict[str, Any],
) -> dict[str, Any]:
    fatal: list[str] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    cards = page.locator(rule.card.selector).all() if rule.card else []
    if not cards:
        fatal.append("card_selector_matched_zero_elements")
    for name in ("title", "when", "where", "url"):
        if getattr(rule.fields, name) is None:
            fatal.append(f"{name}_selector_missing")
    if fatal:
        return {
            "schema_version": 1,
            "rule_fingerprint": rule_fingerprint(rule),
            "source_id": rule.source_id,
            "listing_url": rule.listing_url,
            "card_selector": rule.card.selector if rule.card else None,
            "matched_card_count": len(cards),
            "accepted_count": 0,
            "rejected_count": 0,
            "publishable": False,
            "fatal_errors": list(dict.fromkeys(fatal)),
            "warnings": [],
            "accepted": [],
            "rejected": [],
            "validation_mode": "operator_live_browser_with_detail_pages",
        }

    seen: set[str] = set()
    for index, card in enumerate(cards[:12]):
        if len(accepted) >= 3:
            break
        try:
            if any(
                card.locator(selector).count() > 0
                or bool(card.evaluate("(element, value) => element.matches(value)", selector))
                for selector in (rule.card.exclude_selectors if rule.card else [])
            ):
                continue

            raw_url = _value(
                card.locator(rule.fields.url.selector),
                rule.fields.url.attribute,
            )
            public_url, reason = validate_detail_url(
                raw_url,
                rule.listing_url,
                source,
            )
            if reason or public_url in seen:
                raise ValueError(reason or "duplicate_detail_url")
            seen.add(public_url)

            values: dict[str, str] = {"url": public_url}
            for name in ("title", "when", "where", "summary", "image"):
                mapping = getattr(rule.fields, name)
                if mapping:
                    values[name] = _value(
                        card.locator(mapping.selector),
                        mapping.attribute,
                    )

            detail = context.new_page()
            detail_info: dict[str, Any] = {}
            try:
                _goto_detail(detail, public_url)
                if not _allowed(str(detail.url), source):
                    raise ValueError("detail_redirected_outside_allowed_domains")
                final_url, final_reason = validate_detail_url(
                    str(detail.url),
                    rule.listing_url,
                    source,
                )
                if final_reason:
                    raise ValueError(final_reason)
                execute_browser_actions(detail, rule.detail_actions)
                root_text = _value(detail.locator("main, article, body"), None)
                if not root_text and not clean(detail.title() or ""):
                    raise ValueError("detail_page_has_no_readable_content")
                if rule.detail_page.enabled:
                    for name in ("title", "when", "where", "summary", "image"):
                        mapping = getattr(rule.detail_page.fields, name)
                        if mapping:
                            value = _value(
                                detail.locator(mapping.selector),
                                mapping.attribute,
                            )
                            if value:
                                values[name] = value
                public_url = final_url
                values["url"] = public_url
                detail_info = {
                    "ok": True,
                    "url": public_url,
                    "page_title": detail.title(),
                }
            finally:
                detail.close()

            reasons = [
                f"{name}_missing_after_detail"
                for name in ("title", "when", "where")
                if not values.get(name)
            ]
            dates = label_dates(values.get("when", ""))
            if not dates:
                reasons.append("when_not_parseable")
            elif (
                rule.validation.require_current_or_future_date
                and max(dates) < _now().date()
            ):
                reasons.append("event_expired")
            if reasons:
                raise ValueError(reasons[0])

            accepted.append(
                {
                    "card_id": f"live-{index}",
                    "event": {
                        "title": values["title"],
                        "when": values["when"],
                        "where": values["where"],
                        "url": public_url,
                        "summary": values.get("summary", ""),
                        "image": values.get("image", ""),
                        "start_date": min(dates).isoformat(),
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
                    "card_id": f"live-{index}",
                    "reason": str(exc) or type(exc).__name__,
                }
            )

    if len(accepted) < 2:
        fatal.append("live_validation_requires_two_confirmed_detail_pages")
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
        "fatal_errors": list(dict.fromkeys(fatal)),
        "warnings": [],
        "accepted": accepted,
        "rejected": rejected,
        "validation_mode": "operator_live_browser_with_detail_pages",
    }


def run_live_session(
    source_id: str,
    listing_url: str,
    *,
    root: Path | str = DEFAULT_STUDIO_ROOT,
    source_config_path: Path | str = DEFAULT_SOURCE_CONFIG,
) -> int:
    """Run one headed browser session until the operator closes all pages."""

    studio_root = Path(root).resolve()
    config_path = Path(source_config_path).resolve()
    store = LocalEventStudioRuleStore(
        root=studio_root,
        source_config_path=config_path,
    )
    safe_source, canonical_url = store._binding(source_id, listing_url)
    source = _source(config_path, safe_source)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            status="failed",
            error=f"missing_playwright:{exc}",
        )
        return 2
    executable = find_browser_executable()
    if not executable:
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            status="failed",
            error="missing_system_chromium",
        )
        return 3

    binding = "__infoscreenStudioBinding"
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(_live_dir(studio_root) / f"{_key(safe_source, canonical_url)}-profile"),
            headless=False,
            executable_path=executable,
            viewport=None,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        def capture(current_page: Any) -> dict[str, Any]:
            if _role(str(current_page.url), canonical_url) != "listing":
                raise ValueError("Return to the configured listing first")
            dom = current_page.evaluate(DOM_EVIDENCE_JS, {"maxElements": 6000})
            captured = _now()
            snapshot_id = (
                captured.strftime("%Y%m%dT%H%M%S%fZ")
                + "-"
                + hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:10]
            )
            metadata = {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "source_id": safe_source,
                "source_name": source.get("name"),
                "listing_url": canonical_url,
                "final_url": str(current_page.url),
                "page_title": current_page.title(),
                "captured_at": captured.isoformat(),
                "prepare": {"mode": "operator_live_browser"},
                "dom_element_count": int(dom.get("element_count") or 0),
                "dom_truncated": bool(dom.get("truncated")),
                "assets": {
                    "page.png": "page.png",
                    "page.html": "page.html",
                    "dom.json": "dom.json",
                    "metadata.json": "metadata.json",
                },
            }
            snapshot = write_snapshot(
                studio_root,
                metadata,
                screenshot=current_page.screenshot(full_page=True, type="png"),
                html=current_page.content(),
                dom=dom,
            )
            draft = store.load_draft(safe_source, canonical_url)
            if draft is None:
                raise ValueError("Select card, detail link and detail fields first")
            test = _write_test_run(
                studio_root,
                _validate(current_page, context, draft, source),
                snapshot_id,
            )
            return {**snapshot, "test_result": test}

        def callback(source_binding: Any, payload: Any) -> dict[str, Any]:
            data = dict(payload or {})
            current_page = source_binding["page"]
            action = data.get("action")
            if action == "clear_draft":
                store.delete_draft(safe_source, canonical_url)
                return {"ok": True, "message": "Draft cleared."}
            if action == "capture_listing":
                snapshot = capture(current_page)
                test = snapshot["test_result"]
                return {
                    "ok": True,
                    "message": (
                        f"Validation {'passed' if test['publishable'] else 'failed'}: "
                        f"{test['accepted_count']} confirmed details."
                    ),
                }
            if action == "select":
                data["page_role"] = _role(str(current_page.url), canonical_url)
                draft = _save_selection(
                    store,
                    safe_source,
                    canonical_url,
                    data,
                )
                return {
                    "ok": True,
                    "message": f"Saved {data.get('mode')}: {data.get('selector') or ''}",
                    "card_selector": draft.card.selector if draft.card else "",
                }
            raise ValueError("unsupported action")

        context.expose_binding(binding, callback)

        def install(target: Any) -> None:
            if not _allowed(str(target.url), source):
                return
            target.evaluate(
                OVERLAY_JS,
                {
                    "binding": binding,
                    "listing_url": canonical_url,
                },
            )
            draft = store.load_draft(safe_source, canonical_url)
            if draft and draft.card:
                target.evaluate(
                    "selector => window.__infoscreenCardSelector = selector",
                    draft.card.selector,
                )

        def configure(target: Any) -> None:
            target.on("domcontentloaded", lambda: install(target))
            target.on(
                "framenavigated",
                lambda frame: (
                    _write_state(
                        studio_root,
                        safe_source,
                        canonical_url,
                        pid=os.getpid(),
                        status="running",
                        current_url=str(target.url),
                    )
                    if frame == target.main_frame
                    else None
                ),
            )

        for target in context.pages:
            configure(target)
        context.on("page", configure)
        try:
            page.goto(canonical_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            page.goto(canonical_url, wait_until="commit", timeout=30000)
        page.wait_for_timeout(600)
        install(page)
        _write_state(
            studio_root,
            safe_source,
            canonical_url,
            pid=os.getpid(),
            status="running",
            current_url=canonical_url,
        )
        try:
            while context.pages:
                time.sleep(0.5)
        finally:
            _write_state(
                studio_root,
                safe_source,
                canonical_url,
                status="closed",
            )
            context.close()
    return 0


__all__ = ["run_live_session", "start_live_session"]
